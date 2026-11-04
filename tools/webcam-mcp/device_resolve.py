"""Pick the Logitech QuickCam out of several V4L2 nodes.

The HDMI capture stick and the webcam swap /dev/videoN when USB order
changes. Board tools follow USB id 046d:0991, not a fixed device node.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

LOGITECH_USB = "046d:0991"
LOGITECH_USB_TOKEN = "046d_0991"
AUTO_NAMES = {"", "auto", "logitech", "webcam"}
DEVICE_RE = re.compile(r"^/dev/video\d+$")


def logitech_from_by_id(directory: Path) -> str | None:
    """Resolve the capture node (video-index0), not the metadata node."""
    if not directory.is_dir():
        return None
    hits = sorted(
        p for p in directory.iterdir()
        if p.is_symlink() and LOGITECH_USB_TOKEN in p.name and p.name.endswith("video-index0")
    )
    if not hits:
        return None
    return str(hits[0].resolve())


def pick_logitech(entries: list[tuple[str, str]]) -> str | None:
    """Choose the lowest /dev/videoN whose kernel name is the QuickCam.

    entries are (device path, kernel name) in any order. UVC exposes a second
    metadata node with the same name; the capture node is the lower number
    and is what by-id calls video-index0.
    """
    found: list[tuple[int, str]] = []
    for device, name in entries:
        if LOGITECH_USB not in name and LOGITECH_USB_TOKEN not in name:
            continue
        match = DEVICE_RE.match(device)
        if not match:
            continue
        found.append((int(device.removeprefix("/dev/video")), device))
    if not found:
        return None
    found.sort()
    return found[0][1]


def logitech_video_device() -> str | None:
    by_id = Path("/dev/v4l/by-id")
    found = logitech_from_by_id(by_id)
    if found and Path(found).exists():
        return found
    root = Path("/sys/class/video4linux")
    if not root.is_dir():
        return None
    entries: list[tuple[str, str]] = []
    for node in root.glob("video*"):
        name_file = node / "name"
        name = name_file.read_text(encoding="utf-8").strip() if name_file.is_file() else ""
        entries.append((f"/dev/{node.name}", name))
    return pick_logitech(entries)


def resolve_device_name(device: str | None, lookup=logitech_video_device) -> str:
    """Map 'auto' to the QuickCam. Explicit /dev/videoN is left alone."""
    text = (device or "auto").strip()
    if text.lower() in AUTO_NAMES:
        found = lookup()
        if not found:
            raise RuntimeError(
                "Logitech QuickCam 046d:0991 is not attached. "
                "Call list_cameras. /dev/video0 may be the HDMI capture stick, "
                "which has no auto_exposure control."
            )
        return found
    if not DEVICE_RE.match(text):
        raise ValueError(f"device must look like /dev/video0 or auto, not {device!r}")
    return text


def env_default_device() -> str:
    return os.environ.get("WEBCAM_MCP_DEVICE", "auto")
