#!/usr/bin/env python3
"""HyperRAM step-1 image: Blink3 plus a walking-pattern prologue.

The prologue is a new machine-code block. It does not edit any .Mod file
or the Blink3 words, except one copy of the setup MOV at 0x9C, and only
in this image. That MOV sends the CPU to the prologue. On a match the
prologue branches to address 0, which is still Blink3's trampoline. On a
mismatch it spins and never stores to the LED.

Fetch stays in block RAM. Only data loads and stores go to HyperRAM.

Why a wrong memory cannot blink the LED
----------------------------------------
The pattern is 1<<0 .. 1<<31 at 0x400, and the two's-complement inverse
at 0x500 (256 bytes higher, so the 64-word block RAM aliases the pair).
The expected XOR and the expected sum of each series are immediates
computed here, not by the same ADD that built the pattern.

Each compare stores (got - expected) at its own word, 0x7C0 through
0x7DC. The CPU turns the LED on only after all eight of those stores
wrote a zero. A wrong word makes a non-zero difference, that slot stays
dark, and io.led stays 0 even if the program then falls into Blink3.

The eight values are the pattern XOR, the pattern sum, the complement
XOR, the complement sum, MT[1] (must still be 0x50), MT[2] (0x70),
the word at 0x114 (0x11111111, an alias of 0x14 on a 256-byte RAM),
and a sentinel written last at 0x7F0 (0xA5A5A5A5). Zeros, all-ones,
a single stuck beat, and "return the last write" all miss at least one
of these. The sum of the walking bits is 0xFFFFFFFF; the sum of the
complements is 0xFFFFFFE1. An alias that returns the complement for
both series matches the XOR (both are 0xFFFFFFFF) and fails the sum.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from imem_layout import (  # noqa: E402
    BEEF,
    BLINK3_FPGA_IMEM_WORDS,
    BLINK3_IMEM_WORDS,
    BLINK3_MAXITER_PC,
    SETUP,
    blink3_imem,
    mov_imm,
    pad_imem,
    patch_blink3_maxiter,
    write_words,
)

PROLOGUE = 0x1200
PATTERN = 0x400
COMPLEMENT = 0x500
ALIAS = 0x114
SENTINEL_ADDR = 0x7F0
SENTINEL = 0xA5A5A5A5
ALIAS_VALUE = 0x11111111
CHECK_BASE = 0x7C0
NWORDS = 32


def f0(op: int, rd: int, rb: int, rc: int) -> int:
    return ((rd & 0xF) << 24) | ((rb & 0xF) << 20) | ((op & 0xF) << 16) | (rc & 0xF)


def f1(op: int, rd: int, rb: int, imm: int) -> int:
    if not 0 <= imm <= 0xFFFF:
        raise ValueError(f"F1 immediate {imm:#x} does not fit")
    return 0x40000000 | ((rd & 0xF) << 24) | ((rb & 0xF) << 20) | ((op & 0xF) << 16) | imm


def mhi(rd: int, hi: int) -> int:
    if not 0 <= hi <= 0xFFFF:
        raise ValueError(hi)
    return 0x60000000 | ((rd & 0xF) << 24) | hi


def stw(ra: int, rb: int, off: int) -> int:
    if not 0 <= off < (1 << 20):
        raise ValueError(off)
    return 0xA0000000 | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | off


def ldw(ra: int, rb: int, off: int) -> int:
    if not 0 <= off < (1 << 20):
        raise ValueError(off)
    return 0x80000000 | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | off


def cond_branch(pc: int, target: int, cond: int) -> int:
    off = (target - (pc + 4)) // 4
    if off < -(1 << 23) or off >= (1 << 23):
        raise ValueError(f"branch from {pc:#x} to {target:#x} off {off}")
    return ((0xE0 | (cond & 0xF)) << 24) | (off & 0xFFFFFF)


def load_const(rd: int, value: int) -> list[int]:
    value &= 0xFFFFFFFF
    hi, lo = value >> 16, value & 0xFFFF
    if hi == 0:
        return [f1(0, rd, 0, lo)]
    if lo == 0:
        return [mhi(rd, hi)]
    return [mhi(rd, hi), f1(6, rd, rd, lo)]


def walking_series() -> tuple[list[int], list[int]]:
    """Same steps as the prologue: start at 1, double while i < 31."""
    pattern = []
    comp = []
    pat = 1
    for i in range(NWORDS):
        pattern.append(pat)
        comp.append((0 - pat - 1) & 0xFFFFFFFF)
        if i < NWORDS - 1:
            pat = (pat + pat) & 0xFFFFFFFF
    return pattern, comp


def fold(words: list[int]) -> tuple[int, int]:
    xor_v = 0
    sum_v = 0
    for w in words:
        xor_v ^= w
        sum_v = (sum_v + w) & 0xFFFFFFFF
    return xor_v, sum_v


def expected_constants() -> dict[str, int]:
    pattern, comp = walking_series()
    px, ps = fold(pattern)
    cx, cs = fold(comp)
    return {
        "xor_pat": px,
        "sum_pat": ps,
        "xor_comp": cx,
        "sum_comp": cs,
        "mt1": 0x50,
        "mt2": 0x70,
        "alias": ALIAS_VALUE,
        "sentinel": SENTINEL,
    }


class Asm:
    def __init__(self) -> None:
        self.items: list[tuple] = []
        self.labels: dict[str, int] = {}

    def label(self, name: str) -> None:
        self.items.append(("lab", name))

    def word(self, value: int) -> None:
        self.items.append(("word", value))

    def at(self, fn) -> None:
        self.items.append(("ins", fn))

    def branch(self, name: str, cond: int) -> None:
        def fn(pc: int, name: str = name, cond: int = cond) -> int:
            return cond_branch(pc, self.labels[name], cond)
        self.items.append(("ins", fn))

    def encode(self, base: int) -> list[int]:
        pc = base
        for kind, val in self.items:
            if kind == "lab":
                if val in self.labels:
                    raise ValueError(f"duplicate label {val}")
                self.labels[val] = pc
            else:
                pc += 4
        pc = base
        out = []
        for kind, val in self.items:
            if kind == "lab":
                continue
            out.append(val if kind == "word" else val(pc))
            pc += 4
        return out


def _fold_diff(a: Asm, acc: int, expected: int, slot: int) -> None:
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, acc, 6))       # R0 = acc - expected
    a.word(f0(6, 10, 10, 0))       # R10 |= R0
    a.word(mov_imm(11, CHECK_BASE + 4 * slot))
    a.word(stw(0, 11, 0))          # store the difference; zero arms this slot


def assemble_prologue(success: int = 0) -> list[int]:
    c = expected_constants()
    a = Asm()
    # R12 (MT = 0x10) and R14 (SP) stay as setup left them.
    a.word(mov_imm(1, 0))
    a.word(mov_imm(2, 1))
    a.word(mov_imm(3, PATTERN))
    a.label("wloop")
    a.word(stw(2, 3, 0))
    a.word(mov_imm(0, 0))
    a.word(f0(9, 6, 0, 2))         # ~pat = 0 - pat - 1
    a.word(f1(9, 6, 6, 1))
    a.word(stw(6, 3, COMPLEMENT - PATTERN))
    a.word(f1(8, 1, 1, 1))
    a.word(f1(9, 0, 1, NWORDS))
    a.branch("wdone", 1)           # BEQ when i == 32, before the next double
    a.word(f0(8, 2, 2, 2))
    a.word(f1(8, 3, 3, 4))
    a.branch("wloop", 7)
    a.label("wdone")
    for w in load_const(2, ALIAS_VALUE):
        a.word(w)
    a.word(mov_imm(3, ALIAS))
    a.word(stw(2, 3, 0))
    for w in load_const(2, SENTINEL):
        a.word(w)
    a.word(mov_imm(3, SENTINEL_ADDR))
    a.word(stw(2, 3, 0))
    for rd in (4, 5, 8, 9, 10):
        a.word(mov_imm(rd, 0))
    a.word(mov_imm(1, 0))
    a.word(mov_imm(3, PATTERN))
    a.label("rloop")
    a.word(ldw(7, 3, 0))
    a.word(f0(7, 4, 4, 7))         # xor_pat ^= word
    a.word(f0(8, 5, 5, 7))         # sum_pat += word
    a.word(f1(8, 1, 1, 1))
    a.word(f1(8, 3, 3, 4))
    a.word(f1(9, 0, 1, NWORDS))
    a.branch("rloop", 9)           # BNE while i != 32
    a.word(mov_imm(1, 0))
    a.word(mov_imm(3, COMPLEMENT))
    a.label("cloop")
    a.word(ldw(7, 3, 0))
    a.word(f0(7, 8, 8, 7))
    a.word(f0(8, 9, 9, 7))
    a.word(f1(8, 1, 1, 1))
    a.word(f1(8, 3, 3, 4))
    a.word(f1(9, 0, 1, NWORDS))
    a.branch("cloop", 9)
    _fold_diff(a, 4, c["xor_pat"], 0)
    _fold_diff(a, 5, c["sum_pat"], 1)
    _fold_diff(a, 8, c["xor_comp"], 2)
    _fold_diff(a, 9, c["sum_comp"], 3)
    a.word(ldw(7, 12, 4))          # MT[1] at 0x14, must still be 0x50
    _fold_diff(a, 7, c["mt1"], 4)
    a.word(ldw(7, 12, 8))
    _fold_diff(a, 7, c["mt2"], 5)
    a.word(mov_imm(3, ALIAS))
    a.word(ldw(7, 3, 0))
    _fold_diff(a, 7, c["alias"], 6)
    a.word(mov_imm(3, SENTINEL_ADDR))
    a.word(ldw(7, 3, 0))
    _fold_diff(a, 7, c["sentinel"], 7)
    a.word(f1(9, 0, 10, 0))        # SUB R0, R10, 0
    a.branch("hold", 9)            # BNE hold when any difference was non-zero
    a.at(lambda pc, success=success: cond_branch(pc, success, 7))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", 7)
    return a.encode(PROLOGUE)


def hyperram_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    success: int = 0,
) -> list[int]:
    if max_iter is not None and mov_iter is not None:
        raise ValueError("pass only one of max_iter and mov_iter")
    words = blink3_imem(final_system)
    if max_iter is not None:
        words = patch_blink3_maxiter(words, max_iter)
    if mov_iter is not None:
        if not 0 < mov_iter <= 0xFFFF:
            raise ValueError(mov_iter)
        words[BLINK3_MAXITER_PC // 4] = mov_imm(0, mov_iter)
    prog = assemble_prologue(success)
    base = PROLOGUE // 4
    end = base + len(prog)
    if end * 4 > 0x2000:
        raise ValueError(f"prologue runs to {end * 4:#x}, past the 8 KiB model")
    if len(words) < end:
        words.extend([BEEF] * (end - len(words)))
    for i, w in enumerate(prog):
        idx = base + i
        if words[idx] != BEEF:
            raise ValueError(f"prologue overlaps a real word at {idx * 4:#x}")
        words[idx] = w
    # Setup still plants MT and SP, then jumps here instead of to address 0.
    if words[0x9C // 4] != 0x40000000:
        raise ValueError(f"setup MOV R0,0 missing at 0x9C: {words[0x9C // 4]:#x}")
    words[0x9C // 4] = mov_imm(0, PROLOGUE)
    if pad is not None:
        words = pad_imem(words, pad)
    return words


def check_image(words: list[int], original: list[int]) -> None:
    c = expected_constants()
    pattern, comp = walking_series()
    assert pattern == [1 << i for i in range(32)]
    assert [a ^ b for a, b in zip(pattern, comp)] == [0xFFFFFFFF] * 32
    assert c["xor_pat"] == 0xFFFFFFFF
    assert c["sum_pat"] == 0xFFFFFFFF
    assert c["xor_comp"] == 0xFFFFFFFF
    assert c["sum_comp"] == 0xFFFFFFE1
    # Blink3 body and the address-0 trampoline are the original words.
    for addr in (0x00, 0x04, 0x08, 0x80, 0x1000, 0x1048, 0x108C):
        assert words[addr // 4] == original[addr // 4], hex(addr)
    assert words[0x9C // 4] == mov_imm(0, PROLOGUE)
    assert words[0xA0 // 4] == 0xC7000000
    # Success branch is the word immediately before the hold label's ADD.
    # Find the unconditional branch to 0 that is not the hold spin.
    branches_to_0 = []
    for i, w in enumerate(words[PROLOGUE // 4 :], start=PROLOGUE // 4):
        if (w >> 24) == 0xE7:
            pc = i * 4
            off = w & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            target = pc + 4 + off * 4
            if target == 0:
                branches_to_0.append(pc)
    assert branches_to_0, "prologue never branches to the Blink3 trampoline"
    assert 0xE7FFFFFF not in words[PROLOGUE // 4 : PROLOGUE // 4 + 400]
    # Hold is a two-instruction spin, not the halt encoding.
    hold = words[branches_to_0[0] // 4 + 1]
    assert hold == f1(8, 1, 1, 1), hex(hold)
    print("[ok] prologue constants", {k: f"{v:08x}" for k, v in c.items()})
    print(f"[ok] prologue {branches_to_0[0] - PROLOGUE + 12} bytes at {PROLOGUE:#x}")
    print(f"[ok] success branch at {branches_to_0[0]:#x}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the HyperRAM step-1 IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None,
                        help="Sim only: MOV the delay instead of MHI, so N can be small")
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "hyperram.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    words = hyperram_imem(src, max_iter=args.max_iter, mov_iter=args.mov_iter, pad=args.pad)
    check_image(words, original)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(f"[imem] {len(words)} words -> {args.out}")
    if args.pad == BLINK3_FPGA_IMEM_WORDS or args.pad is None:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
