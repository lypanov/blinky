#!/usr/bin/env python3
"""8×8 glyphs for the Dock text mode.

Bit 7 of a row is the leftmost pixel. Row 0 is the top. Space and the
ten digits are drawn. Every other code is blank. The Verilog function
and the video test use these same bytes.
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Active-pixel origin of the 40×15 window. Digits occupy row 0,
# columns 18..21, so the four glyphs sit on the middle of the screen.
TEXT_X = 160
TEXT_Y = 48
TEXT_COLS = 40
TEXT_ROWS = 15
CELL = 8
DIGIT_COL0 = 18
DIGITS = 4

# Block (15, 11) of the 20×20 square, in active pixels.
SQUARE_X = 15 * 20
SQUARE_Y = 11 * 20
SQUARE = 20

_ART = {
    "0": (
        ".######.",
        "#......#",
        "#......#",
        "#......#",
        "#......#",
        "#......#",
        ".######.",
        "........",
    ),
    "1": (
        "...##...",
        "..###...",
        "...##...",
        "...##...",
        "...##...",
        "...##...",
        ".######.",
        "........",
    ),
    "2": (
        ".######.",
        "......#.",
        "......#.",
        ".######.",
        "#.......",
        "#.......",
        ".######.",
        "........",
    ),
    "3": (
        ".######.",
        "......#.",
        "......#.",
        ".######.",
        "......#.",
        "......#.",
        ".######.",
        "........",
    ),
    "4": (
        "#......#",
        "#......#",
        "#......#",
        ".######.",
        "......#.",
        "......#.",
        "......#.",
        "........",
    ),
    "5": (
        ".######.",
        "#.......",
        "#.......",
        ".######.",
        "......#.",
        "......#.",
        ".######.",
        "........",
    ),
    "6": (
        ".######.",
        "#.......",
        "#.......",
        ".######.",
        "#......#",
        "#......#",
        ".######.",
        "........",
    ),
    "7": (
        ".######.",
        "......#.",
        "......#.",
        ".....#..",
        "....#...",
        "...#....",
        "...#....",
        "........",
    ),
    "8": (
        ".######.",
        "#......#",
        "#......#",
        ".######.",
        "#......#",
        "#......#",
        ".######.",
        "........",
    ),
    "9": (
        ".######.",
        "#......#",
        "#......#",
        ".######.",
        "......#.",
        "......#.",
        ".######.",
        "........",
    ),
}


def _pack(rows: tuple[str, ...]) -> tuple[int, ...]:
    out = []
    for row in rows:
        if len(row) != 8 or any(ch not in ".#" for ch in row):
            raise SystemExit(f"bad glyph row {row!r}")
        byte = 0
        for i, ch in enumerate(row):
            if ch == "#":
                byte |= 1 << (7 - i)
        out.append(byte)
    return tuple(out)


GLYPHS = {ord(ch): _pack(rows) for ch, rows in _ART.items()}


def rows(ch: int) -> tuple[int, ...]:
    return GLYPHS.get(ch, (0, 0, 0, 0, 0, 0, 0, 0))


def bit(ch: int, row: int, col: int) -> int:
    return (rows(ch)[row] >> (7 - col)) & 1


def decimal(count: int) -> str:
    """Four digits, leading zeros. The units place is column 21."""
    return f"{count % 10000:04d}"


def active_white(count: int, square: bool) -> set[tuple[int, int]]:
    """White active pixels of one frame. Origin is the active area."""
    white: set[tuple[int, int]] = set()
    text = decimal(count)
    for i, ch in enumerate(text):
        col = DIGIT_COL0 + i
        for row in range(CELL):
            for sub in range(CELL):
                if bit(ord(ch), row, sub):
                    white.add((TEXT_X + col * CELL + sub, TEXT_Y + row))
    if square:
        for y in range(SQUARE_Y, SQUARE_Y + SQUARE):
            for x in range(SQUARE_X, SQUARE_X + SQUARE):
                white.add((x, y))
    return white


def verilog_function() -> str:
    lines = [
        "function [7:0] font8;",
        "  input [7:0] ch;",
        "  input [2:0] row;",
        "  begin",
        "    case ({ch, row})",
    ]
    for ch in range(256):
        glyph = GLYPHS.get(ch)
        if glyph is None:
            continue
        for row, byte in enumerate(glyph):
            key = (ch << 3) | row
            lines.append(f"      11'h{key:03X}: font8 = 8'h{byte:02X};")
    lines += [
        "      default: font8 = 8'h00;",
        "    endcase",
        "  end",
        "endfunction",
    ]
    return "\n".join(lines)


def _between(text: str, begin: str, end: str) -> str:
    a = text.find(begin)
    b = text.find(end)
    if a < 0 or b < 0 or b < a:
        raise SystemExit(f"markers {begin!r} .. {end!r} missing")
    return text[a + len(begin) : b]


def check() -> None:
    video = (ROOT / "gowin" / "video.v").read_text()
    if "// FONT8 BEGIN" not in video:
        if "function [7:0] font8" in video or "wire text_on = 1'b0;" not in video:
            raise SystemExit("gowin/video.v digit ROM is neither present nor retired")
        print("ok font8 retired; the bitmap draws the count")
        return
    body = textwrap.dedent(
        _between(video, "// FONT8 BEGIN\n", "// FONT8 END\n")
    ).strip("\n")
    want = verilog_function()
    if body != want:
        raise SystemExit("gowin/video.v font does not match tools/font8x8.py")
    for name, value in (
        ("TEXT_X", TEXT_X),
        ("TEXT_Y", TEXT_Y),
        ("TEXT_W", TEXT_COLS * CELL),
        ("TEXT_H", TEXT_ROWS * CELL),
    ):
        if f"{name} = 10'd{value};" not in video:
            raise SystemExit(f"video.v {name} is not {value}")
    cpp = (ROOT / "sim" / "tb_video_text.cpp").read_text()
    blob = _between(cpp, "// FONT8 BEGIN\n", "// FONT8 END\n")
    found = {}
    for ch, row, byte in re.findall(
        r"font\[(\d+)\]\[(\d+)\] = 0x([0-9A-Fa-f]+);", blob
    ):
        found[(int(ch), int(row))] = int(byte, 16)
    for ch, glyph in GLYPHS.items():
        for row, byte in enumerate(glyph):
            if found.get((ch, row)) != byte:
                raise SystemExit(f"tb_video_text.cpp glyph {ch} row {row}")
    if 'DIGIT_COL0 = 18' not in cpp or 'TEXT_X = 160' not in cpp:
        raise SystemExit("tb_video_text.cpp geometry drifted")
    print("ok font8 10 glyphs, video.v and tb_video_text.cpp match")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        print(verilog_function())
