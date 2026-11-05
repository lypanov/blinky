#!/usr/bin/env python3
"""Step 8 image: the Modules body is the reset path.

tests/BlinkModules.Mod is the formula. This host has no Oberon
compiler, so this file emits the ORG encodings. Reset still begins
at the setup block. The MOV at 0x9C enters this body instead of the
memory prologue. The body is

    GET(16); GET(20); GET(24); DEC(limit, 1000H); BT prologue

and the prologue's success path is still Load("Blink5"). The 4 KB
reserve is that DEC. R14 becomes the stack origin that was read, and
the delay loop's existing push lands inside the reserve. Nothing is
added inside the delay loop. chainFix stays on. The tail does not
grow: the proof word is XOR-ed into the step-7 store at the link slot.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_files_imem import EXTRA_CHECKS, NAME_ACC, files_imem  # noqa: E402
from build_hyperram_imem import (  # noqa: E402
    Asm,
    PROLOGUE,
    cond_branch,
    f0,
    f1,
    ldw,
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
# The behavioural HyperRAM is 8 KB. The reserve is the top 4 KB of
# that, so the delay loop's push at R14-4 stays inside the model.
STACK = 0x2000
RESERVE = 0x1000
LIMIT = STACK - RESERVE
PROOF = 0x05F0
PROOF_SKIP = 0x05E0
NONCE = 0xDEC0
MT1 = 0x50
MT2 = 0x70
BNE = 9
ALWAYS = 7
BT_R0 = 0xC7000000


def _store_abs(a: Asm, addr: int, value: int | None) -> None:
    """Store an immediate, or R0 when value is None."""
    if value is not None:
        a.word(mov_imm(0, value))
    a.word(mov_imm(1, addr))
    a.word(stw(0, 1, 0))


def _load_abs(a: Asm, addr: int, rd: int) -> None:
    a.word(mov_imm(1, addr))
    a.word(ldw(rd, 1, 0))


def assemble_body(
    hold: int,
    stub_return: int,
    reserve: int,
    proof: int,
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

    # Power-up memory is 0. A skipped store must not look like success,
    # so the stored word is the difference XOR a nonce.
    a.word(f1(7, 0, 8, NONCE))
    _store_abs(a, proof, None)

    # Address 20 and 24 are MT[1] and MT[2]. The prologue still requires
    # 0x50 and 0x70 there. Address 16 is restored to the power-up zero.
    _store_abs(a, ADDR_ALLOC, 0)
    _store_abs(a, ADDR_ROOT, MT1)
    _store_abs(a, ADDR_LIMIT, MT2)

    a.word(f1(9, 0, 8, 0))
    a.label("gate")
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
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
    )
    _place(words, BODY // 4, prog, 0x1000 // 4)
    if fall:
        gate = local["gate"]
        words[gate // 4] = f0(0, 1, 0, 1)
    words[store_pc // 4] = cond_branch(store_pc, local["stub"], ALWAYS)
    _retarget_reset(words)
    labels = dict(labels)
    labels.update(local)
    labels["body"] = BODY
    labels["flush"] = store_pc
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
        raise SystemExit("DEC(limit, 1000H) is missing")
    if f1(9, 4, 4, 0x8000) in block:
        raise SystemExit("the 32 KB reserve is in the image")
    if mov_imm(1, PROOF) not in block:
        raise SystemExit("the proof word is not addressed")
    if words[labels["flush"] // 4] == stw(NAME_ACC, 11, 0):
        raise SystemExit("the files store does not enter the stub")
    if _b_target(labels["flush"], words[labels["flush"] // 4]) != labels["stub"]:
        raise SystemExit("the files store was not retargeted at the stub")
    # The delay loop's MHI is untouched, and 0x1048 is still not a MOV here.
    if any(word == mov_imm(0, 0x1048) for word in block):
        raise SystemExit("MOV of 0x1048 is in the modules body")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-8 Modules IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None)
    parser.add_argument("--skip-slot", type=int, default=None)
    parser.add_argument("--mode", choices=("all", "dir", "none"), default="all")
    parser.add_argument("--break-dec", action="store_true",
                        help="Subtract 1001H instead of 1000H")
    parser.add_argument("--fall", action="store_true",
                        help="Replace the Init branch to the hold with MOV R1, R1")
    parser.add_argument("--skip-proof", action="store_true",
                        help="Store the proof word at 0x5E0 so 0x5F0 stays 0")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "modules.words"),
    )
    args = parser.parse_args()
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
    )
    clean = (
        args.break_slot is None
        and args.skip_slot is None
        and args.mode == "all"
        and not args.break_dec
        and not args.fall
        and not args.skip_proof
    )
    if clean:
        check_image(words, labels, nprog)
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
        "->",
        args.out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
