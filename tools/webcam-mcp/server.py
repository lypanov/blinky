#!/usr/bin/env python3
"""Local webcam capture and V4L2 controls for Cursor agents (streamable HTTP MCP).

capture_still: one JPEG then drop the device (tools/webcam_still.sh).
capture_burst: N JPEGs from one open camera.
capture_video: one continuous ffmpeg v4l2 clip from one open camera.
measure_blink records via capture_video (or analyzes a clip path it returned).
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
    list_device_controls,
    load_saved_controls,
    resolve_updates,
    save_device_controls,
    state_path,
)

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from blink_trust import named_board, parse_roi_arg  # noqa: E402

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 8766
CAPTURE_DIR = Path(os.environ.get("WEBCAM_MCP_CAPTURE_DIR", Path.home() / "fpga" / "captures"))
DEFAULT_DEVICE = os.environ.get("WEBCAM_MCP_DEVICE", "/dev/video0")
DEFAULT_SIZE = "640x480"
LOCK_TIMEOUT_S = 120.0
FFMPEG_TIMEOUT_S = 25.0
ANALYZE_PYTHON = os.environ.get("WEBCAM_MCP_ANALYZE_PYTHON", "/usr/bin/python3")
ANALYZE_SCRIPT = Path(__file__).resolve().parent.parent / "analyze_blink.py"
LED_DETECT_SCRIPT = Path(__file__).resolve().parent.parent / "led_detect.py"
BLINK_DIR = Path(os.environ.get("WEBCAM_MCP_BLINK_DIR", Path.home() / "fpga" / "blink-measure"))
AUTO_ADJUST_MAX_ITERS = 10
# LED-priority profile: dark background, unclipped coloured cores, manual WB.
# Mean luma is not the target (that washed the Logitech and bloomed the LEDs).
#
# Bee's QuickCam Pro (046d:0991) delivers fps ≈ exposure_time_absolute/10
# until it caps at 30. Short shutter (50–110) looks great on a still but
# records ~6 fps, which aliases Blink3's 3.43 Hz to ~2.56 Hz. Keep exposure
# >= 250 so MJPEG copy actually runs at 25–30 fps.
LED_PROFILE = {
    "auto_exposure": 1,
    "white_balance_automatic": 0,
    "white_balance_temperature": 4000,
    "brightness": 128,
    "contrast": 40,
    "saturation": 64,
    "backlight_compensation": 0,
    "exposure_dynamic_framerate": 0,
}
LED_GAIN_EXP = [
    (48, 300),
    (64, 300),
    (80, 300),
    (40, 300),
    (96, 300),
    (32, 300),
    (112, 300),
]
# gain 16 is only tried when cores are already too bright (see auto_adjust).
LED_GAIN_LOW = (16, 300)
AUTO_ADJUST_HYSTERESIS = 12.0
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
        "exposure/white_balance) or auto_adjust. auto_adjust exposes for LED "
        "blobs (colour, compactness, no bloom) — not mean luma — and sets "
        "manual white balance/saturation so orange vs red is visible. "
        "detect_leds records a short clip, classifies each LED as blinking or "
        "steady, and assigns boards from geometry+colour (nano4k = two LEDs, "
        "primer20k = three, orange vs red). measure_blink(roi=nano4k|primer20k) "
        "uses those detected positions. roi may also be auto, top, bottom, or "
        "x,y,w,h. Does not touch the FPGA or serial ports. Stills/clips go "
        "under ~/fpga/captures/; blink runs under ~/fpga/blink-measure/."
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
        "-input_format", "mjpeg",
        "-video_size", f"{width}x{height}",
        "-framerate", "30",
        "-i", device,
        "-frames:v", str(frames),
        "-update", "1",
        str(out),
    ]
    run_ffmpeg(cmd, "capture")
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg wrote no image to {out}")


def grab_burst(
    device: str,
    width: int,
    height: int,
    n: int,
    interval_s: float,
    warmup_frames: int,
    fps: int = 30,
) -> list[Path]:
    """One V4L2 open: skip warmup once, then n JPEGs at interval_s. Camera stays open."""
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = Path(device).name
    tmp = CAPTURE_DIR / f".burst-{stamp}"
    tmp.mkdir(parents=True, exist_ok=True)
    pattern = tmp / "%02d.jpg"
    out_fps = (1.0 / interval_s) if interval_s > 0 else float(max(fps, 1))
    vf = f"select='gte(n,{max(0, warmup_frames)})',setpts=N/FRAME_RATE/TB,fps={out_fps:.6f}"
    timeout = max(FFMPEG_TIMEOUT_S, warmup_frames / max(fps, 1) + n * max(interval_s, 1.0 / max(fps, 1)) + 15.0)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-f", "v4l2",
        "-video_size", f"{width}x{height}",
        "-framerate", str(fps),
        "-i", device,
        "-vf", vf,
        "-frames:v", str(n),
        "-q:v", "3",
        str(pattern),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
        files = sorted(tmp.glob("*.jpg"))
        if len(files) != n:
            raise RuntimeError(f"ffmpeg burst wrote {len(files)} JPEGs, expected {n}")
        outs: list[Path] = []
        for i, src in enumerate(files):
            dest = CAPTURE_DIR / f"{stamp}-{stem}-{i:02d}-raw.jpg"
            if dest.exists():
                dest = CAPTURE_DIR / f"{stamp}-{stem}-{i:02d}-{datetime.now().strftime('%f')}-raw.jpg"
            src.replace(dest)
            outs.append(dest)
        return outs
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffmpeg burst timed out after {timeout:.0f}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"ffmpeg burst failed: {detail}") from exc
    finally:
        for leftover in tmp.glob("*"):
            leftover.unlink(missing_ok=True)
        try:
            tmp.rmdir()
        except OSError:
            pass


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
    """Capture N stills from one open camera. Paths only.

    Opens /dev/videoN once (not once per frame — a 12-shot 0.2s burst used
    to take 2–4s per reopen). warmup_frames are discarded at the start, then
    n JPEGs are taken at interval_s. Each shot writes -raw.jpg; -enhanced.jpg
    only when enhance=true. The `path` field is the file returned to the model.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if n < 1 or n > 30:
        raise ValueError("n must be 1..30")
    if interval_s < 0 or interval_s > 30:
        raise ValueError("interval_s must be 0..30")
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    with camera_lock():
        prepare_device(device)
        raws = grab_burst(device, width, height, n, interval_s, warmup_frames)
    shots: list[dict[str, str]] = []
    for raw in raws:
        enhanced = maybe_enhance(raw, enhance, enhance_vf)
        shown = enhanced if enhanced is not None else raw
        shot = {"path": str(shown), "raw": str(raw)}
        if enhanced is not None:
            shot["enhanced"] = str(enhanced)
        shots.append(shot)
    return shots


