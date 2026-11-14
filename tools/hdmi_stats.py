#!/usr/bin/env python3
"""Print luma stats from a YUYV grab on the HDMI capture card.

Do not convert YUYV to RGB to judge the picture. White is luma 255.
A locked grey Dock field with luma about 139 and U=V=128 is not armed.
See docs/load-boards.md.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEVICE = "/dev/video0"
SIZES = {
    "nano": (720, 480),
    "4k": (720, 480),
    "dock": (1024, 768),
    "20k": (1024, 768),
}


def grab(device: str, width: int, height: int, frames: int, dest: Path) -> None:
    fmt = subprocess.run(
        [
            "v4l2-ctl",
            "-d",
            device,
            f"--set-fmt-video=width={width},height={height},pixelformat=YUYV",
        ],
        capture_output=True,
        text=True,
    )
    if fmt.returncode != 0:
        sys.exit(fmt.stderr or "v4l2-ctl failed")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "v4l2",
        "-input_format",
        "yuyv422",
        "-video_size",
        f"{width}x{height}",
        "-i",
        device,
        "-vframes",
        str(frames),
        "-f",
        "rawvideo",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(proc.stderr or "ffmpeg grab failed")


def stats(raw: bytes, width: int, height: int) -> None:
    frame = width * height * 2
    if len(raw) < frame:
        sys.exit(f"grab is {len(raw)} bytes, need {frame} for one {width}x{height} frame")
    n = len(raw) // frame
    print(f"frames {n} size {width}x{height} bytes {len(raw)}")
    for i in range(n):
        pix = raw[i * frame : (i + 1) * frame]
        y = pix[0::2]
        u = pix[1::4]
        v = pix[3::4]
        bright = sum(1 for b in y if b >= 200)
        print(
            f"frame {i}: luma min {min(y)} mean {sum(y) / len(y):.1f} "
            f"max {max(y)} pixels>=200 {bright} "
            f"U mean {sum(u) / len(u):.1f} V mean {sum(v) / len(v):.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--device", default=DEVICE)
    parser.add_argument(
        "--board",
        choices=sorted(SIZES),
        help="nano/4k is 720x480, dock/20k is 1024x768",
    )
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--file", type=Path, help="existing .yuyv instead of grabbing")
    parser.add_argument("--out", type=Path, help="where to write a new grab")
    args = parser.parse_args()
    if args.board:
        width, height = SIZES[args.board]
    elif args.width and args.height:
        width, height = args.width, args.height
    else:
        parser.error("pass --board nano|dock or --width and --height")
    if args.file:
        stats(args.file.read_bytes(), width, height)
        return 0
    dest = args.out or Path("/tmp/blinky-hdmi.yuyv")
    grab(args.device, width, height, args.frames, dest)
    stats(dest.read_bytes(), width, height)
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
