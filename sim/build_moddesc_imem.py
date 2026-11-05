#!/usr/bin/env python3
"""Step 6 image: ModDesc, the module table, and a procedure-variable call.

tests/BlinkMod.Mod is the source of the formulas. This host has no Oberon
compiler, so this file emits the ORG encodings. The image is the step-5
P/D-chain ROM plus one block in the free words after the walker. That
block is the only success path. Address 0 branches to the hold, so a
procedure variable of 0 does not enter Blink3.

The block poisons MT[1] and MT[2], fills two ModDesc records, and
installs each with Modules.Mod's

    SYSTEM.PUT(mod.num * 4 + MTOrg, mod.data)

MTOrg is R12 (0x10). It then computes the procedure variable the same
way Load calls a module body:

    body := mod.code + w

and executes BLR of that register. The procedure checks that R15 is the
link BLR planted, then enters LightToggle at 0x1048. A non-zero compare
branches to the step-5 hold and the pin stays dark.
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
    ldw,
    load_const,
    stw,
)
from build_pdchain_imem import (  # noqa: E402
    CHAIN,
    FIX_AMMT,
    FIX_BL,
    FIX_LT,
    FIX_ODD_ADD,
    _b_target,
    _place,
    pdchain_imem,
)
from imem_layout import (  # noqa: E402
    BEEF,
    blink3_imem,
    mov_imm,
    pad_imem,
    write_words,
)

# Free ROM begins at the step-5 walker's end. 66 words remain before 0x2000.
BLOCK = 0x1EF8
# ModDesc is 80 bytes (Modules.Mod DescSize). The records sit below the
# step-5 import anchor at 0x300.
AMMT_DESC = 0x240
LT_DESC = 0x2A0
ENTRY_W = 0x2F0
CHECK = 0x800
# 32 reader/ALU slots, five chain compares, then these three.
# Must match extraChecks for FPGA_IMAGE=moddesc.
EXTRA_CHECKS = 40
MT_SLOT = 37
BODY_SLOT = 38
LINK_SLOT = 39
BNE = 9
ALWAYS = 7
BLR_R1 = 0xD7000001
BT_R11 = 0xC700000B
SLOT_BASE = CHECK + 4 * MT_SLOT

# Modules.Mod field offsets.
OFF_NAME = 0
OFF_NEXT = 32
OFF_NUM = 40
OFF_DATA = 52
OFF_CODE = 56

# Big-endian name words: "LT" and "MM", then two zero bytes.
LT_NAME = 0x4C540000
AMMT_NAME = 0x4D4D0000
LT_NUM = 2
LT_DATA = 0x70
LT_CODE = 0x1048
AMMT_NUM = 1
AMMT_DATA = 0x50
AMMT_CODE = 0x1000
HOLD_LIMIT = 0x2000


def _store(a: Asm, base: int, offset: int, value: int) -> None:
    for word in load_const(0, value):
        a.word(word)
    a.word(stw(0, base, offset))


def assemble_moddesc(hold: int, break_slot: int | None) -> tuple[list[int], dict[str, int]]:
    """Fill, install, compare, then BLR. The pad checks the link."""

    def exp(slot: int, value: int) -> int:
        if break_slot == slot:
            return (value + 1) & 0xFFFFFFFF
        return value

    a = Asm()
    # The step-5 checks have already passed, so R10 is 0. Poison the
    # table the setup planted. The blink's GetSB then depends on install.
    a.word(mov_imm(0, 0))
    a.word(stw(0, 12, 4))
    a.word(stw(0, 12, 8))

    a.word(mov_imm(3, LT_DESC))
    _store(a, 3, OFF_NAME, LT_NAME)
    _store(a, 3, OFF_NEXT, AMMT_DESC)
    _store(a, 3, OFF_NUM, LT_NUM)
    _store(a, 3, OFF_DATA, LT_DATA)
    _store(a, 3, OFF_CODE, LT_CODE)
    a.at(lambda pc: mov_imm(0, (a.labels["pad"] - LT_CODE) & 0xFFFF))
    a.word(mov_imm(4, ENTRY_W))
    a.word(stw(0, 4, 0))

    a.word(mov_imm(3, AMMT_DESC))
    _store(a, 3, OFF_NAME, AMMT_NAME)
    _store(a, 3, OFF_NUM, AMMT_NUM)
    _store(a, 3, OFF_DATA, AMMT_DATA)
    _store(a, 3, OFF_CODE, AMMT_CODE)

    def call_install(desc: int) -> None:
        a.word(mov_imm(3, desc))
        a.at(lambda pc: mov_imm(11, pc + 8))
        a.branch("install", ALWAYS)

    call_install(LT_DESC)
    call_install(AMMT_DESC)

    # R11 stays SLOT_BASE through the three stores (offsets 0, 4, 8).
    a.word(ldw(1, 12, 8))
    a.word(f1(9, 5, 1, exp(MT_SLOT, LT_DATA)))
    a.word(ldw(1, 12, 4))
    a.word(f1(9, 0, 1, AMMT_DATA))
    a.word(f0(6, 5, 5, 0))
    a.word(mov_imm(11, SLOT_BASE))
    a.word(stw(5, 11, 0))
    a.word(f0(6, 10, 10, 5))

    a.word(mov_imm(3, LT_DESC))
    a.word(ldw(1, 3, OFF_CODE))
    a.word(mov_imm(4, ENTRY_W))
    a.word(ldw(0, 4, 0))
    a.word(f0(8, 1, 1, 0))
    a.at(lambda pc: f1(9, 0, 1, exp(BODY_SLOT, a.labels["pad"]) & 0xFFFF))
    a.word(stw(0, 11, 4))
    a.word(f0(6, 10, 10, 0))

    a.word(f1(9, 0, 10, 0))
    a.at(lambda pc: cond_branch(pc, hold, BNE))
    a.label("call")
    a.word(BLR_R1)
    a.label("link")
    a.at(lambda pc: cond_branch(pc, hold, ALWAYS))

    a.label("pad")
    a.at(lambda pc: mov_imm(6, exp(LINK_SLOT, a.labels["link"]) & 0xFFFF))
    a.word(f0(9, 0, 15, 6))
    a.word(stw(0, 11, 8))
    a.word(f0(6, 10, 10, 0))
    a.word(f1(9, 0, 10, 0))
    a.at(lambda pc: cond_branch(pc, hold, BNE))
    a.at(lambda pc: cond_branch(pc, LT_CODE, ALWAYS))

    a.label("install")
    a.word(ldw(8, 3, OFF_NUM))
    a.word(ldw(0, 3, OFF_DATA))
    a.word(f1(1, 8, 8, 2))
    a.word(f0(8, 8, 12, 8))
    a.word(stw(0, 8, 0))
    a.word(BT_R11)

    prog = a.encode(BLOCK)
    if BLOCK + len(prog) * 4 > HOLD_LIMIT:
        raise SystemExit(
            f"moddesc block is {len(prog)} words, "
            f"ends at {BLOCK + len(prog) * 4:#x}"
        )
    if a.labels["pad"] - LT_CODE > 0xFFFF:
        raise SystemExit("entry offset does not fit in one MOV")
    return prog, dict(a.labels)


def _retarget_success(words: list[int], hold: int) -> int:
    hits = [
        pc
        for pc in range(CHAIN, hold, 4)
        if _b_target(pc, words[pc // 4]) == 0
    ]
    if len(hits) != 1:
        raise SystemExit(f"expected one branch to address 0, found {hits}")
    pc = hits[0]
    words[pc // 4] = cond_branch(pc, BLOCK, ALWAYS)
    return pc


def moddesc_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
) -> tuple[list[int], dict[str, int]]:
    chain_break = break_slot if break_slot is not None and break_slot < MT_SLOT else None
    words, chain_labels = pdchain_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        break_slot=chain_break,
    )
    hold = chain_labels["hold"]
    local = break_slot if break_slot is not None and break_slot >= MT_SLOT else None
    prog, labels = assemble_moddesc(hold, local)
    need = HOLD_LIMIT // 4
    if len(words) < need:
        words.extend([BEEF] * (need - len(words)))
    _place(words, BLOCK // 4, prog, need)
    success = _retarget_success(words, hold)
    words[0] = cond_branch(0, hold, ALWAYS)
    words[1] = cond_branch(4, hold, ALWAYS)
    labels = dict(labels)
    labels["hold"] = hold
    labels["success"] = success
    if pad is not None:
        words = pad_imem(words, pad)
    return words, labels


def check_image(words: list[int], original: list[int], labels: dict[str, int]) -> None:
    if words[0x108C // 4] != 0xF7102011:
        raise SystemExit("ROM 0x108C is not the unfixed BL")
    if words[0x100C // 4] != 0x8D000003:
        raise SystemExit("ROM 0x100C is not the unfixed GetSB")
    for banned in (FIX_BL, FIX_AMMT, FIX_LT, FIX_ODD_ADD):
        if banned in words:
            raise SystemExit(f"fixed word {banned:#x} is in the ROM")
    for addr in (0x1000, 0x1048):
        if words[addr // 4] != original[addr // 4]:
            raise SystemExit(f"word at {addr:#x} changed")
    hold = labels["hold"]
    if _b_target(0, words[0]) != hold or _b_target(4, words[1]) != hold:
        raise SystemExit("address 0 still reaches Blink3")
    success = labels["success"]
    if _b_target(success, words[success // 4]) != BLOCK:
        raise SystemExit("chain success path does not reach the descriptor block")
    if any(_b_target(pc, words[pc // 4]) == 0 for pc in range(CHAIN, hold, 4)):
        raise SystemExit("a success branch to address 0 remains")
    call = labels["call"]
    if words[call // 4] != BLR_R1:
        raise SystemExit(f"procedure call at {call:#x} is {words[call // 4]:#x}")
    if labels["link"] != call + 4:
        raise SystemExit("BLR link is not the following word")
    if not any(
        _b_target(pc, words[pc // 4]) == LT_CODE
        for pc in range(labels["pad"], labels["install"], 4)
    ):
        raise SystemExit("the procedure does not enter LightToggle")
    end = labels["install"] + 6 * 4
    print(
        "[ok] moddesc",
        EXTRA_CHECKS,
        "checks, block",
        hex(BLOCK),
        "call",
        hex(call),
        "pad",
        hex(labels["pad"]),
        "entry",
        hex(LT_CODE),
        "w",
        hex(labels["pad"] - LT_CODE),
        "end",
        hex(end),
        f"({(end - BLOCK) // 4} words)",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-6 ModDesc IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None,
                        help="Sim only: add 1 to this expected constant")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "moddesc.words"),
    )
    args = parser.parse_args()
    src = os.path.join(ROOT, "tests", "final_system.code")
    original = blink3_imem(src)
    words, labels = moddesc_imem(
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