@mcp.tool()
def capture_video(
    duration: float = 10.0,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    fps: int = 30,
    lock_exposure: bool = False,
) -> dict[str, Any]:
    """Record a continuous clip from one open camera. Path only, no stills.

    One ffmpeg v4l2 session for `duration` seconds (not a burst of JPEGs).
    Writes an MJPEG .mkv under ~/fpga/captures/. lock_exposure=true freezes
    AE/gain like tools/measure_blink.sh (stable fps); default false leaves
    current controls. measure_blink uses this recorder (or pass the returned
    path as measure_blink(video=...)).
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if duration < 1 or duration > 90:
        raise ValueError("duration must be 1..90 seconds")
    if fps < 5 or fps > 60:
        raise ValueError("fps must be 5..60")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = CAPTURE_DIR / f"{stamp}-{Path(device).name}.mkv"
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    with camera_lock():
        prepare_device(device)
        return record_continuous_clip(
            device, dest, width, height, fps, duration, lock_exposure=lock_exposure
        )


def led_cache_path() -> Path:
    return state_path().parent / "leds.json"


def load_led_cache() -> dict[str, Any] | None:
    path = led_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_led_cache(data: dict[str, Any]) -> Path:
    path = led_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def run_led_detect_jpeg(path: Path) -> dict[str, Any]:
    if not LED_DETECT_SCRIPT.is_file():
        raise RuntimeError(f"missing {LED_DETECT_SCRIPT}")
    proc = subprocess.run(
        [ANALYZE_PYTHON, str(LED_DETECT_SCRIPT), "--jpeg", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    return json.loads(proc.stdout)


def resolve_detected_roi(board: str, detection: dict[str, Any]) -> str | None:
    info = (detection.get("boards") or {}).get(board)
    if not info:
        return None
    roi = info.get("measure_roi")
    if not roi:
        return None
    return f"{int(roi['x'])},{int(roi['y'])},{int(roi['w'])},{int(roi['h'])}"


def run_led_detect_video(video: Path, annotated: Path, json_path: Path) -> dict[str, Any]:
    if not LED_DETECT_SCRIPT.is_file():
        raise RuntimeError(f"missing {LED_DETECT_SCRIPT}")
    annotated.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ANALYZE_PYTHON,
        str(LED_DETECT_SCRIPT),
        "--video", str(video),
        "--annotate", str(annotated),
        "--json", str(json_path),
        "--max-frames", "240",
    ]
    try:
        proc = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=90.0
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"led_detect.py failed: {detail}") from exc
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return json.loads(proc.stdout)


def _knob_snapshot(values: dict[str, int]) -> dict[str, int]:
    keys = (
        "brightness",
        "contrast",
        "saturation",
        "gain",
        "auto_exposure",
        "exposure_time_absolute",
        "white_balance_automatic",
        "white_balance_temperature",
        "backlight_compensation",
        "exposure_dynamic_framerate",
    )
    return {name: values[name] for name in keys if name in values}


@mcp.tool()
def auto_adjust(
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    max_iters: int = AUTO_ADJUST_MAX_ITERS,
    target_mean: float = TARGET_MEAN,
) -> list:
    """Expose so FPGA LEDs are distinct, unclipped, and coloured.

    Does **not** target mean luma (that washed Bee's Logitech and bloomed
    the LEDs). Applies a manual AE/AWB LED profile, then searches gain and
    shutter for compact red/orange blobs with orange-vs-red hue remaining.
    target_mean is ignored (kept so old callers do not break). Persists the
    knobs. Returns before and after JPEGs.
    """
    del target_mean
    device = parse_device(device)
    width, height = parse_size(resolution)
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    if max_iters < 1 or max_iters > 20:
        raise ValueError("max_iters must be 1..20")

    history: list[dict[str, Any]] = []
    before: Path | None = None
    best_path: Path | None = None
    best_score = -1e9
    best_ctrls: dict[str, int] = {}
    with camera_lock():
        prepare_device(device)
        before, _ = still_paths(device, suffix="auto-before")
        grab_still(device, before, width, height, warmup_frames)
        before_metrics = run_led_detect_jpeg(before)
        history.append(
            {
                "iter": "before",
                "path": str(before),
                "metrics": {k: v for k, v in before_metrics.items() if k != "blobs"},
                "values": _knob_snapshot(current_values(list_device_controls(device))),
            }
        )

        apply_control_updates(device, dict(LED_PROFILE))
        saved = load_saved_controls().get(device, {})
        candidates: list[dict[str, int]] = []
        seen_gain_exp: set[tuple[int, int]] = set()

        def add_cand(gain: int, exp: int, extra: dict[str, int] | None = None) -> None:
            key = (int(gain), int(exp))
            if extra is None and key in seen_gain_exp:
                return
            if extra is None:
                seen_gain_exp.add(key)
            cand = dict(LED_PROFILE)
            cand["gain"] = int(gain)
            cand["exposure_time_absolute"] = int(exp)
            if extra:
                cand.update(extra)
            candidates.append(cand)

        # Score the persisted knobs first so close ties keep a stable setting.
        if isinstance(saved.get("gain"), int) and isinstance(
            saved.get("exposure_time_absolute"), int
        ):
            extra = {}
            if isinstance(saved.get("saturation"), int):
                extra["saturation"] = saved["saturation"]
            if isinstance(saved.get("white_balance_temperature"), int):
                extra["white_balance_temperature"] = saved["white_balance_temperature"]
            add_cand(saved["gain"], saved["exposure_time_absolute"], extra or None)
        for gain, exp in LED_GAIN_EXP:
            add_cand(gain, exp)
        extra_wb_sat = [
            {"white_balance_temperature": 3200},
            {"white_balance_temperature": 3800, "saturation": 80},
            {"saturation": 80},
            {"saturation": 48, "white_balance_temperature": 3800},
        ]

        def capture_scored(label: str, warmup: int) -> dict[str, Any]:
            nonlocal best_score, best_path, best_ctrls
            raw, _ = still_paths(device, suffix=label)
            grab_still(device, raw, width, height, warmup)
            metrics = run_led_detect_jpeg(raw)
            values = _knob_snapshot(current_values(list_device_controls(device)))
            step = {
                "iter": label,
                "path": str(raw),
                "score": metrics.get("score"),
                "metrics": {k: v for k, v in metrics.items() if k != "blobs"},
                "values": values,
                "n_blobs": metrics.get("n_blobs"),
                "has_orange": metrics.get("has_orange"),
                "has_red": metrics.get("has_red"),
            }
            history.append(step)
            score = float(metrics.get("score") or -1e9)
            if score > best_score:
                best_score = score
                best_path = raw
                best_ctrls = dict(values)
            return step

        n_main = min(len(candidates), max(1, max_iters - 1))
        for i, cand in enumerate(candidates[:n_main]):
            apply_control_updates(device, cand)
            capture_scored(f"auto{i:02d}", 6 if i else warmup_frames)

        # Only hunt WB/sat when orange vs red is missing. Otherwise the
        # extras tie on score and flip 3200/4000 every call.
        remaining = max_iters - (len(history) - 1)
        both_colours = bool(best_ctrls) and any(
            s.get("has_red") and s.get("has_orange") for s in history if s.get("path") == str(best_path)
        )
        if remaining > 0 and best_ctrls and not both_colours:
            variants = extra_wb_sat[:remaining]
            for j, extra in enumerate(variants):
                cand = dict(LED_PROFILE)
                cand["gain"] = best_ctrls.get("gain", 48)
                cand["exposure_time_absolute"] = best_ctrls.get(
                    "exposure_time_absolute", 300
                )
                cand.update(extra)
                apply_control_updates(device, cand)
                capture_scored(f"autowb{j:02d}", 6)
        elif remaining > 0 and best_ctrls:
            best_metrics = next(
                (s.get("metrics") or {} for s in reversed(history) if s.get("path") == str(best_path)),
                {},
            )
            med_peak = float(best_metrics.get("med_peak") or 0)
            if med_peak >= 220:
                add_low = dict(LED_PROFILE)
                add_low["gain"] = LED_GAIN_LOW[0]
                add_low["exposure_time_absolute"] = LED_GAIN_LOW[1]
                apply_control_updates(device, add_low)
                capture_scored("auto-low", 6)

        # Hysteresis: keep the persisted gain/exp if it is within a few
        # score points of the winner so falling light does not chatter.
        saved_gain = saved.get("gain")
        saved_exp = saved.get("exposure_time_absolute")
        if isinstance(saved_gain, int) and isinstance(saved_exp, int) and history:
            saved_steps = [
                s
                for s in history
                if (s.get("values") or {}).get("gain") == saved_gain
                and abs(int((s.get("values") or {}).get("exposure_time_absolute") or 0) - saved_exp) <= 15
            ]
            if saved_steps:
                saved_best = max(saved_steps, key=lambda s: float(s.get("score") or -1e9))
                saved_score = float(saved_best.get("score") or -1e9)
                if best_score - saved_score <= AUTO_ADJUST_HYSTERESIS:
                    best_score = saved_score
                    best_path = Path(saved_best["path"]) if saved_best.get("path") else best_path
                    best_ctrls = dict(saved_best.get("values") or best_ctrls)

        if best_ctrls:
            apply_control_updates(device, best_ctrls)
            last_values = current_values(list_device_controls(device))
            persist_keys = set(LED_PROFILE) | {"gain", "exposure_time_absolute"}
            merge_persist(device, {k: last_values[k] for k in persist_keys if k in last_values})
        else:
            last_values = current_values(list_device_controls(device))

    assert before is not None
    after = best_path or before
    after_step = next((s for s in reversed(history) if s.get("path") == str(after)), history[-1])
    knobs = after_step.get("values") or _knob_snapshot(last_values)
    summary = {
        "score": after_step.get("score"),
        "n_blobs": after_step.get("n_blobs"),
        "has_red": after_step.get("has_red"),
        "has_orange": after_step.get("has_orange"),
        "metrics": after_step.get("metrics"),
        "values": knobs,
        "before": str(before),
        "after": str(after),
        "history": [
            {k: v for k, v in step.items() if k != "metrics"} | {"metrics_score": (step.get("metrics") or {}).get("score")}
            for step in history
        ],
    }
    text = (
        f"auto_adjust LED-priority score={summary['score']} "
        f"n_blobs={summary['n_blobs']} red={summary['has_red']} "
        f"orange={summary['has_orange']} values={knobs}\n"
        f"before={before}\nafter={after}\n"
        + json.dumps({k: v for k, v in summary.items() if k != "history"}, indent=2)
    )
    return [text, Image(path=before), Image(path=after)]


@mcp.tool()
def detect_leds(
    duration: float = 4.0,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    fps: int = 30,
    video: str | None = None,
) -> list:
    """Find LED blobs, classify blinking vs steady, assign nano4k / primer20k.

    Records a short clip (or analyzes a capture_video path). Uses LED
    geometry and colour (orange vs red) — not USB cords. Returns JSON
    (coordinates, colour, state, board) plus an annotated debug image.
    measure_blink(roi=nano4k|primer20k) uses the detected measure ROI.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if duration < 1 or duration > 20:
        raise ValueError("duration must be 1..20 seconds")
    if fps < 5 or fps > 60:
        raise ValueError("fps must be 5..60")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BLINK_DIR / f"{stamp}-leds"
    outdir.mkdir(parents=True, exist_ok=True)
    rec: dict[str, Any] | None = None
    if video:
        clip = parse_video_path(video)
    else:
        dest = outdir / "clip.mkv"
        with camera_lock():
            prepare_device(device)
            rec = record_continuous_clip(
                device, dest, width, height, fps, duration, lock_exposure=True
            )
        clip = Path(rec["path"])
    annotated = outdir / "annotated.jpg"
    json_path = outdir / "leds.json"
    result = run_led_detect_video(clip, annotated, json_path)
    result["capture"] = rec
    result["annotated"] = str(annotated)
    result["json"] = str(json_path)
    save_led_cache(result)
    n = len(result.get("leds") or [])
    boards = list((result.get("boards") or {}).keys())
    text = (
        f"detect_leds n={n} boards={boards} reason={result.get('assign_reason')}\n"
        + json.dumps({k: v for k, v in result.items() if k != "capture"}, indent=2)
    )
    out: list = [text]
    if annotated.is_file():
        out.append(Image(path=annotated))
    return out


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


