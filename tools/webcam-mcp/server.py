#!/usr/bin/env python3
"""Local webcam stills and V4L2 controls for Cursor agents (streamable HTTP MCP).

Same capture approach as tools/webcam_still.sh: ffmpeg -f v4l2, one JPEG,
then drop the device so scripts like tools/measure_blink.sh can use it.
Does not touch the FPGA, serial ports, or openFPGALoader.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Image

from controls import (
    TARGET_MEAN,
    apply_control_updates,
    apply_saved_controls,
    current_values,
    driver_defaults,
    freeze_auto_exposure,
    list_device_controls,
    load_saved_controls,
    measure_jpeg,
    resolve_updates,
    save_device_controls,
    suggest_nudge,
    well_exposed,
)

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from blink_trust import parse_roi_arg  # noqa: E402

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 8766
CAPTURE_DIR = Path(os.environ.get("WEBCAM_MCP_CAPTURE_DIR", Path.home() / "fpga" / "captures"))
DEFAULT_DEVICE = os.environ.get("WEBCAM_MCP_DEVICE", "/dev/video0")
DEFAULT_SIZE = "640x480"
LOCK_TIMEOUT_S = 90.0
FFMPEG_TIMEOUT_S = 25.0
ANALYZE_PYTHON = os.environ.get("WEBCAM_MCP_ANALYZE_PYTHON", "/usr/bin/python3")
ANALYZE_SCRIPT = Path(__file__).resolve().parent.parent / "analyze_blink.py"
BLINK_DIR = Path(os.environ.get("WEBCAM_MCP_BLINK_DIR", Path.home() / "fpga" / "blink-measure"))
AUTO_ADJUST_MAX_ITERS = 8
# Optional per-call software eq, off by default. The previous capture_still
# default (brightness=0.25/contrast=1.6/gamma=1.8) washed out the Logitech.
ENHANCE_VF = "eq=brightness=0.25:contrast=1.6:gamma=1.8"

DEVICE_RE = re.compile(r"^/dev/video\d+$")
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")

mcp = MCPServer(
    "webcam",
    instructions=(
        "Take still JPEGs from V4L2 cameras on this machine (Bee) and adjust "
        "the Logitech QuickCam Pro for Notebooks (046d:0991, /dev/video0) with "
        "real v4l2-ctl controls. capture_still returns the raw camera JPEG by "
        "default; pass enhance=true only for an optional mild software eq. "
        "If a frame looks washed out or too dark, call get_camera_controls, "
        "then set_camera_controls (brightness/contrast/gain/auto_exposure/"
        "exposure/white_balance) or auto_adjust. reset_camera_controls restores "
        "driver defaults. Settings persist across captures and service restarts. "
        "measure_blink records a clip and reports BOTH the edge/threshold rate "
        "and the FFT rate (trust FFT when edges undercount, historically ~6.9 Hz), "
        "plus brightness.png and roi.png. roi may be auto, top, bottom, nano4k "
        "(bottom on Bee), primer20k (top), or x,y,w,h. Named halves prepare for "
        "two boards in one frame; this tool still meters one LED. "
        "Does not touch the FPGA or serial ports. Stills go under "
        "~/fpga/captures/; blink runs under ~/fpga/blink-measure/."
    ),
)


def _lock_path() -> Path:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    return runtime / "webcam-mcp.lock"


@contextmanager
def camera_lock():
    """Exclusive flock so two agents cannot open the camera at once."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as fh:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"camera busy (lock {path} held for >{LOCK_TIMEOUT_S:.0f}s)"
                    ) from None
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def parse_device(device: str) -> str:
    device = (device or DEFAULT_DEVICE).strip()
    if not DEVICE_RE.match(device):
        raise ValueError(f"device must look like /dev/video0, not {device!r}")
    if not Path(device).exists():
        raise FileNotFoundError(f"{device} does not exist. Call list_cameras.")
    return device


