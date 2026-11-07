#!/usr/bin/env python3
"""Step 8 image: the Modules body is the reset path.

tests/BlinkModules.Mod is the formula for Init. Reset still begins
at the setup block. The MOV at 0x9C enters this body instead of the
memory prologue. The body is

    GET(16); GET(20); GET(24); DEC(limit, 8000H); BT prologue

and the prologue's success path is still Load("Blink5"). The 32 KB
reserve is that DEC. One store lands at each end of the gap and both
words are read back into the same difference. Before the gate, the
body also checks 58 DIV 29 = 2, 58 MOD 29 = 0 (MOV from H), the same
pair as an F0 divide, floor division of -5 by 3, and SYSTEM.BIT of
bit 0 of the word 1. A failed predicate is a nonzero difference, and
the existing BNE holds the LED before the delay loop. R14 becomes
the stack origin that was read, and the delay loop's existing push
lands on the high end. Nothing is added inside the delay loop.
chainFix stays on. The tail does not grow: the proof word is XOR-ed
into the step-7 store at the link slot.

R12 becomes 20H, BootLoad's MTOrg. Kernel.Install's encoding is stored
at that address, which is MT[0]: an unconditional branch to Trap.
Trap reads the instruction at R15-4 and takes DIV 10H MOD 10H the way
ORG lowers it, ASR by 4 then AND 0xF. Trap 0 returns through R15.
Any other number branches to the hold. The blink image does not
execute BL R12. --assert-false is the separate trace: it plants
ASSERT(FALSE) (trap 7) in data memory and branches through R12.
--trap0 is the return trace. Fetch is still the pROM, so the same
branch is also the ROM word at 20H. The boards load the blink image.

Before the gate, the body calls the compiled Modules.Check twice.
sim/inner_core.py compiles those words. "Blink5" must leave res 0
and "9bad" must leave res 1. Both differences fold into R8, which
the existing link-slot store already checks. The tail stays 40.

Proof 5 places that delay loop in external memory and fetches it.
The loader stays in the pROM. Load's BT R1 is retargeted at the
placer (0x1100). The placer copies the fixed page-0x10 words to
0x2200, rewrites the one BL for that address, and walks one
type-chain entry at 0x2304. The CPU then fetches page 0x22 from
external memory. Reset and training never do.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_files_imem import EXTRA_CHECKS, FILES, NAME_ACC, files_imem  # noqa: E402
from inner_core import MOD_NUM, load_inner  # noqa: E402
from build_hyperram_imem import (  # noqa: E402
    Asm,
    PROLOGUE,
    cond_branch,
    f0,
    f1,
    ldw,
    load_const,
    mhi,
    mov_imm,
    stw,
    write_words,
)
from build_pdchain_imem import _b_target, _place  # noqa: E402
from imem_layout import BEEF  # noqa: E402

BODY = 0x06C0
ADDR_ALLOC = 16
ADDR_ROOT = 20
ADDR_LIMIT = 24
ALLOC = 0x0C00
MOD_ROOT = 0x0020
# BootLoad's MTOrg. MT[0] is the trap branch. MT[1] and MT[2] follow it.
MT_ORG = 0x20
# Page 0x10 (0x1000..0x10FF) is the code window: a word load there
# returns the pROM, not HyperRAM. The reserve starts at 0x2000, above
# that page and above the low map, and is the next 8000H bytes. The
# stack origin is 0xA000. The delay loop's push at R14-4 is the last
# word of the gap. sim/HyperRamUserModel.v covers it.
STACK = 0xA000
RESERVE = 0x8000
LIMIT = STACK - RESERVE
LOW_MARK = 0xA11A
HIGH_MARK = 0xE11D
PROOF = 0x05F0
PROOF_SKIP = 0x05E0
NONCE = 0xDEC0
MT1 = 0x50
MT2 = 0x70
BNE = 9
ALWAYS = 7
MI = 0
BT_R0 = 0xC7000000
BT_R1 = 0xC7000001
# F0 u=1 op MOV, Rd = R0. ORG.H(0) and the MOD arm of DivOp.
MOV_H = 0x20000000
# Word whose bit 0 is set. SYSTEM.BIT rotates right by bit+1 and tests MI.
BIT_ADDR = 0x05E8
BIT_WORD = 1
# Check's static base is MT[3]. res is at data+28H, the compiler's offset.
MOD_DATA = 0x0B00
RES_ADDR = MOD_DATA + 0x28
MT3 = MT_ORG + MOD_NUM * 4
BLINK_NAME = 0x0B40
BAD_NAME = 0x0B48
BLINK_LEN = 7  # "Blink5" plus 0X, ORS.slen
BAD_LEN = 5  # "9bad" plus 0X
BLINK_WORDS = (0x6E696C42, 0x0000356B)  # Blink5\0\0
BAD_WORDS = (0x64616239, 0x00000000)  # 9bad\0\0\0\0
# The placed body. Page 0x22 is the fetch window. Page 0x10 stays the
# pROM code window the copy loads from. The type word sits one page
# later, off the data table at 0x600 and off the stack ends.
PLACER = 0x1100
BODY_ORG = 0x2200
LOOP_SRC = 0x1048
LOOP_WORDS = (0x10AC - LOOP_SRC) // 4
BL_DISP = 0x108C - LOOP_SRC
BL_AT = BODY_ORG + BL_DISP
TOGGLE = 0x1000
FIX_GETSB = 0x8DC00008
GETSB_AT = BODY_ORG + (0x1054 - LOOP_SRC)
TYPE_DATA = 0x2300
TYPE_AT = TYPE_DATA + 4
# mno = 0, vno = 8, disp = 1. One step returns adr to TYPE_DATA.
TYPE_RAW = (8 << 12) | 1
TYPE_FIXED = TYPE_DATA + 8
_BL_OFF = (TOGGLE - BL_AT - 4) // 4
BL_WORD = 0xF7000000 | (_BL_OFF & 0xFFFFFF)


def _store_abs(a: Asm, addr: int, value: int | None) -> None:
    """Store an immediate, or R0 when value is None."""
    if value is not None:
        a.word(mov_imm(0, value))
    a.word(mov_imm(1, addr))
    a.word(stw(0, 1, 0))


def _load_abs(a: Asm, addr: int, rd: int) -> None:
    a.word(mov_imm(1, addr))
    a.word(ldw(rd, 1, 0))


def _f1s(op: int, rd: int, rb: int, imm: int) -> int:
    """F1 with the v bit set when the immediate is negative."""
    if not -0x8000 <= imm <= 0xFFFF:
        raise ValueError(imm)
    word = f1(op, rd, rb, imm & 0xFFFF)
    if imm < 0:
        word |= 0x10000000
    return word


def _fold(a: Asm) -> None:
    """IOR R0 into the difference accumulator R8."""
    a.word(f0(6, 8, 8, 0))


def _bl(a: Asm, name: str) -> None:
    def fn(pc: int, name: str = name) -> int:
        off = (a.labels[name] - (pc + 4)) // 4
        if not -0x800000 <= off < 0x800000:
            raise ValueError(f"BL to {name} is out of range")
        return 0xF7000000 | (off & 0xFFFFFF)

    a.at(fn)


def _call_check(a: Asm, name_addr: int, length: int, expect: int, tag: str) -> None:
    a.word(mov_imm(0, name_addr))
    a.word(mov_imm(1, length))
    _bl(a, "check")
    a.label(tag)
    _load_abs(a, RES_ADDR, 0)
    a.word(f1(9, 0, 0, expect))  # SUB R0, R0, expect
    _fold(a)


def _div_pair(a: Asm, expect_q: int) -> None:
    """R0 holds the dividend. Subtract the expected quotient and fold H."""
    if expect_q < 0:
        a.word(_f1s(9, 0, 0, expect_q))
    else:
        a.word(f1(9, 0, 0, expect_q))
    _fold(a)
    a.word(MOV_H)
    _fold(a)


def _div_checks(a: Asm, break_div: bool) -> None:
    """58 DIV 29 = 2, remainder 0, as F1 and as F0. Then -5 DIV 3 = -2, H = 1."""
    a.word(mov_imm(0, 58))
    a.word(f1(11, 0, 0, 29))
    _div_pair(a, 3 if break_div else 2)
    a.word(mov_imm(0, 58))
    a.word(mov_imm(1, 29))
    a.word(f0(11, 0, 0, 1))
    a.word(f1(9, 0, 0, 2))
    _fold(a)
    a.word(MOV_H)
    _fold(a)
    a.word(_f1s(0, 0, 0, -5))
    a.word(f1(11, 0, 0, 3))
    a.word(_f1s(9, 0, 0, -2))
    _fold(a)
    a.word(MOV_H)
    a.word(f1(9, 0, 0, 1))
    _fold(a)


def _bit_check(a: Asm, break_bit: bool) -> None:
    """SYSTEM.BIT of bit 0: LDW, ROR by 1, MI. A clear sign poisons R8."""
    a.word(mov_imm(0, 0 if break_bit else BIT_WORD))
    a.word(mov_imm(1, BIT_ADDR))
    a.word(stw(0, 1, 0))
    a.word(ldw(1, 1, 0))
    a.word(f1(3, 1, 1, 1))
    a.branch("bit_ok", MI)
    a.word(mov_imm(0, 1))
    _fold(a)
    a.label("bit_ok")


def install_word(trap: int, at: int = MT_ORG) -> int:
    """Kernel.Install: 0E7000000H + (Padr - at) DIV 4 - 1."""
    if (trap | at) & 3:
        raise ValueError(hex(trap), hex(at))
    off = (trap - at) // 4 - 1
    if not -0x800000 <= off < 0x800000:
        raise ValueError(off)
    return 0xE7000000 | (off & 0xFFFFFF)


def bl_r12(num: int) -> int:
    """ORG.Trap: BLR, condition always, trap number, register MT."""
    if not 0 <= num <= 15:
        raise ValueError(num)
    return 0xD7000000 | ((num & 0xF) << 4) | 0xC


def _ldw_signed(ra: int, rb: int, off: int) -> int:
    if not -0x80000 <= off < 0x80000:
        raise ValueError(off)
    return 0x80000000 | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | (off & 0xFFFFF)


def _load_abs_word(a: Asm, rd: int, value_at) -> None:
    """MHI/IOR of a word known once labels exist."""

    def hi(pc: int) -> int:
        word = value_at() & 0xFFFFFFFF
        return mhi(rd, word >> 16)

    def lo(pc: int) -> int:
        word = value_at() & 0xFFFFFFFF
        return f1(6, rd, rd, word & 0xFFFF)

    a.at(hi)
    a.at(lo)


def _install(a: Asm) -> None:
    """Store Install's branch at [R12] and fold it against the encoding."""
    a.at(lambda pc: mov_imm(1, a.labels["trap"]))
    a.word(f0(9, 0, 1, 12))
    a.word(f1(2, 0, 0, 2))
    a.word(f1(9, 0, 0, 1))
    a.word(mhi(3, 0xE700))
    a.word(f0(6, 4, 3, 0))
    a.word(stw(4, 12, 0))
    a.word(ldw(1, 12, 0))
    _load_abs_word(a, 3, lambda: install_word(a.labels["trap"]))
    a.word(f0(9, 0, 1, 3))
    _fold(a)