def count_clip_frames(path: Path) -> int | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-count_frames",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames",
                "-of", "csv=p=0",
                str(path),
            ],
            text=True,
            timeout=30.0,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    token = (out or "").strip().split(",")[0].strip()
    if not token or token in {"N/A", "0"}:
        return None
    try:
        return int(token)
    except ValueError:
        return None


def record_continuous_clip(
    device: str,
    dest: Path,
    width: int,
    height: int,
    fps: int,
    duration_s: float,
    *,
    lock_exposure: bool = False,
) -> dict[str, Any]:
    """One V4L2 open, one ffmpeg -t clip. Shared by capture_video and measure_blink."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    log = dest.with_suffix(".log")
    orig: dict[str, int] = {}
    _v4l2_silent(
        device,
        [f"--set-fmt-video=width={width},height={height},pixelformat=MJPG"],
    )
    _v4l2_silent(device, [f"--set-parm={fps}"])
    if lock_exposure:
        orig = current_values(list_device_controls(device))
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
        "-t", f"{duration_s:.1f}",
        "-c:v", "copy",
        str(dest),
    ]
    start = time.monotonic()
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(
            f"device={device} {width}x{height} fps={fps} duration={duration_s} "
            f"lock_exposure={lock_exposure}\n"
        )
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        try:
            if lock_exposure:
                time.sleep(min(2.0, max(0.2, duration_s / 4)))
                lock_exposure_for_measure(device, orig)
            timeout = duration_s + 20.0
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"ffmpeg video capture timed out after {timeout:.0f}s") from None
        finally:
            if lock_exposure:
                restore_controls(device, orig)
    wall_s = time.monotonic() - start
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        detail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError(f"ffmpeg video capture failed (exit {proc.returncode}): {detail}")
    n_frames = count_clip_frames(dest)
    delivered_fps = None
    if n_frames and duration_s > 0:
        delivered_fps = round(n_frames / duration_s, 3)
    return {
        "path": str(dest),
        "log": str(log),
        "device": device,
        "duration_s": duration_s,
        "wall_s": round(wall_s, 3),
        "fps": fps,
        "delivered_fps": delivered_fps,
        "n_frames": n_frames,
        "width": width,
        "height": height,
        "lock_exposure": lock_exposure,
        "bytes": dest.stat().st_size,
    }


def parse_video_path(video: str) -> Path:
    path = Path(video).expanduser().resolve()
    allowed = (CAPTURE_DIR.resolve(), BLINK_DIR.resolve())
    if not any(path == root or root in path.parents for root in allowed):
        raise ValueError(f"video must be under {CAPTURE_DIR} or {BLINK_DIR}")
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist. Call capture_video first.")
    return path


def analyze_blink_clip(
    video: Path,
    outdir: Path,
    warmup_s: float,
    roi: str | None,
    fps: float | None = None,
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
    if fps and fps >= 4:
        cmd.extend(["--fps", f"{fps:.4f}"])
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
    video: str | None = None,
) -> list:
    """Measure blink rate from capture_video (edge/threshold AND FFT).

    Records with the same continuous ffmpeg v4l2 session as capture_video
    (camera held open, AE frozen like tools/measure_blink.sh — not a burst of
    stills). Or pass video= to a clip path capture_video already returned.
    Returns both frequencies, which method is trusted (edge when it agrees
    with FFT; untrusted when they disagree — FFT leakage from the other
    board is not silently adopted). JSON path, and brightness.png + roi.png.
    duration/warmup are seconds (defaults 25 / 8). roi: auto, full, top,
    bottom, nano4k, primer20k, or x,y,w,h. nano4k/primer20k run LED
    detection on the clip and meter that board's blinking LED only (never a
    steady LED; ROI is clipped away from the other board). Falls back to
    top/bottom halves only if the board itself is missing. Does not program
    the FPGA. tools/measure_blink.sh still exists.
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
    board = named_board(roi)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = BLINK_DIR / f"{stamp}-mcp"
    outdir.mkdir(parents=True, exist_ok=True)
    rec: dict[str, Any] | None = None
    if video:
        clip = parse_video_path(video)
    else:
        dest = outdir / "clip.mkv"
        with camera_lock():
            prepare_device(device)
            rec = record_continuous_clip(
                device,
                dest,
                width,
                height,
                fps,
                warmup + duration + 2.0,
                lock_exposure=True,
            )
        clip = Path(rec["path"])
    detection: dict[str, Any] | None = None
    analyze_roi = roi
    annotated: Path | None = None
    result: dict[str, Any] | None = None
    if board:
        annotated = outdir / "leds-annotated.jpg"
        det_json = outdir / "leds.json"
        detection = run_led_detect_video(clip, annotated, det_json)
        save_led_cache(detection)
        xywh = resolve_detected_roi(board, detection)
        if xywh:
            analyze_roi = xywh
        elif (detection.get("boards") or {}).get(board):
            result = {
                "frequency_hz": None,
                "edge_frequency_hz": None,
                "fft_frequency_hz": None,
                "trusted_method": "untrusted",
                "trusted_reason": f"no blinking LED found on {board}",
                "confidence": 0.0,
                "warnings": [f"no blinking LED found on {board}; not metering a steady LED"],
                "paths": {},
            }
    delivered = None if rec is None else rec.get("delivered_fps")
    if result is None:
        result = analyze_blink_clip(clip, outdir, warmup, analyze_roi, fps=delivered)
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
        "roi_requested": roi,
        "board": board,
        "detected_roi": analyze_roi if board else None,
        "leds": None if detection is None else {
            "assign_reason": detection.get("assign_reason"),
            "boards": detection.get("boards"),
            "leds": detection.get("leds"),
            "annotated": str(annotated) if annotated else None,
        },
        "duration_s": result.get("duration_s"),
        "fps": result.get("fps"),
        "warnings": result.get("warnings"),
        "paths": result.get("paths"),
        "video": str(clip),
        "capture": rec,
    }
    text = (
        f"measure_blink trusted={trusted} {freq} Hz "
        f"(edge={edge} fft={fft}) predicted_blink3={pred} Hz "
        f"board={board} roi={analyze_roi}\n"
        + json.dumps(summary, indent=2)
    )
    out: list = [text]
    if annotated is not None and annotated.is_file():
        out.append(Image(path=annotated))
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
