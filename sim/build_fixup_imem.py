#!/usr/bin/env python3
"""Step 2 image: HyperRAM prologue, then the fixup ALU, then Blink3.

tests/BlinkBoot.Mod is the source of the checks. This file emits the ORG
encodings (Put0 / Put1 / Put3) because the Oberon compiler is not in the
build. Every result is compared with a constant computed here. A non-zero
difference is stored, the pin stays dark, and the CPU sits in a hold loop.

The new instructions are not in the delay loop. With the fitted HyperRAM
read latency the steady blink stays 103*N+142 cycles per edge.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    hyperram_imem,
    load_const,
    mov_imm,
    stw,
)
from imem_layout import BEEF, BLINK3_FPGA_IMEM_WORDS, blink3_imem, pad_imem, write_words  # noqa: E402

ALU = 0x1400
CHECK = 0x800
# Must match CPUSubset0 extraChecks for FPGA_IMAGE=fixup.
EXTRA_CHECKS = 20
INST = 0xA5F3C0DE
NEG = 0x88CA6C00  # -2000000000
POS = 0x77359400  # 2000000000

MI, CS, LT, LE, ALWAYS = 0, 2, 5, 6, 7
PL, GE, GT = 8, 13, 14


def f1s(op: int, rd: int, rb: int, imm: int) -> int:
    """F1 with ORG's v bit: negative immediates are sign-extended."""
    if not -0x8000 <= imm <= 0x7FFF:
        raise ValueError(imm)
    word = f1(op, rd, rb, imm & 0xFFFF)
    if imm < 0:
        word |= 0x10000000
    return word


def asr(value: int, n: int) -> int:
    value &= 0xFFFFFFFF
    if n == 0:
        return value
    if value & 0x80000000:
        return ((value >> n) | (0xFFFFFFFF << (32 - n))) & 0xFFFFFFFF
    return value >> n


def ror(value: int, n: int) -> int:
    value &= 0xFFFFFFFF
    n &= 31
    if n == 0:
        return value
    return ((value >> n) | (value << (32 - n))) & 0xFFFFFFFF


def expected_map() -> dict[int, int]:
    """slot -> value the CPU must produce. Python arithmetic, not the CPU."""
    mno = (INST >> 20) & 0xF
    pno = (INST >> 12) & 0xFF
    disp = INST & 0xFFF
    mod24 = ror((INST << 8) & 0xFFFFFFFF, 8)
    return {
        0: 0xFFFFFFFF,          # MOV -1, sign-extended
        1: 1 << 20,             # F1 LSL
        2: 1 << 20,             # F0 LSL
        3: asr(0x80000000, 4),  # F1 ASR of the sign bit
        4: mno,
        5: pno,
        6: disp,
        7: mod24,
        8: mod24,              # F0 ROR of the same shifted word
        9: 0xF & (~0x2 & 0xFFFFFFFF),  # ANN {0..3} - {1}
        10: 0x00010000 & (~0xFFFFFFFF & 0xFFFFFFFF),  # ANN with sign-extended -1
        11: 4,                  # WHILE i < 4
        12: 1,                  # overflow LT taken
        13: 1,                  # carry set, BCS taken
        14: 1,                  # carry clear, BCS not taken
        15: 1,                  # MI taken on -1
        16: 1,                  # MI not taken on +1
        17: 1,                  # PL taken on +1
        18: 1,                  # LE taken on equal
        19: 1,                  # GT not taken on equal
    }


def _diff(a: Asm, reg: int, expected: int, slot: int) -> None:
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, reg, 6))     # R0 = got - expected
    a.word(f0(6, 10, 10, 0))     # R10 |= difference
    a.word(mov_imm(11, CHECK + 4 * slot))
    a.word(stw(0, 11, 0))


def _taken(a: Asm, cond: int, yes: str, done: str) -> None:
    """Branch is the next instruction after the flag writer. R2 becomes 1 if taken."""
    a.branch(yes, cond)
    a.branch(done, ALWAYS)
    a.label(yes)
    a.word(mov_imm(2, 1))
    a.label(done)


def _not_taken(a: Asm, cond: int, bad: str, done: str) -> None:
    """R2 is preset to 1. A taken branch clears it."""
    a.branch(bad, cond)
    a.branch(done, ALWAYS)
    a.label(bad)
    a.word(mov_imm(2, 0))
    a.label(done)


