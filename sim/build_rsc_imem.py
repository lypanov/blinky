#!/usr/bin/env python3
"""Step 3 image: memory prologue, fixup ALU, then LDB/STB and an .rsc header.

tests/BlinkRsc.Mod is the source of the reader. This file emits the ORG
encodings because the Oberon compiler is not in the build. The header is
written into HyperRAM with STB and read back with LDB. Every expected
byte, key, version and size is a Python immediate. A non-zero difference
is stored, the pin stays dark, and the CPU sits in its own hold loop.

The new instructions are not in the delay loop. With the fitted HyperRAM
read latency the steady blink stays 103*N+142 cycles per edge.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_fixup_imem import ALU, CHECK, assemble_alu, f1s  # noqa: E402
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    hyperram_imem,
    ldb,
    ldw,
    load_const,
    mov_imm,
    stb,
    stw,
)
from imem_layout import BEEF, blink3_imem, pad_imem, write_words  # noqa: E402

READER = 0x1800
# 20 ALU compares plus these 12. Must match CPUSubset0 extraChecks for
# FPGA_IMAGE=rsc. Slots 20..31 are addresses 0x850..0x87C.
BYTE_CHECKS = 12
EXTRA_CHECKS = 32

HDR = 0x900
LANE = 0x920
NEIGH = 0x924
COPY = 0x940

# Files.ReadString stops at 0X. "Blink5" is the module name this reader checks.
NAME = bytes((0x42, 0x6C, 0x69, 0x6E, 0x6B, 0x35, 0x00))
# Files.ReadInt, little-endian. Not a copy of the bytes in memory: the
# expected word is this constant.
KEY = 0x13579BDF
KEY_BYTES = bytes((0xDF, 0x9B, 0x57, 0x13))
VERSION = 0x01  # Modules.versionkey = 1X
SIZE = 0x00000100
SIZE_BYTES = bytes((0x00, 0x01, 0x00, 0x00))
LANE_BYTES = bytes((0x11, 0x22, 0x33, 0x44))
LANE_WORD = 0x44332211
NEIGH_WORD = 0xA5A5A5A5
UPDATED = 0x77

BNE = 9
ALWAYS = 7


def read_int(data: bytes, offset: int) -> int:
    """Files.ReadInt: ((x3*100H + x2)*100H + x1)*100H + x0."""
    x = data[offset + 3]
    x = ((x << 8) + data[offset + 2]) & 0xFFFFFFFF
    x = ((x << 8) + data[offset + 1]) & 0xFFFFFFFF
    x = ((x << 8) + data[offset]) & 0xFFFFFFFF
    return x


def header_bytes() -> bytes:
    data = NAME + KEY_BYTES + bytes((VERSION,)) + SIZE_BYTES
    if len(data) != 16:
        raise SystemExit(f"header is {len(data)} bytes")
    if read_int(data, 7) != KEY or read_int(data, 12) != SIZE:
        raise SystemExit("header integers do not match the immediates")
    if data[11] != VERSION:
        raise SystemExit("version byte is not at offset 11")
    return data


def expected_map() -> dict[int, int]:
    """slot -> value the CPU must produce. Python arithmetic, not the CPU."""
    return {
        20: LANE_WORD,
        21: LANE_BYTES[0],
        22: LANE_BYTES[1],
        23: LANE_BYTES[2],
        24: LANE_BYTES[3],
        25: NEIGH_WORD,
        26: UPDATED,
        27: LANE_BYTES[2],  # byte 2 still there after the later STB
        28: 0,              # name diffs OR a failed string compare
        29: KEY,
        30: VERSION,
        31: SIZE,
    }


def _diff(a: Asm, reg: int, expected: int, slot: int) -> None:
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, reg, 6))
    a.word(f0(6, 10, 10, 0))
    a.word(mov_imm(11, CHECK + 4 * slot))
    a.word(stw(0, 11, 0))


def _store_bytes(a: Asm, base: int, data: bytes) -> None:
    for i, byte in enumerate(data):
        a.word(mov_imm(1, byte))
        a.word(stb(1, base, i))


def _read_int(a: Asm, base: int, offset: int) -> None:
    """R1 becomes Files.ReadInt of the four bytes at base+offset."""
    a.word(ldb(1, base, offset + 3))
    a.word(f1(1, 1, 1, 8))
    a.word(ldb(2, base, offset + 2))
    a.word(f0(8, 1, 1, 2))
    a.word(f1(1, 1, 1, 8))
    a.word(ldb(2, base, offset + 1))
    a.word(f0(8, 1, 1, 2))
    a.word(f1(1, 1, 1, 8))
    a.word(ldb(2, base, offset))
    a.word(f0(8, 1, 1, 2))


def assemble_reader(break_slot: int | None = None, success: int = 0) -> tuple[list[int], dict[int, int]]:
    exp = expected_map()
    if set(exp) != set(range(20, 20 + BYTE_CHECKS)):
        raise SystemExit(f"expected slots 20..31, got {sorted(exp)}")
    if break_slot is not None:
        exp[break_slot] = (exp[break_slot] + 1) & 0xFFFFFFFF
    header = header_bytes()
    a = Asm()
    a.word(mov_imm(10, 0))

    # Four STB lanes, then one LDW. A STB that writes the whole word leaves
    # only the last byte, so the word is not 44332211H.
    a.word(mov_imm(3, LANE))
    _store_bytes(a, 3, LANE_BYTES)
    a.word(ldw(1, 3, 0))
    _diff(a, 1, exp[20], 20)
    for lane, slot in enumerate(range(21, 25)):
        a.word(ldb(1, 3, lane))
        _diff(a, 1, exp[slot], slot)

    # Neighbour word, then a byte store in the previous word. The neighbour
    # is a different beat of the same burst. A mask that writes every beat
    # destroys A5A5A5A5H. A mask that writes every byte of this beat
    # destroys the 33H that was stored earlier.
    for w in load_const(1, NEIGH_WORD):
        a.word(w)
    a.word(mov_imm(4, NEIGH))
    a.word(stw(1, 4, 0))
    a.word(mov_imm(3, LANE))
    a.word(mov_imm(1, UPDATED))
    a.word(stb(1, 3, 3))
    a.word(mov_imm(4, NEIGH))
    a.word(ldw(1, 4, 0))
    _diff(a, 1, exp[25], 25)
    a.word(mov_imm(3, LANE))
    a.word(ldb(1, 3, 3))
    _diff(a, 1, exp[26], 26)
    a.word(ldb(1, 3, 2))
    _diff(a, 1, exp[27], 27)

    # Header, then a second copy for the ORG string loop. The copy is not
    # the proof: both LDBs can return the same wrong byte. The unrolled
    # compares below use immediates.
    a.word(mov_imm(3, HDR))
    _store_bytes(a, 3, header)
    a.word(mov_imm(3, COPY))
    _store_bytes(a, 3, NAME)

    a.word(mov_imm(5, 0))
    a.word(mov_imm(3, HDR))
    for i, byte in enumerate(NAME):
        a.word(ldb(1, 3, i))
        a.word(mov_imm(2, byte))
        a.word(f0(9, 0, 1, 2))
        a.word(f0(6, 5, 5, 0))

    # ORG.StringRelation, with R3/R4 as the two pointers and R8 as the compare.
    a.word(mov_imm(3, HDR))
    a.word(mov_imm(4, COPY))
    a.label("str")
    a.word(ldb(1, 3, 0))
    a.word(f1(8, 3, 3, 1))
    a.word(ldb(2, 4, 0))
    a.word(f1(8, 4, 4, 1))
    a.word(f0(9, 8, 1, 2))
    a.branch("str_diff", BNE)
    a.word(f1(9, 8, 1, 0))
    a.branch("str", BNE)
    a.word(mov_imm(2, 1))
    a.branch("str_done", ALWAYS)
    a.label("str_diff")
    a.word(mov_imm(2, 0))
    a.label("str_done")
    a.word(mov_imm(1, 1))
    a.word(f0(9, 0, 2, 1))
    a.word(f0(6, 5, 5, 0))
    _diff(a, 5, exp[28], 28)

    a.word(mov_imm(3, HDR))
    _read_int(a, 3, len(NAME))
    _diff(a, 1, exp[29], 29)
    a.word(ldb(1, 3, len(NAME) + 4))
    _diff(a, 1, exp[30], 30)
    _read_int(a, 3, len(NAME) + 5)
    _diff(a, 1, exp[31], 31)

    a.word(f1(9, 0, 10, 0))
    a.branch("hold", BNE)
    # Default target is address 0, which is the step-3 image. Step 4 passes
    # the stored-BL prologue. The encoding for target 0 is unchanged.
    a.at(lambda pc, success=success: cond_branch(pc, success, ALWAYS))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)
    return a.encode(READER), exp


def _branch_target(pc: int, word: int) -> int | None:
    top = (word >> 24) & 0xFF
    if not 0xE0 <= top <= 0xEF:
        return None
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return pc + 4 + off * 4


def rsc_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
) -> list[int]:
    alu_break = break_slot if break_slot is not None and break_slot < 20 else None
    byte_break = break_slot if break_slot is not None and break_slot >= 20 else None
    words = hyperram_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        success=ALU,
        # The failure scanner runs through 0x1400. The ALU has to sit
        # there, so a miss is the two-instruction hold instead.
        hold_scan=False,
    )
    alu, _ = assemble_alu(alu_break, success=READER)
    reader, _ = assemble_reader(byte_break)
    if (READER // 4) < (ALU // 4) + len(alu):
        raise ValueError("reader overlaps the ALU prologue")
    end = (READER // 4) + len(reader)
    if end * 4 > 0x2000:
        raise ValueError(f"reader runs to {end * 4:#x}")
    if len(words) < end:
        words.extend([BEEF] * (end - len(words)))
    for base, prog in ((ALU // 4, alu), (READER // 4, reader)):
        for i, w in enumerate(prog):
            idx = base + i
            if words[idx] != BEEF:
                raise ValueError(f"prologue overlaps a real word at {idx * 4:#x}")
            words[idx] = w
    if pad is not None:
        words = pad_imem(words, pad)
    return words


def check_image(words: list[int], original: list[int]) -> None:
    assert words[0x9C // 4] == mov_imm(0, 0x1200)
    for addr in (0x00, 0x04, 0x1000, 0x1048):
        assert words[addr // 4] == original[addr // 4], hex(addr)
    assert words[ALU // 4 + 1] == f1s(0, 1, 0, -1)
    into_alu = [
        pc
        for pc in range(0x1200, ALU, 4)
        if _branch_target(pc, words[pc // 4]) == ALU
    ]
    into_reader = [
        pc
        for pc in range(ALU, READER, 4)
        if _branch_target(pc, words[pc // 4]) == READER
    ]
    into_blink = [
        pc
        for pc in range(READER, 0x2000, 4)
        if _branch_target(pc, words[pc // 4]) == 0
    ]
    assert into_alu, "memory prologue does not enter the ALU"
    assert into_reader, "ALU does not enter the reader"
    assert into_blink, "reader does not enter Blink3"
    assert any((w >> 28) == 0x9 for w in words[READER // 4 : 0x2000 // 4])
    assert any((w >> 28) == 0xB for w in words[READER // 4 : 0x2000 // 4])
    print("[ok] rsc checks", EXTRA_CHECKS, "reader at", hex(READER))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-3 .rsc IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None,
                        help="Sim only: add 1 to this expected constant")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "rsc.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    words = rsc_imem(
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
