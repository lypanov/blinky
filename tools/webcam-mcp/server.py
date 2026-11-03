#!/usr/bin/env python3
"""Local webcam stills for Cursor agents (streamable HTTP MCP).

Same capture approach as tools/webcam_still.sh: ffmpeg -f v4l2, one JPEG,
then drop the device so scripts like tools/measure_blink.sh can use it.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver import Image

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 8766
CAPTURE_DIR = Path(os.environ.get("WEBCAM_MCP_CAPTURE_DIR", Path.home() / "fpga" / "captures"))
DEFAULT_DEVICE = os.environ.get("WEBCAM_MCP_DEVICE", "/dev/video0")
DEFAULT_SIZE = "640x480"
LOCK_TIMEOUT_S = 30.0
FFMPEG_TIMEOUT_S = 25.0
# Same look Alex liked on the HDMI-monitor stills. Applied only to the
# MCP stills, never to tools/measure_blink.sh (that path stays raw).
ENHANCE_VF = "eq=brightness=0.25:contrast=1.6:gamma=1.8"

DEVICE_RE = re.compile(r"^/dev/video\d+$")
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")

mcp = MCPServer(
    "webcam",
    instructions=(
        "Take still JPEGs from V4L2 cameras on this machine (Bee). "
        "Today the Logitech is /dev/video0; an HDMI capture stick will show up "
        "as another /dev/videoN. Call list_cameras if you are unsure. "
        "Does not touch the FPGA or serial ports. "
        "capture_still returns a brightened JPEG by default "
        f"(ffmpeg -vf {ENHANCE_VF!r}); pass enhance=false for the raw frame. "
        "Both files are saved under ~/fpga/captures/."
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
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffmpeg {what} timed out") from exc
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


def enhance_still(src: Path, dst: Path) -> None:
    """Brighten a saved JPEG. Does not open the camera."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-i", str(src),
        "-vf", ENHANCE_VF,
        str(dst),
    ]
    run_ffmpeg(cmd, "enhance")
    if not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg wrote no enhanced image to {dst}")


def capture_raw_and_enhanced(
    device: str,
    width: int,
    height: int,
    warmup_frames: int,
    suffix: str = "",
) -> tuple[Path, Path]:
    raw, enhanced = still_paths(device, suffix=suffix)
    with camera_lock():
        grab_still(device, raw, width, height, warmup_frames)
    enhance_still(raw, enhanced)
    return raw, enhanced


@mcp.tool()
def list_cameras() -> list[dict[str, str]]:
    """List V4L2 /dev/videoN devices and their kernel names.

    Does not open the camera. The Logitech QuickCam is usually /dev/video0
    (a matching /dev/video1 is often a metadata node and will fail capture).
    A later HDMI capture stick will appear as another named UVC device.
    """
    return list_v4l_cameras()


@mcp.tool()
def capture_still(
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    enhance: bool = True,
) -> list:
    """Capture one JPEG still.

    Returns the image for the model to look at, plus saved paths under
    ~/fpga/captures/. enhance=true (default) returns the brightened frame
    (eq=brightness=0.25:contrast=1.6:gamma=1.8); enhance=false returns the
    raw frame. Both the -raw.jpg and -enhanced.jpg files are always written.
    Releases the camera as soon as the raw grab finishes.
    warmup_frames discards the first N frames (auto-exposure); 0 matches
    tools/webcam_still.sh.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    raw, enhanced = capture_raw_and_enhanced(device, width, height, warmup_frames)
    shown = enhanced if enhance else raw
    return [
        f"Saved raw to {raw}\nSaved enhanced to {enhanced}",
        Image(path=shown),
    ]


@mcp.tool()
def capture_burst(
    n: int = 3,
    interval_s: float = 0.5,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
    enhance: bool = True,
) -> list[dict[str, str]]:
    """Capture N stills, sleeping interval_s between shots. Paths only.

    Each shot writes both -raw.jpg and -enhanced.jpg. The `path` field is
    the enhanced file by default, or the raw file when enhance=false.
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
        raw, enhanced = capture_raw_and_enhanced(
            device, width, height, warmup_frames, suffix=f"{i:02d}"
        )
        shown = enhanced if enhance else raw
        shots.append({"path": str(shown), "raw": str(raw), "enhanced": str(enhanced)})
        if i + 1 < n and interval_s:
            time.sleep(interval_s)
    return shots


def main() -> None:
    parser = argparse.ArgumentParser(description="Webcam stills MCP server")
    parser.add_argument("--host", default=os.environ.get("WEBCAM_MCP_HOST", HOST_DEFAULT))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WEBCAM_MCP_PORT", PORT_DEFAULT)))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("webcam-mcp binds 127.0.0.1 only (refusing --host %s)" % args.host)
    host = "127.0.0.1" if args.host == "localhost" else args.host
    mcp.run(transport="streamable-http", host=host, port=args.port)


if __name__ == "__main__":
    main()