def _emit_trap_call(a: Asm, num: int) -> None:
    """Store the BL at its own address, then execute it.

    Trap's GET reads data memory. The fetch of the BL is the pROM word,
    and the two words are the same encoding.
    """
    word = bl_r12(num)
    a.at(lambda pc: mov_imm(1, a.labels["assert_bl"]))
    _load_abs_word(a, 0, lambda word=word: word)
    a.word(stw(0, 1, 0))
    a.label("assert_bl")
    a.word(word)


def _trap_body(a: Asm, hold: int) -> None:
    """Kernel.Trap's decode. Trap 0 returns. Anything else holds."""
    a.word(_ldw_signed(1, 15, -4))
    a.word(f1(2, 1, 1, 4))
    a.word(f1(4, 1, 1, 0xF))
    a.branch("trap_ret", 1)
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, ALWAYS))
    a.label("trap_ret")
    a.word(0xC700000F)


def assemble_body(
    hold: int,
    stub_return: int,
    reserve: int,
    proof: int,
    break_div: bool = False,
    break_bit: bool = False,
    trap_num: int | None = None,
    break_check: bool = False,
) -> tuple[list[int], dict[str, int]]:
    a = Asm()
    a.word(mov_imm(8, 0))
    _store_abs(a, ADDR_ALLOC, ALLOC)
    _store_abs(a, ADDR_ROOT, MOD_ROOT)
    _store_abs(a, ADDR_LIMIT, STACK)

    # Init reads the words back. The registers just written are not the proof.
    _load_abs(a, ADDR_ALLOC, 2)
    _load_abs(a, ADDR_ROOT, 3)
    _load_abs(a, ADDR_LIMIT, 4)
    # R14 is the stack origin, the top of the reserve, before DEC.
    a.word(f0(0, 14, 0, 4))
    a.word(f1(9, 4, 4, reserve))

    a.word(f1(9, 0, 2, ALLOC))
    a.word(f0(6, 8, 8, 0))
    a.word(f1(9, 0, 3, MOD_ROOT))
    a.word(f0(6, 8, 8, 0))
    a.word(f1(9, 0, 4, LIMIT))
    a.word(f0(6, 8, 8, 0))

    # The low end is the limit, above the code page. The high end is
    # the last word under R14, which is also where the delay loop's
    # existing push lands.
    _store_abs(a, LIMIT, LOW_MARK)
    _store_abs(a, STACK - 4, HIGH_MARK)
    _load_abs(a, LIMIT, 5)
    _load_abs(a, STACK - 4, 6)
    a.word(f1(9, 0, 5, LOW_MARK))
    a.word(f0(6, 8, 8, 0))
    a.word(f1(9, 0, 6, HIGH_MARK))
    a.word(f0(6, 8, 8, 0))

    # DIV, H, and SYSTEM.BIT. A wrong quotient, a wrong remainder, or a
    # clear sign after the rotate leaves R8 nonzero and the gate holds.
    _div_checks(a, break_div)
    _bit_check(a, break_bit)

    # Power-up memory is 0. A skipped store must not look like success,
    # so the stored word is the difference XOR a nonce.
    a.word(f1(7, 0, 8, NONCE))
    _store_abs(a, proof, None)

    # Addresses 16, 20, and 24 keep AllocPtr, root, and the stack origin.
    # R12 is 20H, so MT[1] and MT[2] are 0x24 and 0x28. Setup planted
    # 0x50 and 0x70 there, and the files block reinstalls them after it
    # restates R12. Install writes the trap branch at MT[0].
    a.word(mov_imm(12, MT_ORG))
    _install(a)

    # Compiled Modules.Check. R12 is 20H and R14 is still the stack
    # origin, so the 20-byte frame sits on the high end of the reserve.
    # The two results fold into the same R8 the gate already tests.
    _store_abs(a, MT3, MOD_DATA)
    for addr, word in (
        (BLINK_NAME, BLINK_WORDS[0]),
        (BLINK_NAME + 4, BLINK_WORDS[1]),
        (BAD_NAME, BAD_WORDS[0]),
        (BAD_NAME + 4, BAD_WORDS[1]),
    ):
        _store_abs(a, addr, word)
    _call_check(a, BLINK_NAME, BLINK_LEN, 1 if break_check else 0, "res_blink")
    _call_check(a, BAD_NAME, BAD_LEN, 1, "res_bad")

    a.word(f1(9, 0, 8, 0))
    a.label("gate")
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
    if trap_num is not None:
        _emit_trap_call(a, trap_num)
    a.word(mov_imm(0, PROLOGUE))
    a.word(BT_R0)

    # The step-7 store of the link slot branches here first. R11 is the
    # slot address and R8 is the file difference.
    a.label("stub")
    _load_abs(a, PROOF, 0)
    a.word(f1(7, 0, 0, NONCE))
    a.word(f0(6, NAME_ACC, NAME_ACC, 0))
    a.word(stw(NAME_ACC, 11, 0))
    a.at(lambda pc, back=stub_return: cond_branch(pc, back, ALWAYS))

    a.label("trap")
    _trap_body(a, hold)
    a.label("check")
    for word in load_inner()["check"]:
        a.word(word)

    prog = a.encode(BODY)
    end = BODY + len(prog) * 4
    if end > 0x1000:
        raise SystemExit(f"modules body ends at {end:#x}")
    return prog, dict(a.labels)