def parse_size(resolution: str | None) -> tuple[int, int]:
    text = (resolution or DEFAULT_SIZE).strip().lower()
    match = SIZE_RE.match(text)
    if not match:
        raise ValueError(f"resolution must look like 640x480, not {resolution!r}")
    return int(match.group(1)), int(match.group(2))


def list_v4l_cameras() -> list[dict[str, str]]:
    root = Path("/sys/class/video4linux")
    if not root.is_dir():
        return []
    cameras: list[dict[str, str]] = []
    nodes = sorted(root.glob("video*"), key=lambda p: int(p.name[5:]))
    for node in nodes:
        name_file = node / "name"
        name = name_file.read_text(encoding="utf-8").strip() if name_file.exists() else ""
        cameras.append({"device": f"/dev/{node.name}", "name": name})
    return cameras


def still_paths(device: str, suffix: str = "") -> tuple[Path, Path]:
    """Return (raw, enhanced) paths that share a timestamp."""
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(device).name
    extra = f"-{suffix}" if suffix else ""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    def pair(stamp: str) -> tuple[Path, Path]:
        return (
            CAPTURE_DIR / f"{stamp}-{stem}{extra}-raw.jpg",
            CAPTURE_DIR / f"{stamp}-{stem}{extra}-enhanced.jpg",
        )

    raw, enhanced = pair(stamp)
    if raw.exists() or enhanced.exists():
        raw, enhanced = pair(datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    return raw, enhanced


def run_ffmpeg(cmd: list[str], what: str) -> None:
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed") from exc
    except subprocess.TimeoutExpired as extra:
        raise RuntimeError(f"ffmpeg {what} timed out") from extra
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"ffmpeg {what} failed: {detail}") from exc


def grab_still(device: str, out: Path, width: int, height: int, warmup_frames: int) -> None:
    """Grab one raw JPEG, then return so the V4L2 device is released."""
    frames = max(0, warmup_frames) + 1
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-f", "v4l2",
        "-video_size", f"{width}x{height}",
        "-i", device,
        "-frames:v", str(frames),
        "-update", "1",
        str(out),
    ]
    run_ffmpeg(cmd, "capture")
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg wrote no image to {out}")


