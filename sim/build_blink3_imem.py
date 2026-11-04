#!/usr/bin/env python3
"""Build the Blink3 custom IMEM from tests/final_system.code (loader-fixed BL)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from imem_layout import blink3_imem, write_words  # noqa: E402


def main() -> int:
    src = os.path.join(ROOT, "tests", "final_system.code")
    out = os.path.join(ROOT, "sim", "visualizer", "imem", "blink3.words")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    words = blink3_imem(src)
    write_words(out, words)
    print(f"[imem] {len(words)} words -> {out}")
    print(f"[imem] word[0] = 0x{words[0]:08x}  (BL AMMT BEGIN 0x1028)")
    print(f"[imem] word[1] = 0x{words[1]:08x}  (BL LightToggle 0x1048)")
    print(f"[imem] 0x108C = 0x{words[0x108C // 4]:08x}  (BL → Toggle, expect f7ffffdc)")
    print(f"[imem] 0x1000 = 0x{words[0x1000 // 4]:08x}  (Toggle)")
    print(f"[imem] 0x1050 = 0x{words[0x1050 // 4]:08x}  (LightToggle counter := 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
