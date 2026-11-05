#!/usr/bin/env python3
"""Step 4 image: one BL stored in HyperRAM and fetched back as an instruction.

tests/BlinkFetch.Mod is the source of the formula. The Oberon compiler is
not in this build, so this file emits the ORG encodings. Modules.FixP for
one instruction is

    offset := (dest - adr - 4) DIV 4
    SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H)

adr is 0x1F00. The ROM at that address is a hold loop. The CPU fetches
0x1F00 from HyperRAM and executes that word. A split bus that still fetches
the ROM enters the hold and the LED stays dark. The new code is not in the
delay loop, so the fitted blink stays 103*N+142 cycles per edge.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_fixup_imem import ALU, assemble_alu  # noqa: E402
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    hyperram_imem,
    load_const,
    mov_imm,
    ldw,
    stw,
)
from build_rsc_imem import READER, assemble_reader  # noqa: E402
from imem_layout import BEEF, blink3_imem, pad_imem, write_words  # noqa: E402

# Must match CPUSubset0's patch PC. The ROM there is a hold, not this BL.
PATCH = 0x1F00
STUB = 0x1C00
PROG = 0x1C80
CHECK = 0x800
# 32 reader/ALU slots plus the stored word and R15. Must match extraChecks.
EXTRA_CHECKS = 34
WORD_SLOT = 32
LINK_SLOT = 33
BNE = 9
ALWAYS = 7


def asr(value: int, n: int) -> int:
    value &= 0xFFFFFFFF
    if n == 0:
        return value
    if value & 0x80000000:
        return ((value >> n) | (0xFFFFFFFF << (32 - n))) & 0xFFFFFFFF
    return value >> n


def fixp_word(dest: int, adr: int) -> int:
    """Modules.Mod lines 143-144. Python arithmetic, not the CPU."""
    offset = asr((dest - adr - 4) & 0xFFFFFFFF, 2)
    return ((offset & 0xFFFFFF) + 0xF7000000) & 0xFFFFFFFF


def bl_target(pc: int, word: int) -> int | None:
    if (word >> 24) != 0xF7:
        return None
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (pc + 4 + off * 4) & 0xFFFFFFFF


def _diff(a: Asm, reg: int, expected: int, slot: int) -> None:
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, reg, 6))
    a.word(f0(6, 10, 10, 0))
    a.word(mov_imm(11, CHECK + 4 * slot))
    a.word(stw(0, 11, 0))


def assemble_prog(break_slot: int | None) -> tuple[list[int], int]:
    word = fixp_word(STUB, PATCH)
    if bl_target(PATCH, word) != STUB:
        raise SystemExit(f"FixP word {word:#x} does not reach the stub")
    # Dropping the MOD 2^24 leaves the sign bits in the word. The compare
    # has to be able to see that mistake.
    unmasked = (asr((STUB - PATCH - 4) & 0xFFFFFFFF, 2) + 0xF7000000) & 0xFFFFFFFF
    if unmasked == word:
        raise SystemExit("MOD 1000000H does not change this offset")
    expected = word
    if break_slot == WORD_SLOT:
        expected = (expected + 1) & 0xFFFFFFFF
    a = Asm()
    a.word(mov_imm(10, 0))
    for w in load_const(1, STUB):
        a.word(w)
    for w in load_const(2, PATCH):
        a.word(w)
    a.word(f0(9, 3, 1, 2))          # dest - adr
    a.word(f1(9, 3, 3, 4))          # - 4
    a.word(f1(2, 3, 3, 2))          # DIV 4, arithmetic
    for w in load_const(4, 0x00FFFFFF):
        a.word(w)
    a.word(f0(4, 3, 3, 4))          # MOD 1000000H
    for w in load_const(4, 0xF7000000):
        a.word(w)
    a.word(f0(8, 3, 3, 4))          # + 0F7000000H
    a.word(stw(3, 2, 0))
    a.word(ldw(1, 2, 0))
    _diff(a, 1, expected, WORD_SLOT)
    a.word(f1(9, 0, 10, 0))
    a.branch("hold", BNE)
    a.at(lambda pc: cond_branch(pc, PATCH, ALWAYS))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)
    return a.encode(PROG), word


def assemble_stub(break_slot: int | None) -> list[int]:
    expected = PATCH + 4
    if break_slot == LINK_SLOT:
        expected = (expected + 1) & 0xFFFFFFFF
    a = Asm()
    _diff(a, 15, expected, LINK_SLOT)
    a.word(f1(9, 0, 10, 0))
    a.branch("hold", BNE)
    a.at(lambda pc: cond_branch(pc, 0, ALWAYS))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)
    return a.encode(STUB)


def assemble_trap() -> list[int]:
    """ROM word at the patch PC. Executing it does not reach Blink3."""
    a = Asm()
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)
    return a.encode(PATCH)


def _place(words: list[int], base: int, prog: list[int], end_limit: int) -> None:
    if base + len(prog) > end_limit:
        raise ValueError(f"block at {base:#x} runs to {(base + len(prog)) * 4:#x}")
    for i, w in enumerate(prog):
        idx = base + i
        if words[idx] != BEEF:
            raise ValueError(f"overlaps a real word at {idx * 4:#x}")
        words[idx] = w


def _b_target(pc: int, word: int) -> int | None:
    top = (word >> 24) & 0xFF
    if not 0xE0 <= top <= 0xEF:
        return None
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return pc + 4 + off * 4


def fetchbl_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
) -> list[int]:
    alu_break = break_slot if break_slot is not None and break_slot < 20 else None
    reader_break = break_slot if break_slot is not None and 20 <= break_slot <= 31 else None
    fetch_break = break_slot if break_slot is not None and break_slot >= 32 else None
    words = hyperram_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        success=ALU,
        # The scanner walks 64 words and runs past the ALU at 0x1400.
        hold_scan=False,
    )
    alu, _ = assemble_alu(alu_break, success=READER)
    reader, _ = assemble_reader(reader_break, success=PROG)
    stub = assemble_stub(fetch_break)
    prog, _word = assemble_prog(fetch_break)
    trap = assemble_trap()
    need = PATCH // 4 + len(trap)
    if len(words) < need:
        words.extend([BEEF] * (need - len(words)))
    _place(words, ALU // 4, alu, STUB // 4)
    _place(words, READER // 4, reader, STUB // 4)
    _place(words, STUB // 4, stub, PROG // 4)
    _place(words, PROG // 4, prog, PATCH // 4)
    _place(words, PATCH // 4, trap, 0x2000 // 4)
    if pad is not None:
        words = pad_imem(words, pad)
    return words


def check_image(words: list[int], original: list[int]) -> None:
    word = fixp_word(STUB, PATCH)
    assert word == 0xF7FFFF3F, hex(word)
    assert bl_target(PATCH, word) == STUB
    assert words[PATCH // 4] != word
    assert words[PATCH // 4] == f1(8, 1, 1, 1)
    assert words[0x9C // 4] == mov_imm(0, 0x1200)
    for addr in (0x00, 0x04, 0x1000, 0x1048):
        assert words[addr // 4] == original[addr // 4], hex(addr)
    assert any(_b_target(pc, words[pc // 4]) == ALU for pc in range(0x1200, ALU, 4))
    assert any(_b_target(pc, words[pc // 4]) == READER for pc in range(ALU, READER, 4))
    assert any(_b_target(pc, words[pc // 4]) == PROG for pc in range(READER, STUB, 4))
    assert any(_b_target(pc, words[pc // 4]) == PATCH for pc in range(PROG, PATCH, 4))
    assert any(_b_target(pc, words[pc // 4]) == 0 for pc in range(STUB, PROG, 4))
    print("[ok] fetchbl", EXTRA_CHECKS, "checks, BL", hex(word), "at", hex(PATCH))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-4 stored-BL IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None,
                        help="Sim only: add 1 to this expected constant")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "fetchbl.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    words = fetchbl_imem(
        src,
        max_iter=args.max_iter,
        mov_iter=args.mov_iter,
        pad=args.pad,
        break_slot=args.break_slot,
    )
    if args.break_slot is None:
        check_image(words, original)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(f"[imem] {len(words)} words -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