def enhance_still(src: Path, dst: Path, vf: str) -> None:
    """Optional software eq on a saved JPEG. Does not open the camera."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-i", str(src),
        "-vf", vf,
        str(dst),
    ]
    run_ffmpeg(cmd, "enhance")
    if not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg wrote no enhanced image to {dst}")


def prepare_device(device: str) -> dict[str, int]:
    """Re-apply persisted v4l2 settings so they survive close/reopen and restarts."""
    try:
        return apply_saved_controls(device)
    except RuntimeError:
        # Device may not be ready yet at service start; capture will retry.
        return {}


def capture_raw(
    device: str,
    width: int,
    height: int,
    warmup_frames: int,
    suffix: str = "",
) -> Path:
    raw, _enhanced = still_paths(device, suffix=suffix)
    with camera_lock():
        prepare_device(device)
        grab_still(device, raw, width, height, warmup_frames)
    return raw


def maybe_enhance(raw: Path, enhance: bool, enhance_vf: str | None) -> Path | None:
    if not enhance:
        return None
    vf = (enhance_vf or ENHANCE_VF).strip()
    if not vf or not re.fullmatch(r"[0-9A-Za-z_:=,.+-]+", vf):
        raise ValueError("enhance_vf must be a simple ffmpeg filter like eq=brightness=0.05:contrast=1.1")
    enhanced = raw.with_name(raw.name.replace("-raw.jpg", "-enhanced.jpg"))
    if enhanced == raw:
        enhanced = raw.with_name(raw.stem + "-enhanced.jpg")
    enhance_still(raw, enhanced, vf)
    return enhanced


def snapshot_controls(device: str) -> dict[str, Any]:
    controls = list_device_controls(device)
    return {
        "device": device,
        "saved": load_saved_controls().get(device, {}),
        "controls": controls,
        "values": current_values(controls),
    }


def merge_persist(device: str, applied: dict[str, int]) -> dict[str, int]:
    prev = load_saved_controls().get(device, {})
    prev.update(applied)
    save_device_controls(device, prev)
    return prev


@mcp.tool()
def list_cameras() -> list[dict[str, str]]:
    """List V4L2 /dev/videoN devices and their kernel names.

    Does not open the camera. The Logitech QuickCam is usually /dev/video0
    (a matching /dev/video1 is often a metadata node and will fail capture).
    A later HDMI capture stick will appear as another named UVC device.
    """
    return list_v4l_cameras()


@mcp.tool()
def get_camera_controls(device: str = DEFAULT_DEVICE) -> dict[str, Any]:
    """List current V4L2 controls, ranges, and driver defaults.

    Includes brightness, contrast, gain, auto_exposure, exposure_time_absolute
    (alias: exposure), white_balance_automatic, white_balance_temperature
    (alias: white_balance), plus the other User/Camera controls this Logitech
    exposes. Inactive flags mean the auto counterpart is on.
    """
    device = parse_device(device)
    with camera_lock():
        prepare_device(device)
        return snapshot_controls(device)


@mcp.tool()
def set_camera_controls(
    device: str = DEFAULT_DEVICE,
    brightness: int | None = None,
    contrast: int | None = None,
    gain: int | None = None,
    auto_exposure: int | None = None,
    exposure: int | None = None,
    exposure_time_absolute: int | None = None,
    white_balance_automatic: int | None = None,
    white_balance: int | None = None,
    white_balance_temperature: int | None = None,
    saturation: int | None = None,
    sharpness: int | None = None,
    backlight_compensation: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Set one or more real camera controls via v4l2-ctl. Values persist.

    Prefer these over software eq. Setting exposure (or exposure_time_absolute)
    switches auto_exposure to Manual Mode (1) first. Setting white_balance
    (temperature) turns white_balance_automatic off. auto_exposure: 1=Manual,
    3=Aperture Priority. persist=true (default) writes ~/.local/state/webcam-mcp/
    so the next capture and service restart re-apply the same values.
    """
    device = parse_device(device)
    requested = {
        "brightness": brightness,
        "contrast": contrast,
        "gain": gain,
        "auto_exposure": auto_exposure,
        "exposure": exposure,
        "exposure_time_absolute": exposure_time_absolute,
        "white_balance_automatic": white_balance_automatic,
        "white_balance": white_balance,
        "white_balance_temperature": white_balance_temperature,
        "saturation": saturation,
        "sharpness": sharpness,
        "backlight_compensation": backlight_compensation,
    }
    with camera_lock():
        prepare_device(device)
        known = {c["name"]: c for c in list_device_controls(device)}
        updates = resolve_updates(requested, known)
        applied = apply_control_updates(device, updates)
        saved = merge_persist(device, applied) if persist else load_saved_controls().get(device, {})
        values = current_values(list_device_controls(device))
    return {
        "device": device,
        "applied": applied,
        "values": values,
        "saved": saved,
        "persisted": persist,
    }


@mcp.tool()
def reset_camera_controls(device: str = DEFAULT_DEVICE, persist: bool = True) -> dict[str, Any]:
    """Restore driver defaults for every control, then forget saved settings.

    On this Logitech that is typically brightness=128, contrast=32, gain=0,
    auto_exposure=3 (Aperture Priority), white_balance_automatic=1.
    """
    device = parse_device(device)
    with camera_lock():
        known = list_device_controls(device)
        defaults = driver_defaults(known)
        applied = apply_control_updates(device, defaults)
        if persist:
            save_device_controls(device, None)
        values = current_values(list_device_controls(device))
    return {
        "device": device,
        "applied": applied,
        "values": values,
        "persisted": persist,
        "saved_cleared": persist,
    }