def assemble_alu(break_slot: int | None = None, success: int = 0) -> tuple[list[int], dict[int, int]]:
    exp = expected_map()
    if set(exp) != set(range(EXTRA_CHECKS)):
        raise SystemExit(f"expected {EXTRA_CHECKS} checks, got {sorted(exp)}")
    if break_slot is not None:
        exp[break_slot] = (exp[break_slot] + 1) & 0xFFFFFFFF
    a = Asm()
    a.word(mov_imm(10, 0))

    # 0. k := -1 is an F1 MOV with v=1. Zero-extend would leave 0000FFFFH.
    a.word(f1s(0, 1, 0, -1))
    _diff(a, 1, exp[0], 0)

    # 1. F1 LSL by 20. A 4-bit shifter would shift by 4.
    a.word(mov_imm(1, 1))
    a.word(f1(1, 1, 1, 20))
    _diff(a, 1, exp[1], 1)

    # 2. F0 LSL, shift count in a register.
    a.word(mov_imm(3, 20))
    a.word(mov_imm(4, 1))
    a.word(f0(1, 1, 4, 3))
    _diff(a, 1, exp[2], 2)

    # 3. F1 ASR of the sign bit. A logical shift leaves 08000000H.
    for w in load_const(1, 0x80000000):
        a.word(w)
    a.word(f1(2, 1, 1, 4))
    _diff(a, 1, exp[3], 3)

    # 4-7. The P-chain field extracts, and MOD 2^24 via LSL then ROR.
    for w in load_const(1, INST):
        a.word(w)
    a.word(f1(2, 1, 1, 20))          # ASR 20
    a.word(f1(4, 1, 1, 15))          # AND 15  -> mno
    _diff(a, 1, exp[4], 4)
    for w in load_const(1, INST):
        a.word(w)
    a.word(f1(2, 1, 1, 12))          # ASR 12
    a.word(f1(4, 1, 1, 0xFF))        # AND 255 -> pno
    _diff(a, 1, exp[5], 5)
    for w in load_const(1, INST):
        a.word(w)
    a.word(f1(4, 1, 1, 0xFFF))       # AND 0xFFF -> disp
    _diff(a, 1, exp[6], 6)
    for w in load_const(1, INST):
        a.word(w)
    a.word(f1(1, 1, 1, 8))           # LSL 8
    a.word(f1(3, 1, 1, 8))           # ROR 8  -> inst MOD 2^24
    _diff(a, 1, exp[7], 7)

    # 8. The same rotate with the count in a register.
    for w in load_const(1, (INST << 8) & 0xFFFFFFFF):
        a.word(w)
    a.word(mov_imm(3, 8))
    a.word(f0(3, 1, 1, 3))
    _diff(a, 1, exp[8], 8)

    # 9. ANN of two registers: {0,1,2,3} - {1}.
    a.word(mov_imm(3, 0xF))
    a.word(mov_imm(4, 0x2))
    a.word(f0(5, 1, 3, 4))
    _diff(a, 1, exp[9], 9)

    # 10. ANN with a sign-extended -1. Zero-extend leaves 00010000H.
    for w in load_const(3, 0x00010000):
        a.word(w)
    a.word(f1s(5, 1, 3, -1))
    _diff(a, 1, exp[10], 10)

    # 11. WHILE i < 4. The exit branch is GE, the negation of LT.
    a.word(mov_imm(1, 0))
    a.label("ge")
    a.word(f1(9, 0, 1, 4))
    a.branch("ge_done", GE)
    a.word(f1(8, 1, 1, 1))
    a.branch("ge", ALWAYS)
    a.label("ge_done")
    _diff(a, 1, exp[11], 11)

    # 12. a < b with overflow. The wrapped result is positive; LT needs V.
    for w in load_const(3, NEG):
        a.word(w)
    for w in load_const(4, POS):
        a.word(w)
    a.word(mov_imm(2, 0))
    a.word(f0(9, 0, 3, 4))
    _taken(a, LT, "ov_ok", "ov_done")
    _diff(a, 2, exp[12], 12)

    # 13. -1 + 1 sets C. BCS must be taken.
    a.word(mov_imm(2, 0))
    a.word(f1s(0, 3, 0, -1))
    a.word(mov_imm(4, 1))
    a.word(f0(8, 0, 3, 4))
    _taken(a, CS, "cs_ok", "cs_done")
    _diff(a, 2, exp[13], 13)

    # 14. 1 + 1 does not set C. BCS must not be taken.
    a.word(mov_imm(2, 1))
    a.word(mov_imm(3, 1))
    a.word(mov_imm(4, 1))
    a.word(f0(8, 0, 3, 4))
    _not_taken(a, CS, "cc_bad", "cc_done")
    _diff(a, 2, exp[14], 14)

    # 15. MI on -1.
    a.word(mov_imm(2, 0))
    a.word(f1s(0, 1, 0, -1))
    _taken(a, MI, "mi_ok", "mi_done")
    _diff(a, 2, exp[15], 15)

    # 16. MI on +1 must not be taken.
    a.word(mov_imm(2, 1))
    a.word(mov_imm(1, 1))
    _not_taken(a, MI, "mi_bad", "mi2_done")
    _diff(a, 2, exp[16], 16)

    # 17. PL on +1.
    a.word(mov_imm(2, 0))
    a.word(mov_imm(1, 1))
    _taken(a, PL, "pl_ok", "pl_done")
    _diff(a, 2, exp[17], 17)

    # 18. LE on equal operands.
    a.word(mov_imm(2, 0))
    a.word(mov_imm(1, 5))
    a.word(f0(9, 0, 1, 1))
    _taken(a, LE, "le_ok", "le_done")
    _diff(a, 2, exp[18], 18)

    # 19. GT on equal operands must not be taken.
    a.word(mov_imm(2, 1))
    a.word(mov_imm(1, 5))
    a.word(f0(9, 0, 1, 1))
    _not_taken(a, GT, "gt_bad", "gt_done")
    _diff(a, 2, exp[19], 19)

    a.word(f1(9, 0, 10, 0))
    a.branch("hold", 9)             # BNE
    # Default target is address 0, which is the step-2 image. Step 3 passes
    # the reader. The encoding for target 0 is unchanged.
    a.at(lambda pc, success=success: cond_branch(pc, success, 7))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)
    return a.encode(ALU), exp


