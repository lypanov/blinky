#!/usr/bin/env python3
"""The book's trap line, painted the way Blink paints it.

System.Trap writes one line: the position, the trap number, the module
and the address. Blink draws that line with the board's font. A dump
from the simulator is the bitmap words the CPU stored. This checks
those words against the same paint.
"""
from __future__ import annotations

import os
import sys

import font_glyph


def write_int(value: int, width: int) -> str:
    """Texts.WriteInt for a value that fits in a signed 32-bit word."""
    if value == -2147483648:
        return " -2147483648"
    if value < 0:
        width -= 1
        digits = str(-value)
        sign = "-"
    else:
        digits = str(value)
        sign = ""
    return " " * max(0, width - len(digits)) + sign + digits


def write_hex(value: int) -> str:
    """Texts.WriteHex: one space and eight uppercase digits."""
    return f" {(value & 0xFFFFFFFF):08X}"


def trap_text(pos: int, trap: int, module: str, pc: int) -> str:
    """The characters System.Trap writes, without the two returns."""
    return (
        "  pos "
        + write_int(pos, 4)
        + "  TRAP"
        + write_int(trap, 4)
        + " in "
        + module
        + " at"
        + write_hex(pc)
    )


def _rows(raster: bytes, width: int, height: int) -> list[int]:
    """Top row first. The file stores the bottom row first, and Blink reverses it."""
    nbytes = (width + 7) // 8
    rows = []
    for row in range(height):
        word = 0
        for byte in range(nbytes):
            word |= raster[row * nbytes + byte] << (8 * byte)
        rows.append(word & 0xFFFFFFFF)
    rows.reverse()
    return rows


def _xor(words: dict[int, int], index: int, bits: int) -> None:
    words[index] = (words.get(index, 0) ^ (bits & 0xFFFFFFFF)) & 0xFFFFFFFF


def paint(words: dict[int, int], span: int, x: int, y: int, width: int, rows: list[int]) -> None:
    """Display.CopyPattern invert. span is the row length in words."""
    if x < 0 or y < 0:
        raise SystemExit(f"glyph at ({x}, {y}) is off the bitmap")
    shift = x % 32
    word = x // 32
    for row, pwd in enumerate(rows):
        index = (y + row) * span + word
        _xor(words, index, pwd << shift)
        if shift + width > 32:
            spilled = (pwd >> (32 - shift)) & 0xFFFFFFFF
            mask = (0x7FFFFFFF >> (31 - shift)) & 0xFFFFFFFF
            _xor(words, index + 1, spilled & mask)


def render(font: bytes, text: str, origin: tuple[int, int], span: int) -> dict[int, int]:
    words: dict[int, int] = {}
    pen, origin_y = origin
    for ch in text:
        dx, x, y, width, height, raster = font_glyph.letter(font, ord(ch))
        if width > 0 and height > 0:
            paint(
                words, span, pen + x, origin_y + y, width,
                _rows(raster, width, height),
            )
        pen += dx
    return {index: value for index, value in words.items() if value}


def load_expect(path: str) -> dict[str, str]:
    fields = {}
    for line in open(path, encoding="ascii"):
        key, value = line.split(None, 1)
        fields[key] = value.strip()
    return fields


def load_dump(path: str) -> dict[int, int]:
    words = {}
    for line in open(path, encoding="ascii"):
        if not line.strip():
            continue
        index, value = line.split()
        word = int(value, 16)
        if word:
            words[int(index)] = word
    return words


def check(expect_path: str, dump_path: str) -> None:
    fields = load_expect(expect_path)
    ox, oy = (int(part) for part in fields["origin"].split())
    text = trap_text(int(fields["pos"]), int(fields["trap"]), fields["module"], int(fields["pc"], 16))
    font = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), fields["font"]), "rb").read()
    want = render(font, text, (ox, oy), int(fields["span"]))
    got = load_dump(dump_path)
    if want != got:
        missing = sorted(set(want) - set(got))
        extra = sorted(set(got) - set(want))
        differ = sorted(index for index in set(want) & set(got) if want[index] != got[index])
        sample = (differ or extra or missing)[:8]
        detail = " ".join(
            f"{index}:{got.get(index, 0):08x}/{want.get(index, 0):08x}" for index in sample
        )
        raise SystemExit(
            f"trap line mismatch missing {len(missing)} extra {len(extra)} "
            f"differ {len(differ)} {detail}\nline {text!r}"
        )
    print(f"[ok] trap line {fields['board']} {text!r} words {len(want)}")


def blank(path: str) -> None:
    words = load_dump(path)
    if words:
        sample = sorted(words)[:4]
        detail = " ".join(f"{index:08x}" for index in (words[i] for i in sample))
        raise SystemExit(f"pre-font bitmap has {len(words)} words, first {detail}")
    print("[ok] pre-font bitmap is empty")


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--blank":
        blank(sys.argv[2])
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "--check":
        check(sys.argv[2], sys.argv[3])
        return 0
    raise SystemExit("usage: tools/trap_line.py --check expect dump | --blank dump")


if __name__ == "__main__":
    main()
