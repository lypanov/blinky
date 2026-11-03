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

DEVICE_RE = re.compile(r"^/dev/video\d+$")
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")

mcp = MCPServer(
    "webcam",
    instructions=(
        "Take still JPEGs from V4L2 cameras on this machine (Bee). "
        "Today the Logitech is /dev/video0; an HDMI capture stick will show up "
        "as another /dev/videoN. Call list_cameras if you are unsure. "
        "Does not touch the FPGA or serial ports."
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


def still_path(device: str, suffix: str = "") -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(device).name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    extra = f"-{suffix}" if suffix else ""
    path = CAPTURE_DIR / f"{stamp}-{stem}{extra}.jpg"
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = CAPTURE_DIR / f"{stamp}-{stem}{extra}.jpg"
    return path


def grab_still(device: str, out: Path, width: int, height: int, warmup_frames: int) -> None:
    """Grab one JPEG, then return so the V4L2 device is released."""
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
        raise RuntimeError("ffmpeg timed out; camera should be free again") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"ffmpeg failed: {detail}") from exc
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg wrote no image to {out}")


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
) -> list:
    """Capture one JPEG still.

    Returns the image for the model to look at, plus the saved path under
    ~/fpga/captures/. Releases the camera as soon as ffmpeg exits.
    warmup_frames discards the first N frames (auto-exposure); 0 matches
    tools/webcam_still.sh.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    out = still_path(device)
    with camera_lock():
        grab_still(device, out, width, height, warmup_frames)
    return [f"Saved to {out}", Image(path=out)]


@mcp.tool()
def capture_burst(
    n: int = 3,
    interval_s: float = 0.5,
    device: str = DEFAULT_DEVICE,
    resolution: str | None = None,
    warmup_frames: int = 8,
) -> list[str]:
    """Capture N stills, sleeping interval_s between shots. Paths only.

    Each shot opens then releases the camera, so other scripts can use it
    between frames. The lock is held only for the duration of each shot.
    """
    device = parse_device(device)
    width, height = parse_size(resolution)
    if n < 1 or n > 30:
        raise ValueError("n must be 1..30")
    if interval_s < 0 or interval_s > 30:
        raise ValueError("interval_s must be 0..30")
    if warmup_frames < 0 or warmup_frames > 60:
        raise ValueError("warmup_frames must be 0..60")
    paths: list[str] = []
    for i in range(n):
        out = still_path(device, suffix=f"{i:02d}")
        with camera_lock():
            grab_still(device, out, width, height, warmup_frames)
        paths.append(str(out))
        if i + 1 < n and interval_s:
            time.sleep(interval_s)
    return paths


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
