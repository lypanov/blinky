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

def load_p5(path: Path, width: int, height: int) -> bytes:
    data = path.read_bytes()
    header = f"P5\n{width} {height}\n255\n".encode()
    if not data.startswith(header):
        raise SystemExit(f"{path} is not a {width}x{height} P5 image")
    body = data[len(header) :]
    if len(body) != width * height:
        raise SystemExit(f"{path} has {len(body)} pixels")
    return body


def draw(
    kind: str,
    count: int,
    square: bool,
    flash_white: bool,
    blank: bool,
    width: int,
    height: int,
) -> bytes:
    img = bytearray(width * height)
    if blank:
        return bytes(img)
    if kind == "flash":
        if flash_white:
            img = bytearray([255]) * (width * height)
        return bytes(img)
    if kind == "square":
        if square:
            for y in range(SQUARE_Y, SQUARE_Y + SQUARE):
                row = y * width
                for x in range(SQUARE_X, SQUARE_X + SQUARE):
                    img[row + x] = 255
        return bytes(img)
    if kind == "text":
        for x, y in active_white(count, square):
            if not (0 <= x < width and 0 <= y < height):
                raise SystemExit(f"glyph pixel {x},{y} outside the picture")
            img[y * width + x] = 255
        return bytes(img)
    raise SystemExit(f"kind {kind}")


def first_diff(got: bytes, exp: bytes, width: int) -> str:
    n = 0
    where = ""
    for i, (a, b) in enumerate(zip(got, exp)):
        if a != b:
            if not where:
                where = f"({i % width},{i // width}) got {a} want {b}"
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
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    args = p.parse_args()
    got = load_p5(args.got, args.width, args.height)
    exp = draw(
        args.kind,
        args.count,
        args.square,
        args.flash_white,
        args.blank,
        args.width,
        args.height,
    )
    white = exp.count(255)
    same = got == exp
    if args.must_differ:
        if same:
            raise SystemExit(
                f"FAIL {args.got.name} matched the wrong picture ({white} white)"
            )
        print(f"ok differ {args.got.name} {first_diff(got, exp, args.width)}")
        return
    if not same:
        raise SystemExit(f"FAIL {args.got.name} {first_diff(got, exp, args.width)}")
    print(f"ok match {args.got.name} white {white}")


if __name__ == "__main__":
    main()
