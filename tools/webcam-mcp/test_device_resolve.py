#!/usr/bin/env python3
"""Logitech node selection. No camera."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from device_resolve import logitech_from_by_id, pick_logitech, resolve_device_name


class DeviceResolveTests(unittest.TestCase):
    def test_picks_lowest_quickcam_not_hdmi(self) -> None:
        entries = [
            ("/dev/video0", "UGREEN 15389: UGREEN 15389"),
            ("/dev/video1", "UGREEN 15389: UGREEN 15389"),
            ("/dev/video3", "UVC Camera (046d:0991)"),
            ("/dev/video2", "UVC Camera (046d:0991)"),
        ]
        self.assertEqual(pick_logitech(entries), "/dev/video2")

    def test_by_id_index0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real-video2"
            target.write_text("x", encoding="utf-8")
            link = root / "usb-046d_0991_9246131D-video-index0"
            link.symlink_to(target)
            (root / "usb-046d_0991_9246131D-video-index1").symlink_to(target)
            (root / "usb-MACROSILICON_UGREEN_15389_20230204-video-index0").symlink_to(target)
            self.assertEqual(logitech_from_by_id(root), str(target.resolve()))

    def test_auto_uses_lookup(self) -> None:
        self.assertEqual(resolve_device_name("auto", lambda: "/dev/video2"), "/dev/video2")
        self.assertEqual(resolve_device_name("/dev/video0", lambda: "/dev/video2"), "/dev/video0")
        with self.assertRaises(RuntimeError):
            resolve_device_name("auto", lambda: None)


if __name__ == "__main__":
    unittest.main()