def _flush_store(words: list[int]) -> int:
    """The step-7 STW of the link-slot accumulator."""
    hits = []
    for addr in (0x89C, 0x8C0):
        marker = mov_imm(11, addr)
        for i, word in enumerate(words[:-1]):
            if word == marker and words[i + 1] == stw(NAME_ACC, 11, 0):
                hits.append((i + 1) * 4)
    if len(hits) != 1:
        raise SystemExit(f"expected one files proof store, found {hits}")
    return hits[0]


def _retarget_reset(words: list[int]) -> None:
    if words[0x9C // 4] != mov_imm(0, PROLOGUE):
        raise SystemExit(
            f"setup MOV at 0x9C is {words[0x9C // 4]:#x}, expected the prologue"
        )
    if words[0xA0 // 4] != BT_R0:
        raise SystemExit("setup does not branch through R0")
    words[0x9C // 4] = mov_imm(0, BODY)


def _retarget_r12(words: list[int]) -> None:
    """Setup and the files block both restate the module table base."""
    old = mov_imm(12, 0x10)
    new = mov_imm(12, MT_ORG)
    hits = [i * 4 for i, word in enumerate(words) if word == old]
    if hits != [0x80, FILES]:
        raise SystemExit(f"R12 = 0x10 sites {[hex(h) for h in hits]}")
    for addr in hits:
        words[addr // 4] = new


def _plant_vector(words: list[int], trap: int) -> None:
    idx = MT_ORG // 4
    if words[idx] != BEEF:
        raise SystemExit(f"ROM {MT_ORG:#x} is {words[idx]:#x}, expected filler")
    words[idx] = install_word(trap)


def assemble_placer(hold: int) -> tuple[list[int], dict[str, int]]:
    """Copy the fixed delay loop, walk one type entry, branch to it."""
    a = Asm()
    a.word(mov_imm(1, LOOP_SRC))
    a.word(mov_imm(2, BODY_ORG))
    a.word(mov_imm(3, LOOP_WORDS))
    a.label("copy")
    a.word(ldw(0, 1, 0))
    a.word(stw(0, 2, 0))
    a.word(f1(8, 1, 1, 4))
    a.word(f1(8, 2, 2, 4))
    a.word(f1(9, 3, 3, 1))
    a.branch("copy", BNE)

    # The copied BL still targets Toggle from 0x108C. Rewrite it.
    a.word(mov_imm(1, BL_AT))
    for w in load_const(0, BL_WORD):
        a.word(w)
    a.word(stw(0, 1, 0))

    # The GetSB the walker stored has to be the one that was copied.
    a.word(mov_imm(1, GETSB_AT))
    a.word(ldw(0, 1, 0))
    for w in load_const(4, FIX_GETSB):
        a.word(w)
    a.word(f0(9, 0, 0, 4))
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))

    # One global type entry. mno is 0, so the word becomes data + vno.
    a.word(mov_imm(1, TYPE_AT))
    a.word(mov_imm(0, TYPE_RAW))
    a.word(stw(0, 1, 0))
    a.word(mov_imm(4, TYPE_DATA))
    a.label("twalk")
    a.word(f0(9, 0, 1, 4))
    a.branch("tdone", 1)  # BEQ
    a.word(ldw(0, 1, 0))
    a.word(f0(0, 2, 0, 0))
    a.word(f1(2, 2, 2, 24))  # ASR 24
    a.word(f1(4, 2, 2, 0xF))
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
    a.word(f0(0, 3, 0, 0))
    a.word(f1(2, 3, 3, 12))  # ASR 12
    a.word(f1(4, 3, 3, 0xFFF))
    a.word(f0(8, 3, 4, 3))  # data + vno
    a.word(stw(3, 1, 0))
    a.word(f1(4, 0, 0, 0xFFF))  # disp
    a.word(f1(1, 0, 0, 2))  # * 4
    a.word(f0(9, 1, 1, 0))
    a.branch("twalk", ALWAYS)

    a.label("tdone")
    a.word(mov_imm(1, TYPE_AT))
    a.word(ldw(0, 1, 0))
    a.word(f1(9, 0, 0, TYPE_FIXED))
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
    a.word(mov_imm(1, BODY_ORG))
    a.label("enter")
    a.word(BT_R1)
    prog = a.encode(PLACER)
    end = PLACER + len(prog) * 4
    if end > 0x1200:
        raise SystemExit(f"placer ends at {end:#x}, prologue is 0x1200")
    return prog, dict(a.labels)


def modules_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
    skip_slot: int | None = None,
    mode: str = "all",
    break_dec: bool = False,
    fall: bool = False,
    skip_proof: bool = False,
    break_div: bool = False,
    break_bit: bool = False,
    trap_num: int | None = None,
    break_check: bool = False,
) -> tuple[list[int], dict[str, int], int]:
    words, labels, nprog = files_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        pad=pad,
        break_slot=break_slot,
        skip_slot=skip_slot,
        mode=mode,
    )
    store_pc = _flush_store(words)
    prog, local = assemble_body(
        labels["hold"],
        store_pc + 4,
        RESERVE + (1 if break_dec else 0),
        PROOF_SKIP if skip_proof else PROOF,
        break_div=break_div,
        break_bit=break_bit,
        trap_num=trap_num,
        break_check=break_check,
    )
    _place(words, BODY // 4, prog, 0x1000 // 4)
    if fall:
        gate = local["gate"]
        words[gate // 4] = f0(0, 1, 0, 1)
    words[store_pc // 4] = cond_branch(store_pc, local["stub"], ALWAYS)
    _retarget_reset(words)
    _retarget_r12(words)
    _plant_vector(words, local["trap"])
    place, placed = assemble_placer(labels["hold"])
    _place(words, PLACER // 4, place, 0x1200 // 4)
    go = labels["go"]
    if words[go // 4] != BT_R1:
        raise SystemExit(f"Load success at {go:#x} is not BT R1")
    words[go // 4] = cond_branch(go, PLACER, ALWAYS)
    labels = dict(labels)
    labels.update(local)
    labels.update(placed)
    labels["body"] = BODY
    labels["flush"] = store_pc
    labels["placer"] = PLACER
    labels["body_org"] = BODY_ORG
    return words, labels, len(prog)


def check_image(words: list[int], labels: dict[str, int], prog_len: int) -> None:
    hold = labels["hold"]
    if _b_target(0, words[0]) != hold or _b_target(4, words[1]) != hold:
        raise SystemExit("address 0 does not branch to the hold")
    if words[0x9C // 4] != mov_imm(0, BODY):
        raise SystemExit("reset does not enter the modules body")
    if words[0xA0 // 4] != BT_R0:
        raise SystemExit("setup lost BT R0")
    block = words[BODY // 4 : BODY // 4 + prog_len]
    if mov_imm(0, PROLOGUE) not in block or BT_R0 not in block:
        raise SystemExit("the body does not enter the prologue")
    if f1(9, 4, 4, RESERVE) not in block:
        raise SystemExit("DEC(limit, 8000H) is missing")
    if f1(9, 4, 4, 0x1000) in block:
        raise SystemExit("the 4 KB reserve is in the image")
    if mov_imm(1, LIMIT) not in block or mov_imm(1, STACK - 4) not in block:
        raise SystemExit("the reserve ends are not both addressed")
    if words[0x1048 // 4] != 0x4EE90004 or words[0x104C // 4] != 0xAFE00000:
        raise SystemExit("the delay loop push moved")
    if _b_target(labels["go"], words[labels["go"] // 4]) != PLACER:
        raise SystemExit("Load does not enter the placer")
    if words[PLACER // 4] != mov_imm(1, LOOP_SRC):
        raise SystemExit("the placer does not copy from the ROM loop")
    if words[labels["enter"] // 4] != BT_R1:
        raise SystemExit("the placer does not branch to the body")
    if BL_WORD in words:
        raise SystemExit("the relocated BL is a ROM fetch, not a stored immediate")
    if mov_imm(1, BODY_ORG) not in words[PLACER // 4 : 0x1200 // 4]:
        raise SystemExit("the placer does not address the placed body")
    if mov_imm(0, TYPE_RAW) not in words[PLACER // 4 : 0x1200 // 4]:
        raise SystemExit("the type entry is not planted")
    if mov_imm(1, PROOF) not in block:
        raise SystemExit("the proof word is not addressed")
    if words[labels["flush"] // 4] == stw(NAME_ACC, 11, 0):
        raise SystemExit("the files store does not enter the stub")
    if _b_target(labels["flush"], words[labels["flush"] // 4]) != labels["stub"]:
        raise SystemExit("the files store was not retargeted at the stub")
    # The delay loop's MHI is untouched, and 0x1048 is still not a MOV here.
    if any(word == mov_imm(0, 0x1048) for word in block):
        raise SystemExit("MOV of 0x1048 is in the modules body")
    if f1(11, 0, 0, 29) not in block or f0(11, 0, 0, 1) not in block:
        raise SystemExit("F1 and F0 DIV of 58 by 29 are not both in the body")
    if block.count(MOV_H) < 3:
        raise SystemExit("MOV from H is not in each divide check")
    if _f1s(0, 0, 0, -5) not in block or f1(11, 0, 0, 3) not in block:
        raise SystemExit("the floor division of -5 by 3 is missing")
    if f1(9, 0, 0, 3) in block:
        raise SystemExit("the broken quotient compare is in the clean image")
    bit_ok = labels["bit_ok"]
    if words[(bit_ok - 16) // 4] != f1(3, 1, 1, 1):
        raise SystemExit("SYSTEM.BIT does not ROR by bit+1")
    if words[(bit_ok - 12) // 4] != cond_branch(bit_ok - 12, bit_ok, MI):
        raise SystemExit("SYSTEM.BIT is not tested with MI")
    if mov_imm(1, BIT_ADDR) not in block or mov_imm(0, BIT_WORD) not in block:
        raise SystemExit("the known bit word is not stored")
    if bl_r12(0) in words or bl_r12(7) in words:
        raise SystemExit("the blink image executes a trap")
    if words[labels["res_blink"] // 4 + 2] != f1(9, 0, 0, 0):
        raise SystemExit("Blink5 is not expected to return res 0")
    check_trap(words, labels)
    check_compiled(words, labels, break_check=False)


def check_trap(words: list[int], labels: dict[str, int]) -> None:
    trap = labels["trap"]
    vector = install_word(trap)
    if words[MT_ORG // 4] != vector:
        raise SystemExit(f"ROM MT[0] is {words[MT_ORG // 4]:#x}, expected {vector:#x}")
    if _b_target(MT_ORG, vector) != trap:
        raise SystemExit("MT[0] does not branch to Trap")
    if words[0x80 // 4] != mov_imm(12, MT_ORG) or words[FILES // 4] != mov_imm(12, MT_ORG):
        raise SystemExit("R12 is not 20H in setup and in the files block")
    if mov_imm(12, 0x10) in words:
        raise SystemExit("a MOV R12, 0x10 remains")
    if words[trap // 4] != _ldw_signed(1, 15, -4):
        raise SystemExit("Trap does not load the instruction at R15-4")
    if words[trap // 4 + 1] != f1(2, 1, 1, 4) or words[trap // 4 + 2] != f1(4, 1, 1, 0xF):
        raise SystemExit("Trap does not decode DIV 10H MOD 10H")
    if words[labels["trap_ret"] // 4] != 0xC700000F:
        raise SystemExit("trap 0 does not return through R15")
    if stw(4, 12, 0) not in words[BODY // 4 : trap // 4]:
        raise SystemExit("Install does not store the branch at [R12]")
    if ldw(1, 12, 0) not in words[BODY // 4 : trap // 4]:
        raise SystemExit("Install does not read the branch back")


def check_compiled(words: list[int], labels: dict[str, int], break_check: bool) -> None:
    """The ROM slice is Norebo's Check, and the tail did not grow."""
    if EXTRA_CHECKS != 40:
        raise SystemExit(f"the tail is {EXTRA_CHECKS}, and 44 stays unloaded")
    core = load_inner()
    check = core["check"]
    at = labels["check"]
    got = words[at // 4 : at // 4 + len(check)]
    if got != check:
        raise SystemExit("ROM Check is not the compiled procedure")
    if check.count(0x8DC0000C) != 2:
        raise SystemExit("GetSB was not fixed to LDW R13, R12, 12")
    expect = 1 if break_check else 0
    if words[labels["res_blink"] // 4 + 2] != f1(9, 0, 0, expect):
        raise SystemExit(f"Blink5 expect is not {expect}")
    if words[labels["res_bad"] // 4 + 2] != f1(9, 0, 0, 1):
        raise SystemExit("9bad is not expected to return res 1")
    if mov_imm(0, MT3) not in words[BODY // 4 : at // 4] and mov_imm(1, MT3) not in words:
        raise SystemExit("MT[3] is not planted")
    if words[0x1048 // 4] != 0x4EE90004 or words[0x104C // 4] != 0xAFE00000:
        raise SystemExit("the delay loop push moved")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-8 Modules IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None)
    parser.add_argument("--skip-slot", type=int, default=None)
    parser.add_argument("--mode", choices=("all", "dir", "none"), default="all")
    parser.add_argument("--break-dec", action="store_true",
                        help="Subtract 8001H instead of 8000H")
    parser.add_argument("--fall", action="store_true",
                        help="Replace the Init branch to the hold with MOV R1, R1")
    parser.add_argument("--skip-proof", action="store_true",
                        help="Store the proof word at 0x5E0 so 0x5F0 stays 0")
    parser.add_argument("--break-div", action="store_true",
                        help="Expect quotient 3 so the DIV predicate fails")
    parser.add_argument("--break-bit", action="store_true",
                        help="Store a clear bit 0 so the MI predicate fails")
    parser.add_argument("--assert-false", action="store_true",
                        help="Sim only: BL R12 with trap 7 and hold the LED")
    parser.add_argument("--trap0", action="store_true",
                        help="Sim only: BL R12 with trap 0, then return")
    parser.add_argument("--break-check", action="store_true",
                        help="Sim only: expect res 1 from Check(Blink5)")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "modules.words"),
    )
    args = parser.parse_args()
    if args.assert_false and args.trap0:
        raise SystemExit("assert-false and trap0 are separate traces")
    trap_num = 7 if args.assert_false else 0 if args.trap0 else None
    src = os.path.join(ROOT, "tests", "final_system.code")
    words, labels, nprog = modules_imem(
        src,
        max_iter=args.max_iter,
        mov_iter=args.mov_iter,
        pad=args.pad,
        break_slot=args.break_slot,
        skip_slot=args.skip_slot,
        mode=args.mode,
        break_dec=args.break_dec,
        fall=args.fall,
        skip_proof=args.skip_proof,
        break_div=args.break_div,
        break_bit=args.break_bit,
        trap_num=trap_num,
        break_check=args.break_check,
    )
    clean = (
        args.break_slot is None
        and args.skip_slot is None
        and args.mode == "all"
        and not args.break_dec
        and not args.fall
        and not args.skip_proof
        and not args.break_div
        and not args.break_bit
        and not args.break_check
        and trap_num is None
    )
    if clean:
        check_image(words, labels, nprog)
    else:
        check_trap(words, labels)
        check_compiled(words, labels, break_check=args.break_check)
    if trap_num is not None and words[labels["assert_bl"] // 4] != bl_r12(trap_num):
        raise SystemExit("the trace BL is not ORG.Trap")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(
        "[ok] modules",
        EXTRA_CHECKS,
        "checks, body",
        hex(BODY),
        f"({nprog} words)",
        "gate",
        hex(labels["gate"]),
        "stub",
        hex(labels["stub"]),
        "flush",
        hex(labels["flush"]),
        "limit",
        hex(LIMIT),
        "check",
        hex(labels["check"]),
        "->",
        args.out,
    )
    if clean:
        for name, mod in load_inner()["modules"].items():
            print(f"[ok] {name}.rsc {mod['bytes']} bytes key {mod['key']:08X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
