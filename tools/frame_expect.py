#!/usr/bin/env python3
"""Draw the picture a frame should hold, and compare it to a capture.

The capture is the video module's active pixels, taken before the HDMI
serializer. This draws the same picture from the mode and the count,
with the 8x8 font. Any difference fails. A deliberately wrong picture
must differ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from font8x8 import SQUARE, SQUARE_X, SQUARE_Y, active_white

W = 640
H = 480


def load_p5(path: Path) -> bytes:
    data = path.read_bytes()
    header = f"P5\n{W} {H}\n255\n".encode()
    if not data.startswith(header):
        raise SystemExit(f"{path} is not a {W}x{H} P5 image")
    body = data[len(header) :]
    if len(body) != W * H:
        raise SystemExit(f"{path} has {len(body)} pixels")
    return body


def draw(kind: str, count: int, square: bool, flash_white: bool, blank: bool) -> bytes:
    img = bytearray(W * H)
    if blank:
        return bytes(img)
    if kind == "flash":
        if flash_white:
            img = bytearray([255]) * (W * H)
        return bytes(img)
    if kind == "square":
        if square:
            for y in range(SQUARE_Y, SQUARE_Y + SQUARE):
                row = y * W
                for x in range(SQUARE_X, SQUARE_X + SQUARE):
                    img[row + x] = 255
        return bytes(img)
    if kind == "text":
        for x, y in active_white(count, square):
            if not (0 <= x < W and 0 <= y < H):
                raise SystemExit(f"glyph pixel {x},{y} outside the picture")
            img[y * W + x] = 255
        return bytes(img)
    raise SystemExit(f"kind {kind}")


def first_diff(got: bytes, exp: bytes) -> str:
    n = 0
    where = ""
    for i, (a, b) in enumerate(zip(got, exp)):
        if a != b:
            if not where:
                where = f"({i % W},{i // W}) got {a} want {b}"
            n += 1
    return f"{n} pixels, first {where}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--got", type=Path, required=True)
    p.add_argument("--kind", choices=("flash", "square", "text"), required=True)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--square", action="store_true")
    p.add_argument("--flash-white", action="store_true")
    p.add_argument("--blank", action="store_true")
    p.add_argument("--must-differ", action="store_true")
    args = p.parse_args()
    got = load_p5(args.got)
    exp = draw(args.kind, args.count, args.square, args.flash_white, args.blank)
    white = exp.count(255)
    same = got == exp
    if args.must_differ:
        if same:
            raise SystemExit(
                f"FAIL {args.got.name} matched the wrong picture ({white} white)"
            )
        print(f"ok differ {args.got.name} {first_diff(got, exp)}")
        return
    if not same:
        raise SystemExit(f"FAIL {args.got.name} {first_diff(got, exp)}")
    print(f"ok match {args.got.name} white {white}")


if __name__ == "__main__":
    main()