def fixup_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
) -> list[int]:
    words = hyperram_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        success=ALU,
        hold_scan=False,
    )
    prog, _exp = assemble_alu(break_slot)
    base = ALU // 4
    end = base + len(prog)
    if end * 4 > 0x2000:
        raise ValueError(f"ALU prologue runs to {end * 4:#x}")
    if len(words) < end:
        words.extend([BEEF] * (end - len(words)))
    for i, w in enumerate(prog):
        idx = base + i
        if words[idx] != BEEF:
            raise ValueError(f"ALU overlaps a real word at {idx * 4:#x}")
        words[idx] = w
    if pad is not None:
        words = pad_imem(words, pad)
    return words


def check_image(words: list[int], original: list[int], exp: dict[int, int]) -> None:
    assert exp[0] == 0xFFFFFFFF
    assert exp[3] == 0xF8000000
    assert exp[4] == 0xF
    assert exp[7] == INST & 0xFFFFFF
    assert exp[9] == 0xD
    assert exp[10] == 0
    assert words[0x9C // 4] == mov_imm(0, 0x1200)
    for addr in (0x00, 0x04, 0x1000, 0x1048):
        assert words[addr // 4] == original[addr // 4], hex(addr)
    # The memory prologue's success branch goes to the ALU, not to Blink3.
    found = False
    for i, w in enumerate(words[0x1200 // 4 : ALU // 4], start=0x1200 // 4):
        if (w >> 24) == 0xE7:
            pc = i * 4
            off = w & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            if pc + 4 + off * 4 == ALU:
                found = True
    assert found, "memory prologue does not enter the ALU"
    assert words[ALU // 4 + 1] == f1s(0, 1, 0, -1)
    print("[ok] fixup checks", EXTRA_CHECKS, "ALU at", hex(ALU))
    for slot, value in exp.items():
        print(f"    slot {slot:2d}  {value:08x}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-2 fixup IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None,
                        help="Sim only: add 1 to this expected constant")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "fixup.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    exp = expected_map()
    words = fixup_imem(
        src,
        max_iter=args.max_iter,
        mov_iter=args.mov_iter,
        pad=args.pad,
        break_slot=args.break_slot,
    )
    if args.break_slot is None:
        check_image(words, original, exp)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(f"[imem] {len(words)} words -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
