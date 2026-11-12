#!/usr/bin/env python3
"""Host drawing of the letter and the count Blink paints.

The font file stores rows bottom-first. This bitmap's Y grows downward,
and Display.CopyPattern draws the first raster byte at the given y, so
Blink reverses the rows before the call. The painter here does the same
reversal. The letter shares the square's words: a load that returns 0
drops the square bits on the way on, and lights the letter on the way off.

Texts.WriteInt(W, n, 1) writes the decimal digits and no leading spaces.
The 4K line is the generated 4x6 file, at bitmap (64, 40). The letter A
is at (80, 55). The Dock line is Oberon10, at bitmap (96, 96). The letter
is at (143, 110).
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
# Top row first. Packed bottom-first, the same way the A above is stored.
TINY_DIGITS = (
    ("###", "#.#", "#.#", "#.#", "###"),
    (".#.", "##.", ".#.", ".#.", "###"),
    ("###", "..#", "###", "#..", "###"),
    ("###", "..#", "###", "..#", "###"),
    ("#.#", "#.#", "###", "..#", "..#"),
    ("###", "#..", "###", "..#", "###"),
    ("###", "#..", "###", "#.#", "###"),
    ("###", "..#", "..#", "..#", "..#"),
    ("###", "#.#", "###", "#.#", "###"),
    ("###", "#.#", "###", "..#", "###"),
)
COUNTS = range(1, 13)


def _pack_rows(rows: tuple[str, ...]) -> bytes:
    out = []
    for row in reversed(rows):
        value = 0
        for i, ch in enumerate(row):
            if ch == "#":
                value |= 1 << i
        out.append(value)
    return bytes(out)


def tiny_bytes() -> bytes:
    """Digits 0..9 and A. NofRuns is the low byte at file offset 14."""
    parts = [
        bytes((0xDB, 0x00, ord("T"), ord("4"))),
        struct.pack("<6H", 6, 0, 3, 0, 4, 2),
        struct.pack("<4H", 48, 58, 65, 66),
    ]
    box = struct.pack("<5H", 4, 0, 0, 3, 5)
    parts.extend(box for _ in range(11))
    parts.extend(_pack_rows(rows) for rows in TINY_DIGITS)
    parts.append(TINY_A)
    return b"".join(parts)


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
    def __init__(self, name: str, width: int, sq, mk, text, scale: int):
        self.name = name
        self.span = width // 8
        self.sq = sq
        self.mk = mk
        self.text = text
        self.scale = scale


# Same origins as the constants in tests/Blink5.Mod.
NANO = Board("nano", 256, (75, 55, 5, 5), (80, 55), (64, 40), 4)
DOCK = Board("dock", 512, (150, 110, 10, 10), (143, 110), (96, 96), 2)


def count_text(count: int) -> str:
    """Texts.WriteInt of a positive count with field width 1."""
    if count < 0:
        raise SystemExit(f"count {count}")
    return str(count)


def draw_text(words: dict[int, int], font: bytes, text: str, origin, span: int, mode: str) -> None:
    pen, origin_y = origin
    for ch in text:
        dx, x, y, w, h, raster = letter(font, ord(ch))
        if w > 0 and h > 0:
            rows = flipped_rows(raster, w, h)
            copy_pattern(words, rows, pen + x, origin_y + y, w, span, mode)
        pen += dx


def _paint_picture(words: dict[int, int], board: Board, font: bytes, count: int, mode: str) -> None:
    dx, x, y, w, h, raster = letter(font, 65)
    del dx
    rows = flipped_rows(raster, w, h)
    sx, sy, sw, sh = board.sq
    mx, my = board.mk
    if mode == "paint":
        paint(words, sx, sy, sw, sh, board.span, "replace", False)
        copy_pattern(words, rows, mx + x, my + y, w, board.span, "paint")
        draw_text(words, font, count_text(count), board.text, board.span, "paint")
    else:
        paint(words, sx, sy, sw, sh, board.span, "replace", True)
        copy_pattern(words, rows, mx + x, my + y, w, board.span, "invert")
        draw_text(words, font, count_text(count), board.text, board.span, "invert")


def frame(board: Board, font: bytes, on: bool, count: int = 1) -> dict[int, int]:
    words: dict[int, int] = {}
    # The off frame paints, then erases, the way Blink's two calls do.
    _paint_picture(words, board, font, count, "paint")
    if not on:
        _paint_picture(words, board, font, count, "invert")
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


def _pictures(board: Board, font: bytes) -> list[tuple]:
    return [tuple(sorted(frame(board, font, True, count).items())) for count in COUNTS]


def _header(nano: list[tuple], dock: list[tuple]) -> str:
    def rows(name: str, items: tuple) -> str:
        body = ",\n".join(f"  {{{word}, 0x{data:08X}u}}" for word, data in items)
        return (
            f"static const PicWord PIC_{name}[] = {{\n{body},\n}};\n"
            f"static const int PIC_{name}_N = {len(items)};\n"
        )

    body = []
    for count, items in enumerate(nano, start=1):
        body.append(rows(f"NANO_{count}", items))
    for count, items in enumerate(dock, start=1):
        body.append(rows(f"DOCK_{count}", items))
    nano_ptrs = ", ".join(f"PIC_NANO_{c}" for c in COUNTS)
    nano_ns = ", ".join(f"PIC_NANO_{c}_N" for c in COUNTS)
    dock_ptrs = ", ".join(f"PIC_DOCK_{c}" for c in COUNTS)
    dock_ns = ", ".join(f"PIC_DOCK_{c}_N" for c in COUNTS)
    last = COUNTS[-1]
    return (
        "// Generated by tools/font_glyph.py. The count, one higher each on-edge.\n"
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
        + "\n".join(body)
        + "\n"
        f"static const PicWord* const PIC_NANO_AT[] = {{ {nano_ptrs} }};\n"
        f"static const int PIC_NANO_AT_N[] = {{ {nano_ns} }};\n"
        f"static const PicWord* const PIC_DOCK_AT[] = {{ {dock_ptrs} }};\n"
        f"static const int PIC_DOCK_AT_N[] = {{ {dock_ns} }};\n"
        f"static const int PIC_COUNTS = {last};\n"
        "\n"
        "inline int picture_ok(const std::map<int, uint32_t>& bmp, int led_on,\n"
        "                       int count, int dock) {\n"
        "  if (!led_on) {\n"
        "    for (const auto& kv : bmp) {\n"
        "      if (kv.second != 0u) {\n"
        "        fprintf(stderr, \"FAIL bitmap word %d is %08x\\n\", kv.first, kv.second);\n"
        "        return 0;\n"
        "      }\n"
        "    }\n"
        "    printf(\"GLYPH led 0\\n\");\n"
        "    return 1;\n"
        "  }\n"
        "  if (count < 1 || count > PIC_COUNTS) {\n"
        "    fprintf(stderr, \"FAIL count %d\\n\", count);\n"
        "    return 0;\n"
        "  }\n"
        "  const PicWord* rows = dock ? PIC_DOCK_AT[count - 1] : PIC_NANO_AT[count - 1];\n"
        "  int n = dock ? PIC_DOCK_AT_N[count - 1] : PIC_NANO_AT_N[count - 1];\n"
        "  for (int i = 0; i < n; i++) {\n"
        "    auto it = bmp.find(rows[i].word);\n"
        "    uint32_t got = it == bmp.end() ? 0u : it->second;\n"
        "    if (got != rows[i].on) {\n"
        "      fprintf(stderr, \"FAIL bitmap word %d is %08x wanted %08x count %d\\n\",\n"
        "              rows[i].word, got, rows[i].on, count);\n"
        "      return 0;\n"
        "    }\n"
        "  }\n"
        "  for (const auto& kv : bmp) {\n"
        "    int known = 0;\n"
        "    for (int i = 0; i < n; i++) if (rows[i].word == kv.first) known = 1;\n"
        "    if (!known && kv.second != 0u) {\n"
        "      fprintf(stderr, \"FAIL bitmap word %d is %08x count %d\\n\",\n"
        "              kv.first, kv.second, count);\n"
        "      return 0;\n"
        "    }\n"
        "  }\n"
        "  printf(\"GLYPH led 1 count %d words %d\\n\", count, n);\n"
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


def _built(tiny: bytes, oberon: bytes) -> tuple[list[tuple], list[tuple]]:
    nano = _pictures(NANO, tiny)
    dock = _pictures(DOCK, oberon)
    for count, (npic, dpic) in enumerate(zip(nano, dock), start=1):
        if not npic or not dpic:
            raise SystemExit(f"count {count} painted nothing")
        if frame(NANO, tiny, False, count) or frame(DOCK, oberon, False, count):
            raise SystemExit(f"count {count} off frame is not black")
        if count > 1 and (npic == nano[count - 2] or dpic == dock[count - 2]):
            raise SystemExit(f"count {count} matches the previous picture")
    return nano, dock


def check() -> None:
    tiny, oberon = _load_fonts()
    if tiny[14] != 2 or oberon[14] != 6:
        raise SystemExit("NofRuns bytes are not 2 and 6")
    nano, dock = _built(tiny, oberon)
    text = open(HEADER_PATH, "r", encoding="ascii").read()
    if text != _header(nano, dock):
        raise SystemExit(f"{HEADER_PATH} does not match the painter")
    print(f"[ok] glyph counts {len(nano)} nano {len(nano[0])} words, "
          f"dock {len(dock[0])} words")


def write() -> None:
    os.makedirs(os.path.dirname(HEADER_PATH), exist_ok=True)
    open(TINY_PATH, "wb").write(tiny_bytes())
    tiny, oberon = _load_fonts()
    nano, dock = _built(tiny, oberon)
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