@mcp.tool()
def capture_still(
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    enhance: bool = False,
    enhance_vf: str | None = None,
) -> list:
    """Capture one JPEG still.

    Returns the image for the model to look at, plus the saved path under
    ~/fpga/captures/. enhance=false (default) returns the raw camera frame.
    Pass enhance=true for optional software eq (mild; not the old washed-out
    brightness=0.25 boost). Releases the camera as soon as the raw grab
    finishes. warmup_frames discards the first N frames (auto-exposure);
    0 matches tools/webcam_still.sh. Camera v4l2 settings persist across shots.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    raw = capture_raw(device, width, height, warmup_frames)
    enhanced = maybe_enhance(raw, enhance, enhance_vf)
    shown = enhanced if enhanced is not None else raw
    lines = [f"Saved raw to {raw}"]
    if enhanced is not None:
        lines.append(f"Saved enhanced to {enhanced}")
    return ["\n".join(lines), Image(path=shown)]


@mcp.tool()
def capture_burst(
    n: int = 3,
    interval_s: float = 0.5,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    enhance: bool = False,
    enhance_vf: str | None = None,
) -> list[dict[str, str]]:
    """Capture N stills, sleeping interval_s between shots. Paths only.

    Each shot writes -raw.jpg. -enhanced.jpg is written only when enhance=true.
    The `path` field is the file returned to the model (raw unless enhance).
    The lock is held only while grabbing the raw frame.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if n < 1 or n > 30:
        raise ValueError("n must be 1..30")
    if interval_s < 0 or interval_s > 30:
        raise ValueError("interval_s must be 0..30")
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    shots: list[dict[str, str]] = []
    for i in range(n):
        raw = capture_raw(device, width, height, warmup_frames, suffix=f"{i:02d}")
        enhanced = maybe_enhance(raw, enhance, enhance_vf)
        shown = enhanced if enhanced is not None else raw
        shot = {"path": str(shown), "raw": str(raw)}
        if enhanced is not None:
            shot["enhanced"] = str(enhanced)
        shots.append(shot)
        if i + 1 < n and interval_s:
            time.sleep(interval_s)
    return shots


