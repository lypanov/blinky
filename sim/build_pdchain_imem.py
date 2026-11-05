#!/usr/bin/env python3
"""Step 5 image: the device walks the P chain and the D chain.

tests/BlinkChain.Mod is the source of the formulas. This host has no
Oberon compiler, so this file emits the ORG encodings. The ROM holds the
unfixed module words. The prologue plants the anchors, walks both chains,
and only then branches to address 0. A store into 0x1000..0x10FF is what
a later fetch of that PC executes. The new instructions are not in the
delay loop.

The two import pairs are not in LightToggle.Mod. They are the D-chain
forms Modules.Mod still has to fix: an imported variable (the following
word keeps its register fields) and a code-relative value (ODD, so the
offset becomes entry + code - data). They sit in the padding after the
module and are linked onto the existing chain. The delay loop does not
fetch them.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_fixup_imem import ALU, assemble_alu  # noqa: E402
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    hyperram_imem,
    ldw,
    load_const,
    mhi,
    mov_imm,
    stw,
)
from build_rsc_imem import READER, assemble_reader  # noqa: E402
from imem_layout import (  # noqa: E402
    BEEF,
    BLINK3_MAXITER_PC,
    blink3_imem,
    pad_imem,
    write_words,
)
from rsc_parser import ImportedModule, fixup_bl, fixup_ldr_str_add  # noqa: E402

CHAIN = 0x1C00
CHECK = 0x800
IMP = 0x300
DESC = 0x310
ENT = 0x330
SENTINEL = 0x3C3C3C3C
LIGHT = 0x50
# 32 reader/ALU slots plus the five chain compares. Must match extraChecks.
EXTRA_CHECKS = 37
BL_SLOT = 32
AMMT_SLOT = 33
VAR_SLOT = 34
EXEC_SLOT = 35
ODD_SLOT = 36
BNE = 9
BEQ = 1
ALWAYS = 7
BT_R11 = 0xC700000B

AMMT_CODE = 0x1000
LT_CODE = 0x1048
AMMT_FIXORG_D = 13
LT_FIXORG_P = 17
LT_FIXORG_D = 30

# Unfixed pairs, then the words Modules.Mod writes. The variable's second
# word keeps displacement 0; offset 1 aliases the same HyperRAM beat, so
# the stored instruction is the proof. The ODD add is the other proof:
# R0 becomes Toggle's address, not the data base.
VAR_AT = 0x10AC
VAR_NEXT = 0x10B0
VAR_RET = 0x10B4
ODD_AT = 0x10C0
ODD_NEXT = 0x10C4
ODD_RET = 0x10C8
VAR_GETSB = 0x8D100006
VAR_LDW = 0x80D00001
ODD_GETSB = 0x8D100005
ODD_ADD = 0x40D80102
FIX_BL = 0xF7FFFFDC
FIX_AMMT = 0x8DC00004
FIX_LT = 0x8DC00008
FIX_VAR_LDW = 0x80D00000
FIX_ODD_ADD = 0x40D80FB0
TOGGLE = 0x1000

AMMT_SITES = (0x100C, 0x1034)
LT_SITES = (0x1054, 0x1068, 0x108C, 0x1094)


def _load_hex(path: str) -> list[int]:
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                words.append(int(line, 16))
    return words


def _b_target(pc: int, word: int) -> int | None:
    top = (word >> 24) & 0xFF
    if not 0xE0 <= top <= 0xEF:
        return None
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return pc + 4 + off * 4


def _place(words: list[int], base: int, prog: list[int], end_limit: int) -> None:
    if base + len(prog) > end_limit:
        raise ValueError(f"block at {base:#x} runs to {(base + len(prog)) * 4:#x}")
    for i, w in enumerate(prog):
        idx = base + i
        if words[idx] != BEEF:
            raise ValueError(f"overlaps a real word at {idx * 4:#x}: {words[idx]:#x}")
        words[idx] = w


def _diff(a: Asm, reg: int, expected: int, slot: int) -> None:
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, reg, 6))
    a.word(f0(6, 10, 10, 0))
    a.word(mov_imm(11, CHECK + 4 * slot))
    a.word(stw(0, 11, 0))


def _load_word(a: Asm, addr: int, rd: int) -> None:
    for w in load_const(3, addr):
        a.word(w)
    a.word(ldw(rd, 3, 0))


def _or_diff(a: Asm, reg: int, expected: int) -> None:
    """R5 |= (reg - expected). The store of R5 is a separate slot."""
    for w in load_const(6, expected):
        a.word(w)
    a.word(f0(9, 0, reg, 6))
    a.word(f0(6, 5, 5, 0))


def _plant(a: Asm, addr: int, value: int) -> None:
    for w in load_const(3, addr):
        a.word(w)
    for w in load_const(0, value):
        a.word(w)
    a.word(stw(0, 3, 0))


def _call(a: Asm, code: int, fixorg_p: int, fixorg_d: int, modnum: int) -> None:
    for w in load_const(1, code):
        a.word(w)
    a.word(mov_imm(4, fixorg_p))
    a.word(mov_imm(5, fixorg_d))
    a.word(mov_imm(7, IMP))
    a.word(mov_imm(8, modnum))
    # The branch is the next word, so the link is this MOV's PC + 8.
    a.at(lambda pc: mov_imm(11, pc + 8))
    a.branch("fix", ALWAYS)


def assemble_chain(break_slot: int | None) -> tuple[list[int], dict[str, int]]:
    """FixP then FixD, then the compares. R12 stays the MT pointer."""
    expect = {
        BL_SLOT: FIX_BL,
        AMMT_SLOT: 0,
        VAR_SLOT: FIX_VAR_LDW,
        EXEC_SLOT: 0,
        ODD_SLOT: TOGGLE,
    }
    if break_slot is not None:
        if break_slot not in expect:
            raise SystemExit(f"break slot {break_slot} is not a chain compare")
        expect[break_slot] = (expect[break_slot] + 1) & 0xFFFFFFFF
    a = Asm()
    a.word(mov_imm(10, 0))
    _plant(a, IMP, DESC)
    _plant(a, DESC + 0, 1)
    _plant(a, DESC + 4, AMMT_CODE)
    _plant(a, DESC + 8, LIGHT)
    _plant(a, DESC + 12, ENT)
    _plant(a, ENT + 0, 40)
    _plant(a, ENT + 4, 0)
    _plant(a, ENT + 8, 0)
    _call(a, AMMT_CODE, 0, AMMT_FIXORG_D, 1)
    _call(a, LT_CODE, LT_FIXORG_P, LT_FIXORG_D, 2)

    _load_word(a, 0x108C, 1)
    _diff(a, 1, expect[BL_SLOT], BL_SLOT)
    a.word(mov_imm(5, 0))
    _load_word(a, 0x100C, 1)
    _or_diff(a, 1, FIX_AMMT)
    _load_word(a, 0x1034, 1)
    _or_diff(a, 1, FIX_AMMT)
    _diff(a, 5, expect[AMMT_SLOT], AMMT_SLOT)
    _load_word(a, VAR_NEXT, 1)
    _diff(a, 1, expect[VAR_SLOT], VAR_SLOT)

    for w in load_const(3, LIGHT):
        a.word(w)
    for w in load_const(0, SENTINEL):
        a.word(w)
    a.word(stw(0, 3, 0))
    a.word(mov_imm(1, 0))
    a.at(lambda pc: cond_branch(pc, VAR_AT, ALWAYS))
    a.label("after_var")
    for w in load_const(4, LIGHT):
        a.word(w)
    a.word(f0(9, 5, 13, 4))
    for w in load_const(4, SENTINEL):
        a.word(w)
    a.word(f0(9, 6, 0, 4))
    a.word(f0(6, 5, 5, 6))
    _diff(a, 5, expect[EXEC_SLOT], EXEC_SLOT)
    a.word(mov_imm(1, 0))
    a.at(lambda pc: cond_branch(pc, ODD_AT, ALWAYS))
    a.label("after_odd")
    _diff(a, 0, expect[ODD_SLOT], ODD_SLOT)
    a.word(f1(9, 0, 10, 0))
    a.branch("hold", BNE)
    a.at(lambda pc: cond_branch(pc, 0, ALWAYS))
    a.label("hold")
    a.word(f1(8, 1, 1, 1))
    a.branch("hold", ALWAYS)

    # R1 code, R4 fixorgP, R5 fixorgD, R7 import list, R8 mod.num, R11 link.
    # R9 holds the D-chain head across FixP. R12 is not written.
    a.label("fix")
    a.word(f1(1, 5, 5, 2))
    a.word(f0(8, 9, 1, 5))
    a.word(f1(1, 4, 4, 2))
    a.word(f0(8, 2, 1, 4))
    a.label("ploop")
    a.word(f0(9, 0, 2, 1))
    a.branch("pdone", BEQ)
    a.word(ldw(3, 2, 0))
    a.word(f1(2, 4, 3, 20))
    a.word(f1(4, 4, 4, 0xF))
    a.word(f1(2, 6, 3, 12))
    a.word(f1(4, 6, 6, 0xFF))
    a.word(f1(4, 5, 3, 0xFFF))
    a.word(f1(9, 4, 4, 1))
    a.word(f1(1, 4, 4, 2))
    a.word(f0(8, 4, 7, 4))
    a.word(ldw(4, 4, 0))
    a.word(ldw(0, 4, 4))
    a.word(ldw(4, 4, 12))
    a.word(f1(1, 6, 6, 2))
    a.word(f0(8, 6, 4, 6))
    a.word(ldw(6, 6, 0))
    a.word(f0(8, 6, 6, 0))
    a.word(f0(9, 6, 6, 2))
    a.word(f1(9, 6, 6, 4))
    a.word(f1(2, 6, 6, 2))
    for w in load_const(0, 0x00FFFFFF):
        a.word(w)
    a.word(f0(4, 6, 6, 0))
    a.word(mhi(0, 0xF700))
    a.word(f0(8, 6, 6, 0))
    a.word(stw(6, 2, 0))
    a.word(f1(9, 0, 5, 0))
    a.branch("pdone", BEQ)
    a.word(f1(1, 5, 5, 2))
    a.word(f0(9, 2, 2, 5))
    a.branch("ploop", ALWAYS)
    a.label("pdone")
    a.word(f0(0, 2, 0, 9))
    a.label("dloop")
    a.word(f0(9, 0, 2, 1))
    a.branch("ddone", BEQ)
    a.word(ldw(3, 2, 0))
    a.word(f1(2, 4, 3, 20))
    a.word(f1(4, 4, 4, 0xF))
    a.word(f1(4, 5, 3, 0xFFF))
    a.word(f1(2, 6, 3, 24))
    a.word(f1(4, 6, 6, 0xFF))
    a.word(f1(9, 0, 4, 0))
    a.branch("dglobal", BEQ)
    a.word(f1(9, 4, 4, 1))
    a.word(f1(1, 4, 4, 2))
    a.word(f0(8, 4, 7, 4))
    a.word(ldw(4, 4, 0))
    a.word(ldw(9, 4, 0))
    a.word(f1(1, 6, 6, 4))
    a.word(f1(8, 6, 6, 12))
    a.word(f1(1, 6, 6, 20))
    a.word(f1(1, 9, 9, 2))
    a.word(f0(8, 6, 6, 9))
    a.word(stw(6, 2, 0))
    a.word(ldw(3, 2, 4))
    a.word(f1(4, 9, 3, 0xFF))
    a.word(f1(4, 0, 3, 0x100))
    a.word(ldw(6, 4, 12))
    a.word(f1(1, 9, 9, 2))
    a.word(f0(8, 9, 6, 9))
    a.word(ldw(9, 9, 0))
    a.word(f1(9, 6, 0, 0))
    a.branch("dnotodd", BEQ)
    a.word(ldw(6, 4, 4))
    a.word(f0(8, 9, 9, 6))
    a.word(ldw(6, 4, 8))
    a.word(f0(9, 9, 9, 6))
    a.label("dnotodd")
    a.word(f1(4, 9, 9, 0xFFFF))
    a.word(mhi(6, 0xFFFF))
    a.word(f0(4, 3, 3, 6))
    a.word(f0(8, 3, 3, 9))
    a.word(stw(3, 2, 4))
    a.branch("dstep", ALWAYS)
    a.label("dglobal")
    a.word(f1(1, 6, 6, 4))
    a.word(f1(8, 6, 6, 12))
    a.word(f1(1, 6, 6, 20))
    a.word(f1(1, 9, 8, 2))
    a.word(f0(8, 6, 6, 9))
    a.word(stw(6, 2, 0))
    a.label("dstep")
    a.word(f1(9, 0, 5, 0))
    a.branch("ddone", BEQ)
    a.word(f1(1, 5, 5, 2))
    a.word(f0(9, 2, 2, 5))
    a.branch("dloop", ALWAYS)
    a.label("ddone")
    a.word(BT_R11)
    prog = a.encode(CHAIN)
    end = CHAIN + len(prog) * 4
    if end > 0x2000:
        raise SystemExit(f"chain prologue ends at {end:#x}")
    return prog, dict(a.labels)


def _replace_placeholders(words: list[int]) -> None:
    ammt = _load_hex(os.path.join(ROOT, "tests", "fixtures", "unfixed", "AMemoryMappedToggle.code"))
    lt = _load_hex(os.path.join(ROOT, "tests", "fixtures", "unfixed", "Blink3test.code"))
    if len(ammt) != 18 or len(lt) != 25:
        raise SystemExit(f"fixture lengths {len(ammt)} {len(lt)}")
    found = []
    for i, w in enumerate(ammt):
        addr = AMMT_CODE + 4 * i
        if words[addr // 4] != w:
            found.append(addr)
            words[addr // 4] = w
    for i, w in enumerate(lt):
        addr = LT_CODE + 4 * i
        if addr == BLINK3_MAXITER_PC:
            continue
        if words[addr // 4] != w:
            found.append(addr)
            words[addr // 4] = w
    if set(found) != set(AMMT_SITES + LT_SITES):
        raise SystemExit(f"host/fixture diffs {sorted(hex(a) for a in found)}")
    for addr in (VAR_AT, VAR_NEXT, VAR_RET, ODD_AT, ODD_NEXT, ODD_RET):
        if words[addr // 4] != BEEF:
            raise SystemExit(f"{addr:#x} is {words[addr // 4]:#x}, not padding")
    words[VAR_AT // 4] = VAR_GETSB
    words[VAR_NEXT // 4] = VAR_LDW
    words[ODD_AT // 4] = ODD_GETSB
    words[ODD_NEXT // 4] = ODD_ADD


def _reference_fixups() -> None:
    """The same walk the host used to write the linked image, plus the pairs."""
    ammt = _load_hex(os.path.join(ROOT, "tests", "fixtures", "unfixed", "AMemoryMappedToggle.code"))
    lt = _load_hex(os.path.join(ROOT, "tests", "fixtures", "unfixed", "Blink3test.code"))
    imp = ImportedModule(num=1, code=AMMT_CODE, data=LIGHT, entries=[40, 0, 0])
    ammt_out = fixup_ldr_str_add(list(ammt), AMMT_FIXORG_D, 1, None, imports=[])
    if ammt_out[3] != FIX_AMMT or ammt_out[13] != FIX_AMMT:
        raise SystemExit(f"AMMT fixup {[hex(ammt_out[i]) for i in (3, 13)]}")
    code = list(lt) + [0] * 8
    code[25] = VAR_GETSB
    code[26] = VAR_LDW
    code[30] = ODD_GETSB
    code[31] = ODD_ADD
    code[27] = 0x11111111
    fixup_ldr_str_add(code, LT_FIXORG_D, 2, None, imports=[imp])
    fixup_bl(code, LT_FIXORG_P, code_base=LT_CODE, imports=[imp])
    expect = {
        3: FIX_LT,
        8: FIX_LT,
        17: FIX_BL,
        19: FIX_LT,
        25: FIX_AMMT,
        26: FIX_VAR_LDW,
        30: FIX_AMMT,
        31: FIX_ODD_ADD,
        27: 0x11111111,
    }
    for idx, word in expect.items():
        if code[idx] != word:
            raise SystemExit(f"index {idx} is {code[idx]:#x}, want {word:#x}")
    off = FIX_ODD_ADD & 0xFFFF
    if (LIGHT + off) & 0xFFFFFFFF != TOGGLE:
        raise SystemExit(f"ODD add lands on {(LIGHT + off):#x}")


def pdchain_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
) -> tuple[list[int], dict[str, int]]:
    alu_break = break_slot if break_slot is not None and break_slot < 20 else None
    reader_break = break_slot if break_slot is not None and 20 <= break_slot <= 31 else None
    chain_break = break_slot if break_slot is not None and break_slot >= 32 else None
    words = hyperram_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        success=ALU,
        hold_scan=False,
    )
    alu, _ = assemble_alu(alu_break, success=READER)
    reader, _ = assemble_reader(reader_break, success=CHAIN)
    chain, labels = assemble_chain(chain_break)
    need = CHAIN // 4 + len(chain)
    if len(words) < need:
        words.extend([BEEF] * (need - len(words)))
    _place(words, ALU // 4, alu, READER // 4)
    _place(words, READER // 4, reader, CHAIN // 4)
    _replace_placeholders(words)
    _place(words, CHAIN // 4, chain, 0x2000 // 4)
    words[VAR_RET // 4] = cond_branch(VAR_RET, labels["after_var"], ALWAYS)
    words[ODD_RET // 4] = cond_branch(ODD_RET, labels["after_odd"], ALWAYS)
    if pad is not None:
        words = pad_imem(words, pad)
    return words, labels


def check_image(words: list[int], original: list[int], labels: dict[str, int]) -> None:
    _reference_fixups()
    assert words[0x108C // 4] == 0xF7102011
    assert words[0x100C // 4] == 0x8D000003
    assert words[0x1034 // 4] == 0x8D00000A
    assert words[0x1054 // 4] == 0x8D000003
    assert words[0x1068 // 4] == 0x8D000005
    assert words[0x1094 // 4] == 0x8D00000B
    assert words[VAR_AT // 4] == VAR_GETSB
    assert words[VAR_NEXT // 4] == VAR_LDW
    assert words[ODD_AT // 4] == ODD_GETSB
    assert words[ODD_NEXT // 4] == ODD_ADD
    assert words[0x1064 // 4] == 0xEF00000E
    # 0x80D00000 is a real LightToggle load, so it is not banned. The pair's
    # own slot is checked above and is still the displacement-1 placeholder.
    for banned in (FIX_BL, FIX_AMMT, FIX_LT, FIX_ODD_ADD):
        if banned in words:
            raise SystemExit(f"fixed word {banned:#x} is in the ROM")
    for addr in (0x00, 0x04, 0x1000, 0x1048):
        if words[addr // 4] != original[addr // 4]:
            raise SystemExit(f"word at {addr:#x} changed")
    if words[0x9C // 4] != mov_imm(0, 0x1200):
        raise SystemExit("setup does not enter the memory prologue")
    if not any(_b_target(pc, words[pc // 4]) == ALU for pc in range(0x1200, ALU, 4)):
        raise SystemExit("memory prologue does not reach the ALU")
    if not any(_b_target(pc, words[pc // 4]) == READER for pc in range(ALU, READER, 4)):
        raise SystemExit("ALU does not reach the reader")
    if not any(_b_target(pc, words[pc // 4]) == CHAIN for pc in range(READER, CHAIN, 4)):
        raise SystemExit("reader does not reach the chain prologue")
    if _b_target(VAR_RET, words[VAR_RET // 4]) != labels["after_var"]:
        raise SystemExit("variable pair does not return")
    if _b_target(ODD_RET, words[ODD_RET // 4]) != labels["after_odd"]:
        raise SystemExit("ODD pair does not return")
    if not any(_b_target(pc, words[pc // 4]) == 0 for pc in range(CHAIN, labels["hold"], 4)):
        raise SystemExit("success path does not reach address 0")
    if labels["hold"] >= labels["fix"]:
        raise SystemExit("hold falls into the walker")
    end = CHAIN + (labels["ddone"] - CHAIN) + 4
    print(
        "[ok] pdchain",
        EXTRA_CHECKS,
        "checks, prologue",
        hex(CHAIN),
        "hold",
        hex(labels["hold"]),
        "walker",
        hex(labels["fix"]),
        "end",
        hex(end),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-5 P/D-chain IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None,
                        help="Sim only: add 1 to this expected constant")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "pdchain.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    words, labels = pdchain_imem(
        src,
        max_iter=args.max_iter,
        mov_iter=args.mov_iter,
        pad=args.pad,
        break_slot=args.break_slot,
    )
    if args.break_slot is None:
        check_image(words, original, labels)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(f"[imem] {len(words)} words -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
