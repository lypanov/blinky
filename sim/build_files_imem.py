#!/usr/bin/env python3
"""Step 7 image: Files serves two .rsc images, then Load calls Blink5.

tests/BlinkFiles.Mod and tests/Blink5.Mod are the formulas. This host
has no Oberon compiler, so this file builds the byte table and emits
the ORG encodings. The table is deposited in HyperRAM (it powers up
as zeros) and read back with LDB. The success path is

    body := 0x1000 + w
    BT body

with w = 0x48, so the body is the delay loop at 0x1048. That address
is not a branch target and not a MOV immediate. A zero file yields
body 0x1000, the compare against 0x48 is not zero, and the pin stays
dark. Address 0 still branches to the hold.

The new instructions sit in the free words at 0x00C0. The step-6 pad
used to branch to 0x1048; it now enters this block. The pad's store
of the link slot is removed. This block stores that slot, and the
stored word is the OR of the link difference and the file compares.
Nothing is added inside the delay loop. chainFix stays on.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    ldb,
    ldw,
    load_const,
    mov_imm,
    stw,
    write_words,
)
from build_moddesc_imem import LT_CODE, moddesc_imem  # noqa: E402
from build_pdchain_imem import (  # noqa: E402
    FIX_AMMT,
    FIX_BL,
    FIX_LT,
    FIX_ODD_ADD,
    _b_target,
    _place,
)

FILES = 0x00C0
# Above the prologue's series at 0x400 and 0x500, below the check
# slots at 0x7C0. The step-3 header at 0x900 is a different table.
DIR = 0x600
AMMT_BASE = 0x620
CODE_BASE = 0x1000
W_EXPECT = 0x48
AMMT_KEY = 0xA11CE001
BLINK5_KEY = 0xB1150005
AMMT_NAME = b"AMemoryMappedToggle\0"
BLINK5_NAME = b"Blink5\0"
MARKER = 0x4F
VERSION = 1
# The files result reuses step 6's link slot (0x89C). Adding tail bits
# past that missed the 27 MHz setup, and those bitstreams were not
# loaded. The pad's own store of this slot is removed; this block
# stores the OR of the link difference and the file compares.
LINK_SLOT = 39
EXTRA_CHECKS = 40
# Break ids. They bump one compare. The store is always LINK_SLOT.
NAME_SLOT = 40
META_SLOT = 41
W_SLOT = 42
MT_SLOT = 43
NAME_ACC = 8
META_ACC = 2
W_ACC = 9
BT_R1 = 0xC7000001
BT_R11 = 0xC700000B
BNE = 9
BEQ = 1
ALWAYS = 7
BANNED = (FIX_BL, FIX_AMMT, FIX_LT, FIX_ODD_ADD)


class Bump:
    def __init__(self, slot: int | None) -> None:
        self.slot = slot
        self.used = False

    def take(self, slot: int | None, value: int) -> int:
        if slot is not None and slot == self.slot and not self.used:
            self.used = True
            return (value + 1) & 0xFFFFFFFF
        return value


class Cursor:
    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.i = 0

    def byte(self, expected: int) -> int:
        got = self.blob[self.i]
        if got != expected:
            raise SystemExit(f"byte at {self.i:#x} is {got:#x}, expected {expected:#x}")
        self.i += 1
        return got

    def word(self, expected: int) -> int:
        got = int.from_bytes(self.blob[self.i : self.i + 4], "little")
        if got != (expected & 0xFFFFFFFF):
            raise SystemExit(f"word at {self.i:#x} is {got:#x}, expected {expected:#x}")
        self.i += 4
        return got

    def bytes(self, data: bytes) -> None:
        got = self.blob[self.i : self.i + len(data)]
        if got != data:
            raise SystemExit(f"bytes at {self.i:#x} are {got!r}, expected {data!r}")
        self.i += len(data)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def _s32(value: int) -> bytes:
    return struct.pack("<i", value)


def ammt_rsc() -> bytes:
    """Sections Load reads. No imports, no code, fixorgT is 0, w is 0."""
    return b"".join(
        [
            AMMT_NAME,
            _u32(AMMT_KEY),
            bytes([VERSION]),
            _u32(0x30),
            bytes([0]),
            _u32(0),
            _u32(4),
            _u32(0),
            _u32(0),
            bytes([0]),
            _u32(0),
            _s32(-1),
            _u32(0),
            _u32(0),
            _u32(0),
            _u32(0),
            bytes([MARKER]),
        ]
    )


def blink5_rsc() -> bytes:
    """Blink5 imports AMMT. w is 0x48. The code section is empty."""
    return b"".join(
        [
            BLINK5_NAME,
            _u32(BLINK5_KEY),
            bytes([VERSION]),
            _u32(0x40),
            AMMT_NAME,
            _u32(AMMT_KEY),
            bytes([0]),
            _u32(0),
            _u32(4),
            _u32(0),
            _u32(0),
            bytes([0]),
            _u32(0),
            _s32(-1),
            _u32(0),
            _u32(0),
            _u32(0),
            _u32(W_EXPECT),
            bytes([MARKER]),
        ]
    )


def _name_word(name: bytes) -> int:
    return int.from_bytes(name[:4], "little")


def directory_words(ammt: bytes, blink: bytes, blink_base: int) -> list[int]:
    return [
        _name_word(AMMT_NAME),
        AMMT_BASE,
        len(ammt),
        _name_word(BLINK5_NAME),
        blink_base,
        len(blink),
    ]


def pack_words(blob: bytes) -> list[int]:
    padded = blob + bytes((-len(blob)) % 4)
    return [
        int.from_bytes(padded[i : i + 4], "little") for i in range(0, len(padded), 4)
    ]


def parse_rsc(blob: bytes) -> dict:
    """The read sequence in Modules.Load, and nothing after the marker."""
    i = 0

    def rb() -> int:
        nonlocal i
        b = blob[i]
        i += 1
        return b

    def ri() -> int:
        x = 0
        for k in range(4):
            x |= rb() << (8 * k)
        return x

    def rs() -> bytes:
        raw = bytearray()
        while True:
            b = rb()
            if b == 0:
                return bytes(raw)
            raw.append(b)

    name = rs()
    key = ri()
    version = rb()
    size = ri()
    imports = []
    while True:
        imp = rs()
        if not imp:
            break
        imports.append((imp, ri()))
    td = ri()
    var = ri()
    strings = ri()
    code_n = ri()
    if code_n:
        raise SystemExit("the code section is not stored in the file")
    cmd = rb()
    entries = ri()
    ptr = ri()
    fixp, fixd, fixt = ri(), ri(), ri()
    w = ri()
    marker = rb()
    if i != len(blob):
        raise SystemExit(f"{len(blob) - i} bytes follow the marker")
    return {
        "name": name,
        "key": key,
        "version": version,
        "size": size,
        "imports": imports,
        "td": td,
        "var": var,
        "strings": strings,
        "code_n": code_n,
        "cmd": cmd,
        "entries": entries,
        "ptr": ptr,
        "fixorgP": fixp,
        "fixorgD": fixd,
        "fixorgT": fixt,
        "w": w,
        "marker": marker,
    }


def _check_files(ammt: bytes, blink: bytes) -> None:
    a = parse_rsc(ammt)
    b = parse_rsc(blink)
    if a["name"] != AMMT_NAME[:-1] or a["key"] != AMMT_KEY or a["version"] != 1:
        raise SystemExit(f"AMMT header {a}")
    if a["imports"] or a["fixorgT"] != 0 or a["w"] != 0 or a["marker"] != MARKER:
        raise SystemExit(f"AMMT tail {a}")
    if a["td"] or a["strings"] or a["code_n"] or a["cmd"] or a["entries"]:
        raise SystemExit(f"AMMT counts {a}")
    if a["var"] != 4 or a["ptr"] != 0xFFFFFFFF:
        raise SystemExit(f"AMMT var/ptr {a}")
    if b["name"] != BLINK5_NAME[:-1] or b["key"] != BLINK5_KEY or b["version"] != 1:
        raise SystemExit(f"Blink5 header {b}")
    if b["imports"] != [(AMMT_NAME[:-1], AMMT_KEY)]:
        raise SystemExit(f"Blink5 imports {b['imports']}")
    if b["fixorgT"] != 0 or b["w"] != W_EXPECT or b["marker"] != MARKER:
        raise SystemExit(f"Blink5 tail {b}")
    if b["code_n"] != 0:
        raise SystemExit("Blink5 code count is not 0")
    # The nested Files.ReadInt formula, which the subroutine below implements
    # as three LSL 8 adds rather than one LSL 24.
    sample = (0x01, 0xE0, 0x1C, 0xA1)
    acc = sample[0]
    acc += sample[1] << 8
    acc += sample[2] << 16
    acc += sample[3] << 24
    if acc != AMMT_KEY:
        raise SystemExit(f"ReadInt formula produced {acc:#x}")


def _call_readint(a: Asm) -> None:
    a.at(lambda pc: mov_imm(11, pc + 8))
    a.branch("readint", ALWAYS)


def _expect_name(a: Asm, cur: Cursor, text: bytes, acc: int, bump: Bump, slot: int | None) -> None:
    cur.bytes(text)
    # The cursor already consumed the bytes. Replay them from `text`.
    raw = text[:-1]
    first = True
    off = 0
    while off + 4 <= len(raw):
        value = int.from_bytes(raw[off : off + 4], "little")
        shown = bump.take(slot, value) if first else value
        _call_readint(a)
        for w in load_const(1, shown):
            a.word(w)
        a.word(f0(9, 0, 0, 1))
        a.word(f0(6, acc, acc, 0))
        off += 4
        first = False
    for b in list(raw[off:]) + [0]:
        shown = (bump.take(slot, b) if first else b) & 0xFF
        a.word(ldb(0, 3, 0))
        a.word(f1(8, 3, 3, 1))
        a.word(f1(9, 0, 0, shown))
        a.word(f0(6, acc, acc, 0))
        first = False


def _expect_byte(a: Asm, cur: Cursor, expected: int, acc: int, bump: Bump, slot: int | None) -> None:
    cur.byte(expected)
    shown = bump.take(slot, expected) & 0xFF
    a.word(ldb(0, 3, 0))
    a.word(f1(8, 3, 3, 1))
    a.word(f1(9, 0, 0, shown))
    a.word(f0(6, acc, acc, 0))


def _skip_int(a: Asm, cur: Cursor, expected: int) -> None:
    cur.word(expected)
    _call_readint(a)


def _check_key(a: Asm, cur: Cursor, expected: int, save: bool) -> None:
    """ReadInt, optionally keep it in R7, and subtract the immediate."""
    cur.word(expected)
    _call_readint(a)
    if save:
        a.word(f0(0, 7, 0, 0))
        for w in load_const(1, expected):
            a.word(w)
        a.word(f0(9, 0, 7, 1))
    else:
        for w in load_const(1, expected):
            a.word(w)
        a.word(f0(9, 0, 0, 1))
    a.word(f0(6, META_ACC, META_ACC, 0))


def _walk_tail(a: Asm, cur: Cursor, bump: Bump, check_w: bool) -> None:
    # Counts are byte or word counts. A zero count has no payload in the
    # file. Variable bytes are allocated, not stored. fixorgT is 0, so
    # there is no type chain to chase.
    _skip_int(a, cur, 0)
    _skip_int(a, cur, 4)
    _skip_int(a, cur, 0)
    _skip_int(a, cur, 0)
    _expect_byte(a, cur, 0, META_ACC, bump, None)
    _skip_int(a, cur, 0)
    _skip_int(a, cur, 0xFFFFFFFF)
    _skip_int(a, cur, 0)
    _skip_int(a, cur, 0)
    _skip_int(a, cur, 0)
    if check_w:
        cur.word(W_EXPECT)
        _call_readint(a)
        a.word(f0(0, 6, 0, 0))
        shown = bump.take(W_SLOT, W_EXPECT)
        a.word(f1(9, 0, 6, shown))
        a.word(f0(6, W_ACC, W_ACC, 0))
    else:
        _skip_int(a, cur, 0)
    _expect_byte(a, cur, MARKER, META_ACC, bump, None)


def _deposit(a: Asm, base: int, words: list[int]) -> None:
    for w in load_const(4, base):
        a.word(w)
    for i, val in enumerate(words):
        for w in load_const(0, val):
            a.word(w)
        a.word(stw(0, 4, i * 4))


def _old(a: Asm, hold: int, name_word: int, tag: str) -> None:
    """R3 = the directory base whose name word matches, else the hold.

    Entry layout is name, base, length. A zero directory matches neither
    name, so a skipped deposit never starts the rider.
    """
    for w in load_const(4, DIR):
        a.word(w)
    a.word(ldw(0, 4, 0))
    for w in load_const(1, name_word):
        a.word(w)
    a.word(f0(9, 0, 0, 1))
    a.branch(f"hit0_{tag}", BEQ)
    a.word(ldw(0, 4, 12))
    for w in load_const(1, name_word):
        a.word(w)
    a.word(f0(9, 0, 0, 1))
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
    a.word(ldw(3, 4, 16))
    a.branch(f"have_{tag}", ALWAYS)
    a.label(f"hit0_{tag}")
    a.word(ldw(3, 4, 4))
    a.label(f"have_{tag}")


def _flush(a: Asm, reg: int, skip_slot: int | None) -> None:
    # Any requested skip moves the proof store off the link slot.
    addr = 0x8C0 if skip_slot is not None else 0x800 + 4 * LINK_SLOT
    a.word(mov_imm(11, addr))
    a.word(stw(reg, 11, 0))
    a.word(f0(6, 10, 10, reg))


def assemble_files(
    hold: int,
    ammt: bytes,
    blink: bytes,
    blink_base: int,
    mode: str,
    break_slot: int | None,
    skip_slot: int | None,
) -> tuple[list[int], dict[str, int]]:
    a = Asm()
    bump = Bump(break_slot)
    # R12 is the module table. Restate it so a clobber earlier in the
    # image cannot aim the reinstall at some other base.
    a.word(mov_imm(12, 0x10))
    a.word(mov_imm(0, 0))
    a.word(stw(0, 12, 4))
    a.word(stw(0, 12, 8))
    a.word(mov_imm(NAME_ACC, 0))
    a.word(mov_imm(META_ACC, 0))
    a.word(mov_imm(W_ACC, 0))
    a.word(mov_imm(10, 0))

    if mode in ("all", "dir"):
        _deposit(a, DIR, directory_words(ammt, blink, blink_base))
    if mode == "all":
        _deposit(a, AMMT_BASE, pack_words(ammt))
        _deposit(a, blink_base, pack_words(blink))

    _old(a, hold, _name_word(AMMT_NAME), "ammt")
    cur = Cursor(ammt)
    _expect_name(a, cur, AMMT_NAME, NAME_ACC, bump, None)
    _check_key(a, cur, AMMT_KEY, save=True)
    _expect_byte(a, cur, VERSION, META_ACC, bump, None)
    _skip_int(a, cur, 0x30)
    _expect_byte(a, cur, 0, NAME_ACC, bump, None)
    _walk_tail(a, cur, bump, check_w=False)
    if cur.i != len(ammt):
        raise SystemExit(f"AMMT walk stopped at {cur.i}, length {len(ammt)}")

    _old(a, hold, _name_word(BLINK5_NAME), "b5")
    cur = Cursor(blink)
    _expect_name(a, cur, BLINK5_NAME, NAME_ACC, bump, NAME_SLOT)
    _check_key(a, cur, BLINK5_KEY, save=False)
    _expect_byte(a, cur, VERSION, META_ACC, bump, META_SLOT)
    _skip_int(a, cur, 0x40)
    _expect_name(a, cur, AMMT_NAME, NAME_ACC, bump, None)
    cur.word(AMMT_KEY)
    _call_readint(a)
    a.word(f0(9, 0, 0, 7))
    a.word(f0(6, META_ACC, META_ACC, 0))
    _expect_byte(a, cur, 0, NAME_ACC, bump, None)
    _walk_tail(a, cur, bump, check_w=True)
    if cur.i != len(blink):
        raise SystemExit(f"Blink5 walk stopped at {cur.i}, length {len(blink)}")

    # Load's PUT, with the resident data addresses. The bytes do not
    # carry 0x50 or 0x70. The values are loaded back before the compare.
    a.word(mov_imm(0, 0x50))
    a.word(stw(0, 12, 4))
    a.word(mov_imm(0, 0x70))
    a.word(stw(0, 12, 8))
    a.word(mov_imm(4, 0))
    a.word(ldw(0, 12, 4))
    a.word(f1(9, 0, 0, bump.take(MT_SLOT, 0x50) & 0xFFFF))
    a.word(f0(6, 4, 4, 0))
    a.word(ldw(0, 12, 8))
    a.word(f1(9, 0, 0, 0x70))
    a.word(f0(6, 4, 4, 0))

    a.word(f0(6, NAME_ACC, NAME_ACC, META_ACC))
    a.word(f0(6, NAME_ACC, NAME_ACC, W_ACC))
    a.word(f0(6, NAME_ACC, NAME_ACC, 4))
    # R5 is the pad's link difference. The pad did not store the slot.
    a.word(f0(6, NAME_ACC, NAME_ACC, 5))
    _flush(a, NAME_ACC, skip_slot)

    # w is in R6. Adding the host code base is the only path to the loop.
    a.word(f1(8, 1, 6, CODE_BASE))
    a.word(f1(9, 0, 10, 0))
    a.at(lambda pc, hold=hold: cond_branch(pc, hold, BNE))
    a.label("go")
    a.word(BT_R1)

    a.label("readint")
    a.word(ldb(0, 3, 0))
    a.word(ldb(1, 3, 1))
    a.word(f1(1, 1, 1, 8))
    a.word(f0(8, 0, 0, 1))
    a.word(ldb(1, 3, 2))
    a.word(f1(1, 1, 1, 8))
    a.word(f1(1, 1, 1, 8))
    a.word(f0(8, 0, 0, 1))
    a.word(ldb(1, 3, 3))
    a.word(f1(1, 1, 1, 8))
    a.word(f1(1, 1, 1, 8))
    a.word(f1(1, 1, 1, 8))
    a.word(f0(8, 0, 0, 1))
    a.word(f1(8, 3, 3, 4))
    a.word(BT_R11)

    prog = a.encode(FILES)
    end = FILES + len(prog) * 4
    if end > 0x1000:
        raise SystemExit(f"files block is {len(prog)} words, ends at {end:#x}")
    if (
        bump.slot is not None
        and bump.slot >= NAME_SLOT
        and not bump.used
    ):
        raise SystemExit(f"break slot {bump.slot} matched no constant")
    return prog, dict(a.labels)


def _branches_to(words: list[int], target: int) -> list[int]:
    return [
        pc
        for pc in range(0, len(words) * 4, 4)
        if _b_target(pc, words[pc // 4]) == target
    ]


def _mov_immediates(word: int) -> list[int]:
    top = word >> 28
    if top == 4 and ((word >> 16) & 0xF) == 0:
        return [word & 0xFFFF]
    if top == 6:
        return [(word & 0xFFFF) << 16]
    return []


def check_image(words: list[int], labels: dict[str, int], prog_len: int) -> None:
    hold = labels["hold"]
    if _b_target(0, words[0]) != hold or _b_target(4, words[1]) != hold:
        raise SystemExit("address 0 does not branch to the hold")
    if words[0x108C // 4] != 0xF7102011:
        raise SystemExit("ROM 0x108C is not the BL placeholder")
    for banned in BANNED:
        if banned in words:
            raise SystemExit(f"banned fixed word {banned:#x} is in the ROM")
    if 0xF7000409 in words or 0xF7000410 in words:
        raise SystemExit("address 0 still has the Blink3 trampoline")
    if 0xD7000001 not in words:
        raise SystemExit("BLR R1 is missing")
    pad_hits = [
        pc
        for pc in range(labels["pad"], labels["install"], 4)
        if _b_target(pc, words[pc // 4]) == FILES
    ]
    if pad_hits != [labels["pad_branch"]]:
        raise SystemExit(f"pad does not enter the files block: {pad_hits}")
    stray = [
        pc
        for pc in _branches_to(words, LT_CODE)
        if not 0x1000 <= pc < 0x1C00
    ]
    if stray:
        raise SystemExit(f"branch to {LT_CODE:#x} outside the module image: {stray}")
    block = words[FILES // 4 : FILES // 4 + prog_len]
    if BT_R1 not in block:
        raise SystemExit("the files block has no BT R1")
    if words[labels["go"] // 4] != BT_R1:
        raise SystemExit("the success word is not BT R1")
    for word in block:
        if LT_CODE in _mov_immediates(word):
            raise SystemExit(f"MOV of {LT_CODE:#x} is in the files block")
    if f1(8, 1, 6, CODE_BASE) not in block:
        raise SystemExit("body is not R6 + 0x1000")
    # The delay loop's MHI or MOV still has to be the only way to count.
    if words[0x9C // 4] != mov_imm(0, 0x1200):
        raise SystemExit("prologue entry was overwritten")
    if stw(0, 11, 8) in words[labels["pad"] // 4 : labels["install"] // 4]:
        raise SystemExit("the pad still stores the link slot")
    if f0(0, 5, 0, 0) not in words[labels["pad"] // 4 : labels["install"] // 4]:
        raise SystemExit("the pad does not keep the link difference")
    if mov_imm(11, 0x800 + 4 * LINK_SLOT) not in block:
        raise SystemExit("the files block does not address the link slot")


def _defer_link_store(words: list[int], labels: dict[str, int]) -> int:
    """Drop the pad's STW of slot 39. The files block stores that bit."""
    store = stw(0, 11, 8)
    hits = [
        pc
        for pc in range(labels["pad"], labels["install"], 4)
        if words[pc // 4] == store
    ]
    if len(hits) != 1:
        raise SystemExit(f"expected one link-slot store in the pad, found {hits}")
    pc = hits[0]
    # R0 is the link difference. Keep it in R5; this block does not write R5.
    words[pc // 4] = f0(0, 5, 0, 0)
    return pc


def files_imem(
    final_system: str,
    max_iter: int | None = None,
    mov_iter: int | None = None,
    pad: int | None = None,
    break_slot: int | None = None,
    skip_slot: int | None = None,
    mode: str = "all",
) -> tuple[list[int], dict[str, int], int]:
    ammt = ammt_rsc()
    blink = blink5_rsc()
    _check_files(ammt, blink)
    blink_base = (AMMT_BASE + len(ammt) + 15) & ~15
    end = blink_base + len(blink)
    if end >= 0x7C0 or DIR < 0x580:
        raise SystemExit(f"byte table {DIR:#x}..{end:#x} collides with a resident region")
    md_break = break_slot if break_slot is not None and break_slot < NAME_SLOT else None
    words, labels = moddesc_imem(
        final_system,
        max_iter=max_iter,
        mov_iter=mov_iter,
        pad=pad,
        break_slot=md_break,
    )
    before = _branches_to(words, LT_CODE)
    prog, local = assemble_files(
        labels["hold"],
        ammt,
        blink,
        blink_base,
        mode,
        break_slot,
        skip_slot,
    )
    _place(words, FILES // 4, prog, 0x1000 // 4)
    _defer_link_store(words, labels)
    pad_hits = [pc for pc in before if labels["pad"] <= pc < labels["install"]]
    if len(pad_hits) != 1:
        raise SystemExit(f"expected one pad branch to {LT_CODE:#x}, found {pad_hits}")
    pc = pad_hits[0]
    words[pc // 4] = cond_branch(pc, FILES, ALWAYS)
    labels = dict(labels)
    labels.update(local)
    labels["pad_branch"] = pc
    labels["blink_base"] = blink_base
    labels["ammt_len"] = len(ammt)
    labels["blink_len"] = len(blink)
    return words, labels, len(prog)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the step-7 Files IMEM")
    parser.add_argument("--max-iter", type=int, default=None)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=None)
    parser.add_argument("--break-slot", type=int, default=None)
    parser.add_argument("--skip-slot", type=int, default=None,
                        help="Store this slot at 0x8C0 so its tail bit stays clear")
    parser.add_argument("--mode", choices=("all", "dir", "none"), default="all")
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "sim", "visualizer", "imem", "files.words"),
    )
    args = parser.parse_args()
    if args.break_slot is not None and args.skip_slot is not None:
        raise SystemExit("break-slot and skip-slot are separate images")
    src = os.path.join(ROOT, "tests", "final_system.code")
    words, labels, nprog = files_imem(
        src,
        max_iter=args.max_iter,
        mov_iter=args.mov_iter,
        pad=args.pad,
        break_slot=args.break_slot,
        skip_slot=args.skip_slot,
        mode=args.mode,
    )
    if args.break_slot is None and args.skip_slot is None and args.mode == "all":
        check_image(words, labels, nprog)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_words(args.out, words)
    print(
        "[ok] files",
        EXTRA_CHECKS,
        "checks, block",
        hex(FILES),
        f"({nprog} words)",
        "pad",
        hex(labels["pad_branch"]),
        "go",
        hex(labels["go"]),
        "ammt",
        labels["ammt_len"],
        "blink5",
        labels["blink_len"],
        "at",
        hex(labels["blink_base"]),
        "w",
        hex(W_EXPECT),
        "->",
        args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