@mcp.tool()
def auto_adjust(
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    max_iters: int = AUTO_ADJUST_MAX_ITERS,
    target_mean: float = TARGET_MEAN,
) -> list:
    """Capture, measure mean luminance / clipping, and nudge v4l2 controls.

    Nudges gain, then brightness. Switches auto_exposure to Manual only if
    exposure_time_absolute itself must move. Stops when mean luma is near
    target_mean (default 115) without highlight clipping. Persists the
    exposure knobs. Returns a summary plus the last JPEG.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    if max_iters < 1 or max_iters > 20:
        raise ValueError("max_iters must be 1..20")
    if target_mean < 40 or target_mean > 200:
        raise ValueError("target_mean must be 40..200")

    history: list[dict[str, Any]] = []
    raw: Path | None = None
    applied_any: dict[str, int] = {}
    with camera_lock():
        prepare_device(device)
        for i in range(max_iters):
            raw, _ = still_paths(device, suffix=f"auto{i:02d}")
            grab_still(device, raw, width, height, warmup_frames)
            metrics = measure_jpeg(raw, width, height)
            known = {c["name"]: c for c in list_device_controls(device)}
            values = current_values(list(known.values()))
            nudge = suggest_nudge(known, metrics, target_mean=target_mean)
            step = {
                "iter": i,
                "path": str(raw),
                "metrics": metrics,
                "nudge": nudge,
                "values": {
                    name: values[name]
                    for name in (
                        "brightness",
                        "contrast",
                        "gain",
                        "auto_exposure",
                        "exposure_time_absolute",
                    )
                    if name in values
                },
            }
            history.append(step)
            if nudge is None:
                break
            if not nudge:
                break
            if "exposure_time_absolute" in nudge:
                freeze = freeze_auto_exposure(known)
                freeze.update(nudge)
                nudge = freeze
            apply_control_updates(device, nudge)
            applied_any.update(nudge)
        last_values = current_values(list_device_controls(device))
        knobs = {
            name: last_values[name]
            for name in (
                "brightness",
                "contrast",
                "gain",
                "auto_exposure",
                "exposure_time_absolute",
            )
            if name in last_values
        }
        if applied_any:
            persist_keys = set(applied_any) | {
                "gain",
                "brightness",
                "auto_exposure",
                "exposure_time_absolute",
            }
            merge_persist(device, {k: last_values[k] for k in persist_keys if k in last_values})

    assert raw is not None
    last = history[-1]
    ok = well_exposed(last["metrics"], target_mean=target_mean)
    status = "well exposed" if ok else "stopped before reaching the exposure band"
    text = (
        f"auto_adjust {status} after {len(history)} capture(s). "
        f"mean_luma={last['metrics']['mean_luma']} "
        f"clip_hi={last['metrics']['clip_hi_frac']} "
        f"values={knobs} path={raw}"
    )
    return [text, Image(path=raw)]


def _v4l2_silent(device: str, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", device, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def lock_exposure_for_measure(device: str, orig: dict[str, int]) -> None:
    """Match tools/measure_blink.sh: Manual AE, freeze shutter/gain, no dynamic fps."""
    ex = orig.get("exposure_time_absolute") or 166
    if orig.get("auto_exposure") != 1 and (ex < 10 or ex > 500):
        ex = 166
    updates = {
        "auto_exposure": 1,
        "exposure_time_absolute": int(ex),
        "exposure_dynamic_framerate": 0,
        "white_balance_automatic": 0,
    }
    if "gain" in orig:
        updates["gain"] = orig["gain"]
    try:
        apply_control_updates(device, updates)
    except RuntimeError:
        pass


def restore_controls(device: str, orig: dict[str, int]) -> None:
    if not orig:
        return
    try:
        apply_control_updates(device, orig)
    except RuntimeError:
        pass


def record_blink_clip(
    device: str,
    outdir: Path,
    width: int,
    height: int,
    fps: int,
    warmup_s: float,
    duration_s: float,
) -> Path:
    """ffmpeg v4l2 capture used by measure_blink.sh, then the device is released."""
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / "capture.log"
    video = outdir / "clip.mkv"
    total = warmup_s + duration_s + 2.0
    orig = current_values(list_device_controls(device))
    _v4l2_silent(
        device,
        [f"--set-fmt-video=width={width},height={height},pixelformat=MJPG"],
    )
    _v4l2_silent(device, [f"--set-parm={fps}"])
    lock_exposure_for_measure(device, orig)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f", "v4l2",
        "-thread_queue_size", "512",
        "-video_size", f"{width}x{height}",
        "-framerate", str(fps),
        "-input_format", "mjpeg",
        "-use_wallclock_as_timestamps", "1",
        "-i", device,
        "-t", f"{total:.1f}",
        "-c:v", "copy",
        str(video),
    ]
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(f"device={device} {width}x{height} fps={fps} warmup={warmup_s} duration={duration_s}\n")
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        try:
            time.sleep(2.0)
            lock_exposure_for_measure(device, orig)
            timeout = total + 20.0
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"ffmpeg blink capture timed out after {timeout:.0f}s") from None
        finally:
            restore_controls(device, orig)
    if proc.returncode != 0 or not video.is_file() or video.stat().st_size == 0:
        detail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError(f"ffmpeg blink capture failed (exit {proc.returncode}): {detail}")
    return video


def analyze_blink_clip(
    video: Path,
    outdir: Path,
    warmup_s: float,
    roi: str | None,
) -> dict[str, Any]:
    if not ANALYZE_SCRIPT.is_file():
        raise RuntimeError(f"missing analyzer {ANALYZE_SCRIPT}")
    cmd = [
        ANALYZE_PYTHON,
        str(ANALYZE_SCRIPT),
        "--video", str(video),
        "--outdir", str(outdir),
        "--warmup", str(warmup_s),
    ]
    if roi:
        cmd.extend(["--roi", roi])
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=120.0,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{ANALYZE_PYTHON} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("analyze_blink.py timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"analyze_blink.py failed: {detail}") from exc
    json_path = outdir / "result.json"
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return json.loads(proc.stdout)


@mcp.tool()
def measure_blink(
    duration: float = 25.0,
    warmup: float = 8.0,
    roi: str | None = None,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    fps: int = 30,
) -> list:
    """Record the FPGA LED and measure blink rate (edge/threshold AND FFT).

    Same capture path as tools/measure_blink.sh (kept): ffmpeg v4l2 clip,
    freeze AE, analyze with /usr/bin/python3. Returns both frequencies, which
    method is trusted (FFT when the edge detector undercounts, as at ~6.9 Hz),
    JSON path, and the brightness.png + roi.png graphs as images.

    duration/warmup are seconds (defaults 25 / 8). roi is optional: auto
    (default), full, top, bottom, nano4k (top), primer20k (bottom), or x,y,w,h.
    top/bottom prepare for two boards in one frame; this tool still meters
    one LED. Does not program the FPGA. tools/measure_blink.sh still exists.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if duration < 2 or duration > 60:
        raise ValueError("duration must be 2..60 seconds")
    if warmup < 0 or warmup > 30:
        raise ValueError("warmup must be 0..30 seconds")
    if fps < 5 or fps > 60:
        raise ValueError("fps must be 5..60")
    parse_roi_arg(roi)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BLINK_DIR / f"{stamp}-mcp"
    BLINK_DIR.mkdir(parents=True, exist_ok=True)
    with camera_lock():
        prepare_device(device)
        video = record_blink_clip(device, outdir, width, height, fps, warmup, duration)
    result = analyze_blink_clip(video, outdir, warmup, roi)
    plot = Path(result.get("paths", {}).get("plot") or (outdir / "brightness.png"))
    roi_png = Path(result.get("paths", {}).get("roi_frame") or (outdir / "roi.png"))
    edge = result.get("edge_frequency_hz")
    fft = result.get("fft_frequency_hz")
    trusted = result.get("trusted_method")
    freq = result.get("frequency_hz")
    pred = (result.get("predicted_blink3") or {}).get("frequency_hz")
    summary = {
        "frequency_hz": freq,
        "edge_frequency_hz": edge,
        "fft_frequency_hz": fft,
        "fft_snr": result.get("fft_snr"),
        "trusted_method": trusted,
        "trusted_reason": result.get("trusted_reason"),
        "confidence": result.get("confidence"),
        "predicted_blink3_hz": pred,
        "error_pct_vs_blink3": result.get("error_pct_vs_blink3"),
        "roi": result.get("roi"),
        "duration_s": result.get("duration_s"),
        "fps": result.get("fps"),
        "warnings": result.get("warnings"),
        "paths": result.get("paths"),
        "video": result.get("video"),
    }
    text = (
        f"measure_blink trusted={trusted} {freq} Hz "
        f"(edge={edge} fft={fft}) predicted_blink3={pred} Hz\n"
        + json.dumps(summary, indent=2)
    )
    out: list = [text]
    if plot.is_file():
        out.append(Image(path=plot))
    if roi_png.is_file():
        out.append(Image(path=roi_png))
    return out


def _warmup_saved_controls() -> None:
    device = os.environ.get("WEBCAM_MCP_DEVICE", DEFAULT_DEVICE)
    if not DEVICE_RE.match(device) or not Path(device).exists():
        return
    try:
        with camera_lock():
            prepare_device(device)
    except Exception:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Webcam stills MCP server")
    parser.add_argument("--host", default=os.environ.get("WEBCAM_MCP_HOST", HOST_DEFAULT))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WEBCAM_MCP_PORT", PORT_DEFAULT)))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("webcam-mcp binds 127.0.0.1 only (refusing --host %s)" % args.host)
    host = "127.0.0.1" if args.host == "localhost" else args.host
    _warmup_saved_controls()
    mcp.run(transport="streamable-http", host=host, port=args.port)


if __name__ == "__main__":
    main()
