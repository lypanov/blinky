#!/usr/bin/env python3
"""Host drawing of the one letter Blink paints beside the square.

The font file stores rows bottom-first. This bitmap's Y grows downward,
and Display.CopyPattern draws the first raster byte at the given y, so
Blink reverses the rows before the call. The painter here does the same
reversal. The letter shares the square's words: a load that returns 0
drops the square bits on the way on, and lights the letter on the way off.

The 4K letter is the generated 4x6 file tests/Tiny4x6.Fnt, character A,
at bitmap (80, 55). The Dock letter is tests/Oberon10.Scn.Fnt, the same
character, at bitmap (143, 110).
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TINY_PATH = os.path.join(ROOT, "tests", "Tiny4x6.Fnt")
OBERON_PATH = os.path.join(ROOT, "tests", "Oberon10.Scn.Fnt")
HEADER_PATH = os.path.join(ROOT, "sim", "glyph_expect.h")
OBERON_SHA = "a3d7bba26c27d2a68a2f763ce1fd29968b15def744b1c62e4de9fd557fb49fd8"

# 3x5 A, bottom-row first, bit 0 on the left. The cell is 4 wide and 6 tall.
TINY_A = bytes((0x05, 0x05, 0x07, 0x05, 0x02))


def tiny_bytes() -> bytes:
    """One run, character A. NofRuns is the low byte at file offset 14."""
    parts = [
        bytes((0xDB, 0x00, ord("T"), ord("4"))),
        struct.pack("<6H", 6, 0, 3, 0, 4, 1),
        struct.pack("<2H", 65, 66),
        struct.pack("<5H", 4, 0, 0, 3, 5),
        TINY_A,
    ]
    return b"".join(parts)


# Hand-combined words. Square bits stay set under the letter.
NANO_ON = (
    (442, 0x0002F800),
    (450, 0x0005F800),
    (458, 0x0007F800),
    (466, 0x0005F800),
    (474, 0x0005F800),
)
DOCK_ON = (
    (1764, 0xFFC40000),
    (1780, 0xFFC40000),
    (1796, 0xFFCA0000),
    (1812, 0xFFCA0000),
    (1828, 0xFFDF0000),
    (1844, 0xFFD10000),
    (1860, 0xFFE08000),
    (1876, 0xFFE08000),
    (1892, 0xFFC00000),
    (1908, 0xFFC00000),
)


def _rd(data: bytes, i: int) -> tuple[int, int]:
    return data[i], i + 2


def parse_font(data: bytes) -> tuple[list[tuple[int, int]], list[tuple[int, int, int, int, int]], list[bytes]]:
    if len(data) < 16 or data[0] != 0xDB:
        raise SystemExit("not a font file")
    i = 4
    meta = []
    for _ in range(6):
        value, i = _rd(data, i)
        meta.append(value)
    nof = meta[5]
    runs = []
    for _ in range(nof):
        beg, i = _rd(data, i)
        end, i = _rd(data, i)
        runs.append((beg, end))
    boxes = []
    for _ in range(sum(end - beg for beg, end in runs)):
        fields = []
        for _n in range(5):
            value, i = _rd(data, i)
            fields.append(value)
        dx, x, y, w, h = fields
        if y >= 128:
            y -= 256
        boxes.append((dx, x, y, w, h))
    rasters = []
    for _dx, _x, _y, w, h in boxes:
        n = ((w + 7) // 8) * h
        rasters.append(data[i : i + n])
        i += n
    if i != len(data):
        raise SystemExit(f"font parse ended at {i}, file is {len(data)}")
    return runs, boxes, rasters


def letter(data: bytes, ch: int) -> tuple[int, int, int, int, int, bytes]:
    runs, boxes, rasters = parse_font(data)
    m = 0
    bi = 0
    found = None
    for beg, end in runs:
        while m < beg and m < 128:
            m += 1
        while m < end and m < 128:
            if m == ch:
                found = bi
            bi += 1
            m += 1
    if found is None:
        raise SystemExit(f"font has no character {ch}")
    return boxes[found] + (rasters[found],)


def _bits(row: int, width: int) -> int:
    return row & ((1 << width) - 1)


def paint(words: dict[int, int], x: int, y: int, w: int, h: int, span: int, mode: str, col_black: bool) -> None:
    """ReplConst for a rectangle that stays inside one word."""
    if x // 32 != (x + w - 1) // 32:
        raise SystemExit(f"rectangle at {x} width {w} crosses a word")
    step = span // 4
    bit0 = x % 32
    mask = ((1 << w) - 1) << bit0
    for row in range(h):
        index = (y + row) * step + (x // 32)
        pix = words.get(index, 0)
        if mode == "invert":
            pix ^= mask
        elif mode == "replace" and col_black:
            pix &= ~mask & 0xFFFFFFFF
        else:
            pix |= mask
        words[index] = pix & 0xFFFFFFFF


def copy_pattern(words: dict[int, int], rows: list[int], x: int, y: int, w: int, span: int, mode: str) -> None:
    """CopyPattern paint or invert. rows are already top-first, one int each."""
    if w > 32 or x % 32 + w > 32:
        raise SystemExit(f"pattern at {x} width {w} spills")
    step = span // 4
    shift = x % 32
    for i, pwd in enumerate(rows):
        index = (y + i) * step + (x // 32)
        pix = words.get(index, 0)
        bits = (_bits(pwd, w) << shift) & 0xFFFFFFFF
        if mode == "invert":
            pix ^= bits
        else:
            pix |= bits
        words[index] = pix & 0xFFFFFFFF


def flipped_rows(raster: bytes, w: int, h: int) -> list[int]:
    nb = (w + 7) // 8
    rows = []
    for r in range(h):
        word = 0
        for b in range(nb):
            word |= raster[r * nb + b] << (8 * b)
        rows.append(word)
    rows.reverse()
    return rows


class Board:
    def __init__(self, name: str, width: int, sq, mk, scale: int):
        self.name = name
        self.span = width // 8
        self.sq = sq
        self.mk = mk
        self.scale = scale


NANO = Board("nano", 256, (75, 55, 5, 5), (80, 55), 4)
DOCK = Board("dock", 512, (150, 110, 10, 10), (143, 110), 2)


def frame(board: Board, font: bytes, on: bool) -> dict[int, int]:
    dx, x, y, w, h, raster = letter(font, 65)
    del dx
    rows = flipped_rows(raster, w, h)
    words: dict[int, int] = {}
    sx, sy, sw, sh = board.sq
    mx, my = board.mk
    if on:
        paint(words, sx, sy, sw, sh, board.span, "replace", False)
        copy_pattern(words, rows, mx + x, my + y, w, board.span, "paint")
    else:
        paint(words, sx, sy, sw, sh, board.span, "replace", False)
        copy_pattern(words, rows, mx + x, my + y, w, board.span, "paint")
        paint(words, sx, sy, sw, sh, board.span, "replace", True)
        copy_pattern(words, rows, mx + x, my + y, w, board.span, "invert")
    return {k: v for k, v in words.items() if v}


def screen_pixels(board: Board, font: bytes) -> set[tuple[int, int]]:
    dx, x, y, w, h, raster = letter(font, 65)
    del dx
    rows = flipped_rows(raster, w, h)
    bits: set[tuple[int, int]] = set()
    sx, sy, sw, sh = board.sq
    for row in range(sh):
        for col in range(sw):
            bits.add((sx + col, sy + row))
    mx, my = board.mk
    for row, pwd in enumerate(rows):
        for col in range(w):
            if pwd & (1 << col):
                bits.add((mx + x + col, my + y + row))
    scale = board.scale
    out = set()
    for bx, by in bits:
        for dy in range(scale):
            for dxs in range(scale):
                out.add((bx * scale + dxs, by * scale + dy))
    return out


def _header(nano: tuple, dock: tuple) -> str:
    def rows(name: str, items: tuple) -> str:
        body = ",\n".join(f"  {{{word}, 0x{data:08X}u}}" for word, data in items)
        return (
            f"static const PicWord PIC_{name}[] = {{\n{body},\n}};\n"
            f"static const int PIC_{name}_N = {len(items)};\n"
        )

    return (
        "// Generated by tools/font_glyph.py. Letter A beside the square.\n"
        "#pragma once\n"
        "#include <cstdint>\n"
        "#include <cstdio>\n"
        "#include <map>\n"
        "\n"
        "struct PicWord {\n"
        "  int word;\n"
        "  uint32_t on;\n"
        "};\n"
        "\n"
        + rows("NANO", nano)
        + "\n"
        + rows("DOCK", dock)
        + "\n"
        "inline int picture_ok(const std::map<int, uint32_t>& bmp, int led_on,\n"
        "                       const PicWord* rows, int n) {\n"
        "  for (int i = 0; i < n; i++) {\n"
        "    auto it = bmp.find(rows[i].word);\n"
        "    uint32_t got = it == bmp.end() ? 0u : it->second;\n"
        "    uint32_t want = led_on ? rows[i].on : 0u;\n"
        "    if (got != want) {\n"
        "      fprintf(stderr, \"FAIL bitmap word %d is %08x wanted %08x\\n\",\n"
        "              rows[i].word, got, want);\n"
        "      return 0;\n"
        "    }\n"
        "  }\n"
        "  for (const auto& kv : bmp) {\n"
        "    int known = 0;\n"
        "    for (int i = 0; i < n; i++) if (rows[i].word == kv.first) known = 1;\n"
        "    if (!known && kv.second != 0u) {\n"
        "      fprintf(stderr, \"FAIL bitmap word %d is %08x\\n\", kv.first, kv.second);\n"
        "      return 0;\n"
        "    }\n"
        "  }\n"
        "  printf(\"GLYPH led %d words %d\\n\", led_on, n);\n"
        "  return 1;\n"
        "}\n"
    )


def _load_fonts() -> tuple[bytes, bytes]:
    tiny = open(TINY_PATH, "rb").read()
    if tiny != tiny_bytes():
        raise SystemExit(f"{TINY_PATH} is not the generated 4x6 file")
    oberon = open(OBERON_PATH, "rb").read()
    digest = hashlib.sha256(oberon).hexdigest()
    if digest != OBERON_SHA:
        raise SystemExit(f"Oberon10.Scn.Fnt sha256 {digest}")
    return tiny, oberon


def check() -> None:
    tiny, oberon = _load_fonts()
    if tiny[14] != 1 or oberon[14] != 6:
        raise SystemExit("NofRuns bytes are not 1 and 6")
    nano = tuple(sorted(frame(NANO, tiny, True).items()))
    dock = tuple(sorted(frame(DOCK, oberon, True).items()))
    if nano != NANO_ON or dock != DOCK_ON:
        raise SystemExit(f"painted words\n nano {nano}\n dock {dock}")
    if frame(NANO, tiny, False) or frame(DOCK, oberon, False):
        raise SystemExit("the off frame is not black")
    nano_px = screen_pixels(NANO, tiny)
    dock_px = screen_pixels(DOCK, oberon)
    if len(nano_px) != 560 or len(dock_px) != 468:
        raise SystemExit(f"screen pixels nano {len(nano_px)} dock {len(dock_px)}")
    text = open(HEADER_PATH, "r", encoding="ascii").read()
    if text != _header(nano, dock):
        raise SystemExit(f"{HEADER_PATH} does not match the painter")
    print(f"[ok] glyph nano {len(nano)} words, dock {len(dock)} words, "
          f"screen pixels {len(nano_px)} and {len(dock_px)}")


def write() -> None:
    os.makedirs(os.path.dirname(HEADER_PATH), exist_ok=True)
    open(TINY_PATH, "wb").write(tiny_bytes())
    tiny, oberon = _load_fonts()
    nano = tuple(sorted(frame(NANO, tiny, True).items()))
    dock = tuple(sorted(frame(DOCK, oberon, True).items()))
    if nano != NANO_ON or dock != DOCK_ON:
        raise SystemExit(f"painted words\n nano {nano}\n dock {dock}")
    if frame(NANO, tiny, False) or frame(DOCK, oberon, False):
        raise SystemExit("the off frame is not black")
    open(HEADER_PATH, "w", encoding="ascii").write(_header(nano, dock))
    print(f"[ok] wrote {TINY_PATH} and {HEADER_PATH}")


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        check()
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--write":
        write()
        return 0
    raise SystemExit("usage: tools/font_glyph.py --write|--check")


if __name__ == "__main__":
    main()
