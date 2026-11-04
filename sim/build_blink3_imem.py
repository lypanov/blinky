#!/usr/bin/env python3
"""Build the Blink3 custom IMEM from tests/final_system.code (loader-fixed BL).

Default (no flags) writes the sim image used by Verilator. FPGA builds pass
--max-iter and --pad so the same trampoline + linked modules land in BRAM
with a hardware-visible delay word.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from imem_layout import (  # noqa: E402
    BLINK3_FPGA_IMEM_WORDS,
    BLINK3_MAXITER,
    BLINK3_MAXITER_PC,
    BLINK3_MHI_WORD,
    blink3_imem,
    blink3_predicted_hz,
    pad_imem,
    patch_blink3_maxiter,
    write_words,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Blink3 IMEM words")
    parser.add_argument(
        "--max-iter",
        type=int,
        default=None,
        help="Patch LightToggle MHI delay (e.g. 262144 or 131072). Default: leave image as linked.",
    )
    parser.add_argument(
        "--pad",
        type=int,
        default=None,
        help=f"Pad with 0xBEEF to this many words (FPGA: {BLINK3_FPGA_IMEM_WORDS}).",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "blink3.words"),
        help="Output hex-word file (one 8-digit word per line)",
    )
    args = parser.parse_args()

    src = os.path.join(ROOT, "tests", "final_system.code")
    words = blink3_imem(src)
    n = args.max_iter
    if n is not None:
        words = patch_blink3_maxiter(words, n)
    if args.pad is not None:
        words = pad_imem(words, args.pad)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)

    mhi = words[BLINK3_MAXITER_PC // 4]
    print(f"[imem] {len(words)} words -> {args.out}")
    print(f"[imem] word[0] = 0x{words[0]:08x}  (BL AMMT BEGIN 0x1028)")
    print(f"[imem] word[1] = 0x{words[1]:08x}  (BL LightToggle 0x1048)")
    print(f"[imem] 0x108C = 0x{words[0x108C // 4]:08x}  (BL → Toggle, expect f7ffffdc)")
    print(f"[imem] 0x1000 = 0x{words[0x1000 // 4]:08x}  (Toggle)")
    print(f"[imem] 0x1050 = 0x{words[0x1050 // 4]:08x}  (LightToggle counter := 0)")
    print(f"[imem] 0x105C = 0x{mhi:08x}  (MHI delay, default {BLINK3_MHI_WORD:08x})")
    if n is not None:
        pred = blink3_predicted_hz(n)
        print(
            f"[imem] maxIterations={n}  predicted blink {pred['frequency_hz']:.4f} Hz "
            f"({pred['cycles_per_edge']} cycles/edge @ {pred['clock_hz']} Hz)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
