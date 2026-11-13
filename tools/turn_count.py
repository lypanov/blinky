#!/usr/bin/env python3
"""Decode Oberon.Turns from TURN lines and require it to rise.

Blink paints an 8-character field. Spaces advance the pen and leave
the background black. The field stays lit on the off edge.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "tools")
from font_glyph import copy_pattern, flipped_rows, letter  # noqa: E402

NANO = (4, 100, "tests/Tiny4x6.Fnt", 32)
DOCK = (8, 160, "tests/Oberon10.Scn.Fnt", 64)


def _paint(font: bytes, origin_x: int, origin_y: int, span: int, count: int) -> dict[int, int]:
    words: dict[int, int] = {}
    pen = origin_x
    for ch in f"{count:08d}":
        dx, x, y, w, h, raster = letter(font, ord(ch))
        if w > 0 and h > 0:
            rows = flipped_rows(raster, w, h)
            copy_pattern(words, rows, pen + x, origin_y + y, w, span, "paint")
        pen += dx
    return {k: v for k, v in words.items() if v}


def _observed(line: str) -> dict[int, int]:
    words = {}
    for item in line.split()[1:]:
        word, data = item.split(":")
        words[int(word)] = int(data, 16)
    return words


def _match(font: bytes, origin_x: int, origin_y: int, span: int,
           got: dict[int, int], start: int) -> int:
    count = start
    limit = start + 2000000
    while count < limit:
        if _paint(font, origin_x, origin_y, span, count) == got:
            return count
        count += 1
    raise SystemExit(f"no turn count from {start} matches {len(got)} words")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in ("nano", "dock"):
        raise SystemExit("usage: tools/turn_count.py LOG nano|dock")
    origin_x, origin_y, font_path, span = NANO if sys.argv[2] == "nano" else DOCK
    font = open(font_path, "rb").read()
    lines = [line for line in open(sys.argv[1], encoding="ascii") if line.startswith("TURN ")]
    if len(lines) < 3:
        raise SystemExit(f"{len(lines)} TURN lines, wanted at least 3")
    prev = 0
    shown = []
    for line in lines:
        got = _observed(line)
        count = _match(font, origin_x, origin_y, span, got, prev + 1)
        if count <= prev:
            raise SystemExit(f"turn count {count} does not rise past {prev}")
        shown.append(count)
        prev = count
    print("[ok] turns " + " ".join(str(n) for n in shown))
    return 0


if __name__ == "__main__":
    main()
