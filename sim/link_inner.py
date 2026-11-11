#!/usr/bin/env python3
"""Prelinked inner core for Proof 7.

Reset enters a short stub. The stub plants addresses 12, 16, 20, and 24,
the module table, and the static data, then branches to the real
Modules body. Files.Init, Kernel.Init, and FileDir.Init are the compiled
procedures. Load("Blink5") reads the two .rsc files through the sector ROM.

The instruction ROM is one 4096-word array. It holds the stub, the packed
reachable code, the init stream, and the three sector pages. A second read
port serves GetSector while the first port is the fetch. HyperRAM keeps
the other two blocks, so the Nano 4K stays at 10.

Blink5's placed code starts with the arm sequence. Address 28 holds the
sum of that code after Load's fixups. The LED arms only if the store at
0x7C0 is 0xA11C0DE5.
"""
from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from build_hyperram_imem import Asm, cond_branch, f0, f1, ldw, load_const, mhi, stw  # noqa: E402
from inner_core import ORDER, load_inner  # noqa: E402
from rsc_parser import ImportedModule, fixup_bl, fixup_ldr_str_add, parse_rsc  # noqa: E402
from sector_image import (  # noqa: E402
    AMMT_SEC,
    BLINK_CONT,
    BLINK_SEC,
    DIR_ROOT,
    HEADER_SIZE,
    RATE_NAME,
    RATE_SEC,
    SECTOR,
    _dir_page,
    _file_pages,
    _header,
    rate_page,
    rom_words,
)

CORE_BASE = 0x18000
INIT_BASE = 0x20000
STUB_PC = 0x80
ALLOC = 0x2000
STACK = 0xC000
# The heap is the gap from the stack origin up to MemLim.
# Files.Old takes a 1280-byte buffer and a 512-byte descriptor.
# The two modules take that pair, and Blink.Rate takes it once more
# (5376). Blink5 continues on a second page, and ReadBuf reuses that
# one buffer, so the page does not take another block. 5632 bytes
# leaves eight 32-byte records. head takes one. The eighth on-edge
# finds none.
FILE_BYTES = 1280 + 512
HEAP_BYTES = FILE_BYTES * 3 + 32 * 8
MEMLIM = STACK + HEAP_BYTES
EXHAUST_RISES = 8
LIMIT = STACK - 0x8000
BODY_LO = ALLOC
BODY_HI = LIMIT
ROM_WORDS = 4096
DESC_SIZE = 80
MAP_PATH = os.path.join(ROOT, "sim", "visualizer", "imem", "core.map")
PAYLOAD = os.path.join(ROOT, "sim", "payload")
NUM = {"Kernel": 1, "FileDir": 2, "Files": 3, "Modules": 4}


def _code_origin(data: bytes) -> tuple[int, int]:
    end = data.index(b"\0")
    off = end + 1 + 4 + 1 + 4
    while data[off] != 0:
        end = data.index(b"\0", off)
        off = end + 1 + 4
    off += 1
    td = struct.unpack_from("<I", data, off)[0]
    off += 4 + td
    off += 4
    strx = struct.unpack_from("<I", data, off)[0]
    off += 4 + strx
    ncode = struct.unpack_from("<I", data, off)[0]
    return off + 4, ncode


def _f1_r15(inst: int) -> tuple[int, int] | None:
    """(op, imm) when this is ADD/SUB of R15 with u = 0. None otherwise."""
    if (inst >> 30) != 1 or ((inst >> 29) & 1) != 0:
        return None
    if ((inst >> 20) & 0xF) != 15:
        return None
    op = (inst >> 16) & 0xF
    if op not in (8, 9):
        return None
    imm = inst & 0xFFFF
    if ((inst >> 28) & 1) and imm & 0x8000:
        imm -= 0x10000
    return op, imm


def _sx24(off: int) -> int:
    off &= 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return off


def _locate(addr: int, bases: dict[str, int], lengths: dict[str, int]) -> tuple[str, int]:
    for name in ORDER:
        base = bases[name]
        if base <= addr < base + lengths[name] * 4 and (addr - base) % 4 == 0:
            return name, (addr - base) // 4
    raise SystemExit(f"branch target {addr:#x} is outside the inner core")


def _d_proc_sites(code: list[int], fix_d: int) -> list[tuple[int, int, int]]:
    sites = []
    adr = fix_d * 4
    seen = set()
    while adr != 0 and adr not in seen:
        seen.add(adr)
        index = adr // 4
        inst = code[index]
        mno = (inst // 0x100000) % 0x10
        disp = inst % 0x1000
        if mno != 0 and index + 1 < len(code):
            nxt = code[index + 1]
            if ((nxt // 0x100) % 2) == 1:
                sites.append((index + 1, mno, nxt % 0x100))
        if disp == 0:
            break
        adr -= disp * 4
    return sites


def _walk(codes, bases, lengths, seeds: set[tuple[str, int]]) -> set[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    stack = list(seeds)
    while stack:
        name, index = stack.pop()
        if (name, index) in seen:
            continue
        if index < 0 or index >= lengths[name]:
            raise SystemExit(f"control left {name} at word {index}")
        seen.add((name, index))
        inst = codes[name][index]
        if (inst >> 30) != 3:
            stack.append((name, index + 1))
            continue
        link = (inst >> 28) & 1
        cond = (inst >> 24) & 0xF
        offset_mode = (inst >> 29) & 1
        always = cond == 7
        never = cond == 15
        if offset_mode and not never:
            target = bases[name] + index * 4 + 4 + _sx24(inst) * 4
            stack.append(_locate(target & 0xFFFFFFFF, bases, lengths))
        if (not always) or link or never:
            stack.append((name, index + 1))
    return seen


def _sub_sp(inst: int) -> bool:
    return (inst >> 30) == 1 and ((inst >> 24) & 0xF) == 0xE and ((inst >> 20) & 0xF) == 14 and ((inst >> 16) & 0xF) == 9


def _compile_payload() -> dict[str, dict]:
    os.makedirs(PAYLOAD, exist_ok=True)
    # Blink5 imports Kernel and Modules. The symbol files are the inner-core
    # compile, so the keys match the modules the bootstrap plants.
    cache = os.path.join(ROOT, "sim", "inner-core")
    for name in ("Kernel", "FileDir", "Files", "Modules"):
        src = os.path.join(cache, f"{name}.smb")
        if not os.path.isfile(src):
            raise SystemExit(f"missing {src}; compile the inner core first")
        open(os.path.join(PAYLOAD, f"{name}.smb"), "wb").write(open(src, "rb").read())
    for name in ("AMemoryMappedToggle", "Blink5"):
        src = os.path.join(ROOT, "tests", f"{name}.Mod")
        dst = os.path.join(PAYLOAD, f"{name}.Mod")
        open(dst, "wb").write(open(src, "rb").read())
    script = f"""
set -euo pipefail
source "{ROOT}/tools/norebo_env.sh"
if ! norebo_export; then
  "{ROOT}/tools/setup_norebo.sh"
  norebo_export
fi
cd "{PAYLOAD}"
"$NOREBO_BIN" ORP.Compile AMemoryMappedToggle.Mod/s
"$NOREBO_BIN" ORP.Compile Blink5.Mod/s
"""
    out = subprocess.check_output(["bash", "-c", script], stderr=subprocess.STDOUT)
    text = out.decode("latin1", errors="replace")
    if "compilation FAILED" in text or "not found" in text:
        raise SystemExit(text)
    mods = {}
    for name in ("AMemoryMappedToggle", "Blink5"):
        path = os.path.join(PAYLOAD, f"{name}.rsc")
        parsed = parse_rsc(path, output_format="quiet")
        parsed["raw"] = open(path, "rb").read()
        if parsed["version"] != 1:
            raise SystemExit(f"{name} version {parsed['version']}")
        if len(parsed["raw"]) > SECTOR - HEADER_SIZE + SECTOR:
            raise SystemExit(
                f"{name}.rsc is {len(parsed['raw'])} bytes; "
                f"a header and one continuation hold {SECTOR - HEADER_SIZE + SECTOR}"
            )
        mods[name] = parsed
    print(text, end="")
    return mods


# 1000 ms between toggles. Two toggles are one blink: 2.000 s, 0.500 Hz.
# The Dock's millisecond is 24187.5 cpu clocks, so an even wait closes
# on a whole pair and the edge spacing does not alternate.
WAIT_MS = 1000


def _is_wait_mov(word: int) -> bool:
    """MOV Rd, 1000. rb and op are 0; the register is free."""
    return (word & 0xF0FF0000) == 0x40000000 and (word & 0xFFFF) == WAIT_MS


def _kernel_time(code: list[int], entries: list[int]) -> tuple[int, int]:
    """Word index of Kernel.Time, and the word index of its MOV -64.

    ORG.Put1 sign-extends a negative immediate, so the address of the
    timer is MOV Rd, -64 (v=1, imm 0xFFC0) followed by a load through it.
    """
    hits = [i for i, word in enumerate(code) if (word & 0xF0FFFFFF) == 0x5000FFC0]
    if len(hits) != 1:
        raise SystemExit(f"Kernel has {len(hits)} MOV -64 words, wanted Time's timer address")
    at = hits[0]
    starts = [entry // 4 for entry in entries if entry % 4 == 0 and entry // 4 <= at]
    if not starts:
        raise SystemExit("no Kernel entry covers the timer load")
    return max(starts), at


def _bl_target(index: int, word: int) -> int:
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return index + 1 + off


def _proc_starts(code: list[int], entries: list[int]) -> list[tuple[int, int]]:
    """(entry number, word index) for entries whose first word is SUB SP, SP."""
    found = []
    for pno, entry in enumerate(entries):
        if entry % 4:
            continue
        index = entry // 4
        if 0 <= index < len(code) and _sub_sp(code[index]):
            found.append((pno, index))
    return found


def _mark_scan(code: list[int], entries: list[int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Entry numbers and word indexes of Kernel.Mark and Kernel.Scan.

    New is the procedure whose opening compares the block size with 32.
    Mark and Scan are the next two procedures in the entry table.
    """
    procs = _proc_starts(code, entries)
    news = []
    for pno, index in procs:
        if 0x40090020 in code[index : index + 16]:
            news.append((pno, index))
    if len(news) != 1:
        raise SystemExit(f"Kernel has {len(news)} procedures that compare with 32, wanted New")
    ordered = sorted(procs, key=lambda item: item[1])
    at = next(i for i, item in enumerate(ordered) if item[1] == news[0][1])
    if at + 2 >= len(ordered):
        raise SystemExit("Mark and Scan are not the procedures after New")
    return ordered[at + 1], ordered[at + 2]


def _drop_collect(raw: bytes, code: list[int], kernel_mno: int, proc_pnos: set[int]) -> bytes:
    """Replace the one local call of the collector with a branch to the next word.

    The collector is the local procedure that calls Kernel.Mark or Kernel.Scan.
    Dark only stores and stops, so its call stays.
    """
    starts = sorted(i for i, word in enumerate(code) if _sub_sp(word))
    if not starts:
        raise SystemExit("Blink5 has no local procedure")
    bls = [(i, _bl_target(i, word)) for i, word in enumerate(code) if (word >> 24) == 0xF7]

    def calls_kernel_gc(word: int) -> bool:
        field = word & 0xFFFFFF
        mno = (field >> 20) & 0xF
        pno = (field >> 12) & 0xFF
        return mno == kernel_mno and pno in proc_pnos

    def is_collect(start: int) -> bool:
        nxt = next((s for s in starts if s > start), len(code))
        return any(start < i < nxt and calls_kernel_gc(code[i]) for i, _target in bls)

    collects = [s for s in starts if is_collect(s)]
    if len(collects) != 1:
        raise SystemExit(f"Blink5 has {len(collects)} collector procedures, wanted one")
    calls = [i for i, target in bls if target == collects[0]]
    if len(calls) != 1:
        raise SystemExit(f"Blink5 calls the collector {len(calls)} times, wanted one")
    origin, ncode = _code_origin(raw)
    if ncode != len(code):
        raise SystemExit(f"Blink5 code length {ncode} != {len(code)}")
    buf = bytearray(raw)
    struct.pack_into("<I", buf, origin + calls[0] * 4, 0xE7000000)
    print(f"[ok] collector call at word {calls[0]} removed")
    return bytes(buf)


# The LED arms only when Blink5 stores this word at this address.
ARM_ADDR = 0x7C0
ARM_WORD = 0xA11C0DE5
SUM_ADDR = 28
# Modules' descriptor. The two-slot table is 2060 bytes. Kernel's static
# image started 8 bytes past a 16-byte boundary, so the pad grows by 4
# and the root moves 2064 bytes past item 29's 0xF7A0.
EXPECT_ROOT = 0xFFB0
BLINK_MT = 0x38
PLANTED_NUM = 4
EQ = 1
ALWAYS = 7


def _arm_prologue(with_disk: bool = False) -> list[int]:
    """OR the differences, then store ARM_WORD xor that OR.

    R8 is the accumulator. R12 and R14 stay. The caller branches to the
    compiled delay loop after the store.

    The flash image also xors mem[8]. The bootstrap stores the disk
    checksum there. A stale disk stores a different sum, the hardware
    arm word was elaborated from this build's checksum, and the LED
    stays dark. The checksum is not an immediate in this sequence.
    """
    a = Asm()
    a.word(f1(0, 8, 0, 0))

    def fold(addr: int, expected: int) -> None:
        for word in load_const(1, addr):
            a.word(word)
        a.word(ldw(0, 1, 0))
        for word in load_const(1, expected):
            a.word(word)
        a.word(f0(9, 0, 0, 1))
        a.word(f0(6, 8, 8, 0))

    fold(12, MEMLIM)
    fold(16, ALLOC)
    fold(20, EXPECT_ROOT)
    fold(24, STACK)
    a.word(f1(0, 0, 0, 58))
    a.word(f1(0, 1, 0, 29))
    a.word(f0(11, 0, 0, 1))
    a.word(f1(9, 0, 0, 2))
    a.word(f0(6, 8, 8, 0))
    a.word(0x20000000)  # MOV R0, H. The remainder of 58 DIV 29 is 0.
    a.word(f0(6, 8, 8, 0))

    def f1v(op: int, rd: int, rb: int, imm: int) -> int:
        """F1 with v=1. imm is the raw 16-bit field, sign-extended by the CPU."""
        return (
            0x50000000
            | ((rd & 0xF) << 24)
            | ((rb & 0xF) << 20)
            | ((op & 0xF) << 16)
            | (imm & 0xFFFF)
        )

    # 65538 * 65535 = 2^32 + 65534. F1 MUL, the form the core executes.
    # The low word is 0xFFFE and H is 1. A dropped high word leaves H at 0.
    a.word(mhi(1, 1))
    a.word(f1(8, 1, 1, 2))
    a.word(f1(10, 0, 1, 0xFFFF))
    a.word(f1(9, 0, 0, 0xFFFE))
    a.word(f0(6, 8, 8, 0))
    a.word(0x20000000)
    a.word(f1(9, 0, 0, 1))
    a.word(f0(6, 8, 8, 0))
    # (-3) * 5 = -15, and H is -1. The unsigned product has the same low
    # word and H = 4, so the high-word check is the signedness check.
    a.word(f1v(0, 0, 0, 0xFFFD))
    a.word(f1(0, 1, 0, 5))
    a.word(f0(10, 0, 0, 1))
    a.word(f1v(9, 0, 0, 0xFFF1))
    a.word(f0(6, 8, 8, 0))
    a.word(0x20000000)
    a.word(f1(8, 0, 0, 1))
    a.word(f0(6, 8, 8, 0))
    for word in load_const(0, BLINK_MT):
        a.word(word)
    a.word(ldw(0, 0, 0))
    a.word(f1(9, 1, 0, 24))
    a.word(ldw(1, 1, 0))
    a.word(f1(9, 2, 0, 20))
    a.word(ldw(2, 2, 0))
    a.word(f1(0, 3, 0, 0))
    a.label("sum")
    a.word(f0(9, 0, 1, 2))
    a.branch("summed", EQ)
    a.word(ldw(0, 1, 0))
    a.word(f0(8, 3, 3, 0))
    a.word(f1(8, 1, 1, 4))
    a.branch("sum", ALWAYS)
    a.label("summed")
    for word in load_const(0, SUM_ADDR):
        a.word(word)
    a.word(ldw(0, 0, 0))
    a.word(f0(9, 0, 3, 0))
    a.word(f0(6, 8, 8, 0))
    for word in load_const(0, ARM_WORD):
        a.word(word)
    a.word(f0(7, 0, 0, 8))
    if with_disk:
        a.word(f1(0, 1, 0, 8))
        a.word(ldw(1, 1, 0))
        a.word(f0(7, 0, 0, 1))
    for word in load_const(1, ARM_ADDR):
        a.word(word)
    a.word(stw(0, 1, 0))
    words = a.encode(0)
    if any(_is_wait_mov(word) for word in words):
        # That MOV is Blink's millisecond assignment. The prologue has none.
        raise SystemExit("arm prologue contains the wait MOV")
    return words


def _rsc_spots(data: bytes) -> dict:
    offset = data.index(b"\0") + 1
    offset += 5  # key, version
    size_at = offset
    offset += 4
    while True:
        if data[offset] == 0:
            offset += 1
            break
        offset = data.index(b"\0", offset) + 1 + 4
    td_size = struct.unpack_from("<I", data, offset)[0]
    offset += 4 + td_size
    offset += 4  # variable-space count; the bytes are not in the file
    strx = struct.unpack_from("<I", data, offset)[0]
    offset += 4 + strx
    code_len_at = offset
    ncode = struct.unpack_from("<I", data, offset)[0]
    code_at = offset + 4
    offset = code_at + ncode * 4
    while True:
        if data[offset] == 0:
            offset += 1
            break
        offset = data.index(b"\0", offset) + 1 + 4
    nofent = struct.unpack_from("<I", data, offset)[0]
    offset += 4 + nofent * 4
    while True:
        ptr = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if ptr == 0xFFFFFFFF:
            break
    fix_at = offset
    entry_at = offset + 12
    if entry_at + 4 >= len(data) or data[entry_at + 4] != ord("O"):
        raise SystemExit("Blink5.rsc has no O marker after the entry point")
    return {
        "size_at": size_at,
        "code_len_at": code_len_at,
        "code_at": code_at,
        "ncode": ncode,
        "fix_at": fix_at,
        "entry_at": entry_at,
    }


def _append_arm(raw: bytes, prologue: list[int]) -> bytes:
    """The arm sequence follows the compiled loop. The entry point moves to it.

    Prepending would stretch the fixup displacements, which count back to the
    first word. The sequence branches to that word when the store has retired.
    """
    spot = _rsc_spots(raw)
    ncode = spot["ncode"]
    code_at = spot["code_at"]
    body = struct.unpack_from("<I", raw, spot["entry_at"])[0]
    if body % 4 or not 0 <= body < ncode * 4:
        raise SystemExit(f"Blink5 entry {body:#x} is outside the compiled code")
    branch_at = (ncode + len(prologue)) * 4
    enter_loop = cond_branch(branch_at, body, ALWAYS)
    extra = list(prologue) + [enter_loop]
    buf = bytearray()
    buf += raw[: spot["code_len_at"]]
    buf += struct.pack("<I", ncode + len(extra))
    buf += raw[code_at : code_at + ncode * 4]
    for word in extra:
        buf += struct.pack("<I", word & 0xFFFFFFFF)
    buf += raw[code_at + ncode * 4 :]
    # The tail shifted by the extra code bytes. Fixups stay in the old words.
    entry_at = spot["entry_at"] + 4 * len(extra)
    fix_at = spot["fix_at"] + 4 * len(extra)
    fp, fd, ft = struct.unpack_from("<III", buf, fix_at)
    if (fp, fd, ft) != struct.unpack_from("<III", raw, spot["fix_at"]):
        raise SystemExit("appending the arm sequence moved a fixup origin")
    entry = struct.unpack_from("<I", buf, entry_at)[0]
    if entry != body:
        raise SystemExit(f"Blink5 entry moved from {body:#x} to {entry:#x}")
    struct.pack_into("<I", buf, entry_at, ncode * 4)
    size = struct.unpack_from("<I", buf, spot["size_at"])[0]
    struct.pack_into("<I", buf, spot["size_at"], size + 4 * len(extra))
    if len(buf) > SECTOR - HEADER_SIZE + SECTOR:
        raise SystemExit(
            f"Blink5.rsc is {len(buf)} bytes; "
            f"a header and one continuation hold {SECTOR - HEADER_SIZE + SECTOR}"
        )
    return bytes(buf)


def _reload_blink(raw: bytes) -> dict:
    path = os.path.join(PAYLOAD, "Blink5.rsc")
    with open(path, "wb") as out:
        out.write(raw)
    parsed = parse_rsc(path, output_format="quiet")
    parsed["raw"] = raw
    return parsed


def _module_code(base: int, parsed: dict) -> int:
    return (
        base
        + DESC_SIZE
        + len(parsed["type_descriptors"]) * 4
        + parsed["data_size"]
        + len(parsed["string_table"])
    )


def _module_end(base: int, parsed: dict) -> int:
    size = parsed["file_size"] + DESC_SIZE
    return ((base + size + 0x100) // 0x20) * 0x20


def _page_sum(page: bytes) -> int:
    total = 0
    for i in range(0, len(page), 4):
        total = (total + int.from_bytes(page[i : i + 4], "little")) & 0xFFFFFFFF
    return total


def _absolute_entries(name: str, entries: list[int], code: list[int],
                      new_at: dict[tuple[str, int], int], data_limit: int) -> list[int]:
    """Procedure entries become packed addresses. Data entries stay offsets.

    A procedure entry is a code offset past the type descriptors and the
    variables, and its first instruction is SUB SP, SP. An offset inside
    the data image is a type descriptor: Rider's entry is 0, and the first
    instruction of Files is also SUB SP, SP. Load adds the module's code
    field, which is 0 for these planted tables.
    """
    out = []
    for entry in entries:
        index = entry // 4
        if (
            entry >= data_limit
            and entry % 4 == 0
            and 0 <= index < len(code)
            and _sub_sp(code[index])
            and (name, index) in new_at
        ):
            out.append(new_at[(name, index)])
        else:
            out.append(entry & 0xFFFFFFFF)
    return out


def _check_files_calls(code: list[int], fix_p: int, entries: list[int]) -> None:
    """Blink's Files imports are Old, Set, and ReadInt, all planted."""
    mno = 4
    pnos = []
    adr = fix_p * 4
    seen = set()
    while adr and adr not in seen:
        seen.add(adr)
        inst = code[adr // 4]
        got = (inst // 0x100000) % 0x10
        pno = (inst // 0x1000) % 0x100
        disp = inst % 0x1000
        if got == mno:
            pnos.append(pno)
        if disp == 0:
            break
        adr -= disp * 4
    if len(pnos) < 3:
        raise SystemExit(f"Blink5 calls Files {len(pnos)} times, wanted Old, Set, and ReadInt")
    for pno in pnos:
        if pno >= len(entries):
            raise SystemExit(f"Files entry {pno} is past the table")
        dest = entries[pno]
        if dest < CORE_BASE or dest >= INIT_BASE:
            raise SystemExit(f"Files entry {pno} is {dest:#x}, not a packed procedure")
    print(f"[ok] Files calls {len(pnos)} entries {pnos}")


def _placed_sum(ammt: dict, blink: dict, kernel_entries: list[int],
                modules_data: int, modules_entries: list[int],
                files_entries: list[int], files_data: int) -> tuple[int, int, int]:
    """Sum of Blink5's code words after Load's fixups. Returns sum, code address, word count.

    The planted Kernel descriptor's code field is 0. Mark, Scan, and Time
    are absolute addresses in the entry table, so dest = entry + code lands
    on the packed procedure. Modules.root is entry 2, a data offset.
    """
    ammt_base = ALLOC
    ammt_code = _module_code(ammt_base, ammt)
    ammt_data = ammt_base + DESC_SIZE
    blink_base = _module_end(ammt_base, ammt)
    blink_code = _module_code(blink_base, blink)
    blink_end = _module_end(blink_base, blink)
    if blink_end > BODY_HI:
        raise SystemExit(f"Blink5 allocation ends at {blink_end:#x}, body window ends at {BODY_HI:#x}")
    ammt_num = PLANTED_NUM + 1
    blink_num = ammt_num + 1
    if blink_num != 6 or BLINK_MT != 0x20 + blink_num * 4:
        raise SystemExit(f"Blink5 is module {blink_num}, prologue reads {BLINK_MT:#x}")
    code = list(blink["code"])
    imp = ImportedModule(
        ammt_num,
        code=ammt_code,
        data=ammt_data,
        entries=ammt["entries"],
    )
    kernel = ImportedModule(
        NUM["Kernel"],
        code=0,
        entries=kernel_entries,
    )
    modules = ImportedModule(
        NUM["Modules"],
        code=0,
        data=modules_data,
        entries=modules_entries,
    )
    files = ImportedModule(
        NUM["Files"],
        code=0,
        data=files_data,
        entries=files_entries,
    )
    fix_p, fix_d, fix_t = blink["fix_org"]
    if fix_t:
        raise SystemExit(f"Blink5 fixorgT {fix_t:#x}")
    imports = [imp, kernel, modules, files]
    fixup_bl(code, fix_p, code_base=blink_code, imports=imports)
    fixup_ldr_str_add(code, fix_d, blink_num, None, imports=imports)
    total = 0
    for word in code:
        total = (total + word) & 0xFFFFFFFF
    return total, blink_code, len(code)


def _load_modules() -> dict[str, dict]:
    load_inner()
    mods = {}
    for name in ORDER:
        path = os.path.join(ROOT, "sim", "inner-core", f"{name}.rsc")
        parsed = parse_rsc(path, output_format="quiet")
        text = parsed["string_table"]
        if name == "Modules":
            if text.count(b"Oberon") != 1:
                raise SystemExit(f"Modules strings {text!r} do not contain Oberon once")
            parsed["string_table"] = text.replace(b"Oberon\x00", b"Blink5\x00", 1)
            if b"Blink5\x00" not in parsed["string_table"] or b"Oberon" in parsed["string_table"]:
                raise SystemExit(f"string patch left {parsed['string_table']!r}")
        mods[name] = parsed
    return mods


def _assign(mods: dict[str, dict]) -> tuple[dict[str, int], dict[str, int], int]:
    data = {}
    # Eight bytes past the heap are a Scan sentinel. A run of unmarked
    # blocks can end on MemLim, and Scan then reads one mark and one
    # size beyond it. The mark is -1 and the size steps past this gap,
    # so the loop stops without writing the module data.
    cursor = MEMLIM + 8
    for name in ORDER:
        data[name] = cursor
        blob = len(mods[name]["type_descriptors"]) * 4
        blob += mods[name]["data_size"]
        blob += len(mods[name]["string_table"])
        cursor = (cursor + blob + 15) & ~15
    if cursor + DESC_SIZE > CORE_BASE:
        raise SystemExit(f"static data ends at {cursor + DESC_SIZE:#x}, core is {CORE_BASE:#x}")
    return data, {name: 0 for name in ORDER}, cursor


def _blob(mod: dict) -> bytes:
    td = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in mod["type_descriptors"])
    var = bytes(mod["data_size"])
    text = mod["string_table"]
    if len(text) % 4:
        text += bytes(4 - (len(text) % 4))
    return td + var + text


def _pairs(data_base: dict[str, int], mods, desc_at: int, desc: bytes, code_at: dict[str, int]) -> list[tuple[int, int]]:
    pairs = [
        (0x0C, MEMLIM),
        (0x10, ALLOC),
        (0x14, desc_at),
        (0x18, STACK),
        (MEMLIM, 8),
        (MEMLIM + 4, 0xFFFFFFFF),
        (0x24, data_base["Kernel"]),
        (0x28, data_base["FileDir"]),
        (0x2C, data_base["Files"]),
        (0x30, data_base["Modules"]),
    ]
    for name in ORDER:
        blob = _blob(mods[name])
        for i in range(0, len(blob), 4):
            word = int.from_bytes(blob[i : i + 4], "little")
            if word:
                pairs.append((data_base[name] + i, word))
    for i in range(0, len(desc), 4):
        word = int.from_bytes(desc[i : i + 4], "little")
        if word:
            pairs.append((desc_at + i, word))
    # code address is filled by the caller once packing is done. The
    # descriptor field is patched below if it was zero at this point.
    del code_at
    return pairs


def _desc(mods, data_base, code_base_modules: int, nxt: int, ent_addr: int) -> bytes:
    buf = bytearray(DESC_SIZE)
    buf[0:8] = b"Modules\x00"
    struct.pack_into("<I", buf, 32, nxt)
    struct.pack_into("<IIIIII", buf, 36,
                      mods["Modules"]["key"],
                      NUM["Modules"],
                      mods["Modules"]["file_size"],
                      0,
                      data_base["Modules"],
                      code_base_modules)
    struct.pack_into("<I", buf, 68, ent_addr)
    return bytes(buf)


def _kernel_desc(mods, data_base, ent_addr: int) -> bytes:
    """ModDesc so Load finds Kernel already present and Blink's BL resolves.

    name, key, num, data, and ent are the fields Load reads. code is 0.
    The Mark, Scan, and Time entry words are absolute addresses, and Load
    adds the entry word to code.
    """
    buf = bytearray(DESC_SIZE)
    buf[0:7] = b"Kernel\x00"
    struct.pack_into("<IIIIII", buf, 36,
                      mods["Kernel"]["key"],
                      NUM["Kernel"],
                      mods["Kernel"]["file_size"],
                      0,
                      data_base["Kernel"],
                      0)
    struct.pack_into("<I", buf, 68, ent_addr)
    return bytes(buf)


def _light(ammt: dict) -> int:
    ptr = ALLOC
    size = ammt["file_size"] + DESC_SIZE
    data = ptr + DESC_SIZE
    ptr = ((ptr + size + 0x100) // 0x20) * 0x20
    if ammt["type_descriptors"]:
        raise SystemExit("AMemoryMappedToggle has a type descriptor; light is not at data+0")
    if ptr >= BODY_HI:
        raise SystemExit(f"AMMT allocation ends at {ptr:#x}, past the body window")
    return data


FLASH_MAGIC = 0x314B5344
FLASH_BUILD = 0xE1
FLASH_BASE = 0x200000
# The book's window is the top 64 bytes, -64 through -4. -80 is the
# screen block and -76 is the reserved text count. The word port and
# the sector base take the two words between those and the window.
IO_WORD = -72
IO_BASE = -68
# The Dock has no NOR. The same file lands here, above the init stream
# (the stream ends near 0x2025C) and inside the HyperRAM stand-in,
# which covers 160 KB. The Dock DDR3 uses this same address.
DISK_DDR = 0x21000
CHECK_ADDR = 8
DIR_AT = 0x60
BOOT_ROM = 512
HALT_WORD = 0xE7FFFFFF


def _io(off: int) -> int:
    return off & 0xFFFFF


def _port_ops(words: list[int], off: int) -> tuple[int, int]:
    """Count LDW and STW whose 20-bit offset is this I/O address."""
    enc = off & 0xFFFFF
    loads = stores = 0
    for word in words:
        if (word & 0xFFFFF) != enc:
            continue
        kind = word & 0xF00FFFFF
        if kind == (0x80000000 | enc):
            loads += 1
        elif kind == (0xA0000000 | enc):
            stores += 1
    return loads, stores


def _check_boot_ports(words: list[int], uart: bool) -> None:
    """The bootstrap may use the flash ports and nothing else in this map."""
    reserved = (
        -80, -76, -64, -60, -56, -52, -48, -44, -40, -36, -32, -28,
    )
    for off in reserved:
        loads, stores = _port_ops(words, off)
        if loads or stores:
            raise SystemExit(
                f"bootstrap still touches {off} ({loads} loads, {stores} stores)"
            )
    loads, stores = _port_ops(words, IO_WORD)
    if loads < 1 or stores != (0 if uart else 1):
        raise SystemExit(
            f"bootstrap word port {IO_WORD}: {loads} loads, {stores} stores"
        )
    loads, stores = _port_ops(words, IO_BASE)
    if loads or stores != 1:
        raise SystemExit(
            f"bootstrap sector base {IO_BASE}: {loads} loads, {stores} stores"
        )


def _plant(a: Asm, static_end: int, flash: bool) -> None:
    """Clear the static image, replay the init stream, then leave for the body.

    HyperRAM powers up as ones. The init stream stores only non-zero
    words. On the flash image the body address is in R5, saved before
    this runs, because the init pointer uses R1.
    """
    a.word(f1(0, 12, 0, 0x20))
    a.word(f1(0, 14, 0, STACK))
    a.word(f1(0, 0, 0, 0))
    # Address 0 powers up as ones. Mark loads it when a pointer list is 0,
    # and a zero there makes that call return.
    a.word(stw(0, 0, 0))
    for word in load_const(2, MEMLIM):
        a.word(word)
    for word in load_const(3, static_end):
        a.word(word)
    a.label("clear")
    a.word(stw(0, 2, 0))
    a.word(f1(8, 2, 2, 4))
    a.word(f0(9, 4, 2, 3))
    a.branch("clear", 9)
    a.word(mhi(1, INIT_BASE >> 16))
    a.label("loop")
    a.word(ldw(2, 1, 0))
    a.branch("done", 1)
    a.word(f1(8, 1, 1, 4))
    a.word(ldw(0, 1, 0))
    a.word(f1(8, 1, 1, 4))
    a.word(stw(0, 2, 0))
    a.branch("loop", 7)
    a.label("done")
    if flash:
        a.word(f0(0, 1, 0, 5))
        a.word(f1(0, 5, 0, 0))
        a.word(0xC7000001)


def _bootstrap(static_end: int) -> list[int]:
    """Read the disk header, copy the core, then run the old stub tail.

    One NOR word per load from -72. The pointer advances in the CPU.
    A failed check branches at the flag the compare just set. Later
    arithmetic is not allowed to sit between that compare and the branch.
    """
    a = Asm()
    a.word(f1(0, 0, 0, 0))
    a.word(f1(0, 4, 0, 0))
    for word in load_const(1, FLASH_BASE):
        a.word(word)
    a.word(stw(1, 0, _io(IO_WORD)))

    def expect(value: int) -> None:
        a.word(ldw(1, 0, _io(IO_WORD)))
        for word in load_const(2, value):
            a.word(word)
        a.word(f0(9, 3, 1, 2))
        a.branch("halt", 9)

    expect(FLASH_MAGIC)
    expect(1)
    expect(FLASH_BUILD)
    a.word(ldw(7, 0, _io(IO_WORD)))
    a.word(f0(9, 6, 7, 0))
    a.branch("halt", 1)
    a.word(f1(4, 6, 7, 3))
    a.word(f0(9, 6, 6, 0))
    a.branch("halt", 9)
    a.word(mhi(6, 1))
    a.word(f1(8, 6, 6, 1))
    a.word(f0(9, 3, 6, 7))
    a.branch("halt", 1)
    a.branch("halt", 0)
    a.word(ldw(8, 0, _io(IO_WORD)))

    a.word(f1(0, 5, 0, DIR_AT))
    a.word(f1(0, 6, 0, 9))
    a.label("dir")
    a.word(f0(9, 3, 6, 0))
    a.branch("dirdone", 1)
    a.word(ldw(1, 0, _io(IO_WORD)))
    a.word(f0(8, 4, 4, 1))
    a.word(stw(1, 5, 0))
    a.word(f1(8, 5, 5, 4))
    a.word(f1(9, 7, 7, 4))
    a.word(f1(9, 6, 6, 1))
    a.branch("dir", 7)
    a.label("dirdone")

    def copy(label: str, count_at: int, dest_at: int | None, dest: int | None) -> None:
        if dest is not None:
            for word in load_const(2, dest):
                a.word(word)
        else:
            a.word(ldw(2, 0, dest_at))
        a.word(ldw(6, 0, count_at))
        a.label(label)
        a.word(f0(9, 3, 6, 0))
        a.branch(label + "x", 1)
        a.word(ldw(1, 0, _io(IO_WORD)))
        a.word(f0(8, 4, 4, 1))
        a.word(stw(1, 2, 0))
        a.word(f1(8, 2, 2, 4))
        a.word(f1(9, 6, 6, 4))
        a.word(f1(9, 7, 7, 4))
        a.branch(label, 7)
        a.label(label + "x")

    copy("code", 0x64, 0x60, None)
    copy("init", 0x6C, None, INIT_BASE)

    a.label("tail")
    a.word(f0(9, 3, 7, 0))
    a.branch("summed", 1)
    a.word(ldw(1, 0, _io(IO_WORD)))
    a.word(f0(8, 4, 4, 1))
    a.word(f1(9, 7, 7, 4))
    a.branch("tail", 7)
    a.label("summed")
    a.word(f0(9, 3, 4, 8))
    a.branch("halt", 9)
    a.word(stw(4, 0, CHECK_ADDR))
    for word in load_const(1, FLASH_BASE + 20 + 36):
        a.word(word)
    a.word(ldw(2, 0, 0x64))
    a.word(ldw(3, 0, 0x6C))
    a.word(f0(8, 1, 1, 2))
    a.word(f0(8, 1, 1, 3))
    a.word(stw(1, 0, _io(IO_BASE)))
    a.word(ldw(5, 0, 0x68))
    _plant(a, static_end, flash=True)
    a.label("halt")
    a.word(HALT_WORD)
    boot = a.encode(STUB_PC)
    if len(boot) > 400:
        raise SystemExit(f"bootstrap is {len(boot)} words; it must stay under PC 0x800")
    if boot[-1] != HALT_WORD:
        raise SystemExit("bootstrap does not end on the halt word")
    _check_boot_ports(boot, uart=False)
    return boot


def _uart_bootstrap(static_end: int) -> list[int]:
    """The flash bootstrap, with UART words instead of the NOR.

    Every word of disk.bin is stored at DISK_DDR as it arrives, so the
    file in DDR3 matches the bytes on the wire. The code and the init
    stream are also copied to the addresses the 4K uses. The sector
    pages stay in that image. -68 receives their DDR3 address. A bad
    magic, build, or checksum branches to the halt and never arms.
    """
    a = Asm()
    a.word(f1(0, 0, 0, 0))
    a.word(f1(0, 4, 0, 0))
    for word in load_const(9, DISK_DDR):
        a.word(word)

    def pull(rd: int) -> None:
        a.word(ldw(rd, 0, _io(IO_WORD)))
        a.word(stw(rd, 9, 0))
        a.word(f1(8, 9, 9, 4))

    def expect(value: int) -> None:
        pull(1)
        for word in load_const(2, value):
            a.word(word)
        a.word(f0(9, 3, 1, 2))
        a.branch("halt", 9)

    expect(FLASH_MAGIC)
    expect(1)
    expect(FLASH_BUILD)
    pull(7)
    a.word(f0(9, 6, 7, 0))
    a.branch("halt", 1)
    a.word(f1(4, 6, 7, 3))
    a.word(f0(9, 6, 6, 0))
    a.branch("halt", 9)
    a.word(mhi(6, 1))
    a.word(f1(8, 6, 6, 1))
    a.word(f0(9, 3, 6, 7))
    a.branch("halt", 1)
    a.branch("halt", 0)
    pull(8)

    a.word(f1(0, 5, 0, DIR_AT))
    a.word(f1(0, 6, 0, 9))
    a.label("dir")
    a.word(f0(9, 3, 6, 0))
    a.branch("dirdone", 1)
    pull(1)
    a.word(f0(8, 4, 4, 1))
    a.word(stw(1, 5, 0))
    a.word(f1(8, 5, 5, 4))
    a.word(f1(9, 7, 7, 4))
    a.word(f1(9, 6, 6, 1))
    a.branch("dir", 7)
    a.label("dirdone")

    def copy(label: str, count_at: int, dest_at: int | None, dest: int | None) -> None:
        if dest is not None:
            for word in load_const(2, dest):
                a.word(word)
        else:
            a.word(ldw(2, 0, dest_at))
        a.word(ldw(6, 0, count_at))
        a.label(label)
        a.word(f0(9, 3, 6, 0))
        a.branch(label + "x", 1)
        pull(1)
        a.word(f0(8, 4, 4, 1))
        a.word(stw(1, 2, 0))
        a.word(f1(8, 2, 2, 4))
        a.word(f1(9, 6, 6, 4))
        a.word(f1(9, 7, 7, 4))
        a.branch(label, 7)
        a.label(label + "x")

    copy("code", 0x64, 0x60, None)
    copy("init", 0x6C, None, INIT_BASE)

    a.label("tail")
    a.word(f0(9, 3, 7, 0))
    a.branch("summed", 1)
    pull(1)
    a.word(f0(8, 4, 4, 1))
    a.word(f1(9, 7, 7, 4))
    a.branch("tail", 7)
    a.label("summed")
    a.word(f0(9, 3, 4, 8))
    a.branch("halt", 9)
    # This disk ends on a zero beat. The checksum store at address 8
    # then never finishes: the bridge stays busy and the PC sits on the
    # next instruction. A nonzero store first lets that store complete.
    # Address 4 is not read. The init stream plants 12, 16, 20 and 24.
    a.word(f1(0, 1, 0, 1))
    a.word(stw(1, 0, 4))
    a.word(stw(4, 0, CHECK_ADDR))
    for word in load_const(1, DISK_DDR + 20 + 36):
        a.word(word)
    a.word(ldw(2, 0, 0x64))
    a.word(ldw(3, 0, 0x6C))
    a.word(f0(8, 1, 1, 2))
    a.word(f0(8, 1, 1, 3))
    a.word(stw(1, 0, _io(IO_BASE)))
    a.word(ldw(5, 0, 0x68))
    # The pointer is done. The delay loop's R9 check is zero on the 4K.
    a.word(f1(0, 9, 0, 0))
    _plant(a, static_end, flash=True)
    a.label("halt")
    a.word(HALT_WORD)
    boot = a.encode(STUB_PC)
    if len(boot) > 400:
        raise SystemExit(f"uart bootstrap is {len(boot)} words; it must stay under PC 0x800")
    if boot[-1] != HALT_WORD:
        raise SystemExit("uart bootstrap does not end on the halt word")
    _check_boot_ports(boot, uart=True)
    return boot


def _finalize_flash(info: dict) -> dict:
    """The arm word is ARM_WORD xor the disk checksum. Build the disk first."""
    import importlib
    disk = importlib.import_module("build_disk_image")
    image = disk.build(info)
    total = int.from_bytes(image[16:20], "little")
    info["arm_word"] = (ARM_WORD ^ total) & 0xFFFFFFFF
    info["disk_checksum"] = total
    info["disk"] = image
    return info


def link(max_iter: int, break_arm: bool = False, flash_boot: bool = False,
         uart_disk: bool = False, no_collect: bool = False) -> dict:
    if flash_boot and uart_disk:
        raise SystemExit("flash boot and the UART disk are different images")
    if not flash_boot and not uart_disk:
        raise SystemExit("the in-ROM image is retired; pass --flash-boot or --uart-disk")
    disk_boot = True
    mods = _load_modules()
    payload = _compile_payload()
    blink_imports = payload["Blink5"]["imports"]
    if [name for name, _key in blink_imports] != ["AMemoryMappedToggle", "Kernel", "Modules", "Files"]:
        raise SystemExit(f"Blink5 imports {blink_imports}")
    blink_key = payload["AMemoryMappedToggle"]["key"]
    got = dict(blink_imports)
    if got["AMemoryMappedToggle"] != blink_key:
        raise SystemExit(f"Blink5 import key {got['AMemoryMappedToggle']:#x} != AMemoryMappedToggle {blink_key:#x}")
    if got["Kernel"] != mods["Kernel"]["key"]:
        raise SystemExit(
            f"Blink5 Kernel key {got['Kernel']:#x} != inner core {mods['Kernel']['key']:#x}"
        )
    if got["Modules"] != mods["Modules"]["key"]:
        raise SystemExit(
            f"Blink5 Modules key {got['Modules']:#x} != inner core {mods['Modules']['key']:#x}"
        )
    if got["Files"] != mods["Files"]["key"]:
        raise SystemExit(
            f"Blink5 Files key {got['Files']:#x} != inner core {mods['Files']['key']:#x}"
        )
    if no_collect:
        (mark_pno, _mark_at), (scan_pno, _scan_at) = _mark_scan(
            mods["Kernel"]["code"], mods["Kernel"]["entries"]
        )
        kernel_mno = next(
            i + 1 for i, (name, _key) in enumerate(blink_imports) if name == "Kernel"
        )
        payload["Blink5"]["raw"] = _drop_collect(
            payload["Blink5"]["raw"], payload["Blink5"]["code"], kernel_mno, {mark_pno, scan_pno}
        )
    prologue = _arm_prologue(with_disk=disk_boot)
    armed_raw = _append_arm(payload["Blink5"]["raw"], prologue)
    payload["Blink5"] = _reload_blink(armed_raw)
    # The delay lives in Blink.Rate. The code is the same for every rate.
    if any(_is_wait_mov(word) for word in payload["Blink5"]["code"]):
        raise SystemExit("Blink5 still has the millisecond MOV; the file should own it")
    with open(os.path.join(PAYLOAD, "Blink5.rsc"), "wb") as out:
        out.write(payload["Blink5"]["raw"])

    data_base, _, desc_at = _assign(mods)
    if desc_at != EXPECT_ROOT:
        raise SystemExit(f"planted root {desc_at:#x} != prologue constant {EXPECT_ROOT:#x}")
    # Modules stays at desc_at. Kernel's descriptor follows it, then both
    # entry tables. Load walks the Modules variable, not this link.
    kernel_at = desc_at + DESC_SIZE
    kernel_ent = kernel_at + DESC_SIZE
    kernel_entries = len(mods["Kernel"]["entries"])
    modules_entries = mods["Modules"]["entries"]
    if kernel_entries < 1:
        raise SystemExit("Kernel has no entries")
    td_bytes = len(mods["Modules"]["type_descriptors"]) * 4
    if len(modules_entries) < 3 or modules_entries[2] != td_bytes:
        raise SystemExit(f"Modules entry 2 is {modules_entries[2:]!r}, wanted root at {td_bytes:#x}")
    modules_ent = kernel_ent + kernel_entries * 4
    # Files is already linked into the core. Load("Files") has to find a
    # descriptor, because Blink calls Old, Set, and ReadInt. code is 0
    # and the procedure entries below are absolute addresses.
    files_at = modules_ent + len(modules_entries) * 4
    files_ent = files_at + DESC_SIZE
    files_len = len(mods["Files"]["entries"])
    static_end = files_ent + files_len * 4
    if static_end >= CORE_BASE:
        raise SystemExit(f"Files descriptor ends at {static_end:#x}, core is {CORE_BASE:#x}")
    lengths = {name: len(mods[name]["code"]) for name in ORDER}
    old_base = {}
    cursor = CORE_BASE
    for name in ORDER:
        old_base[name] = cursor
        cursor += lengths[name] * 4

    codes = {name: list(mods[name]["code"]) for name in ORDER}
    proc_sites = {}
    for name in ORDER:
        parsed = mods[name]
        fix_p, fix_d, fix_t = parsed["fix_org"]
        if fix_t:
            raise SystemExit(f"{name} fixorgT {fix_t} is not zero")
        proc_sites[name] = _d_proc_sites(codes[name], fix_d)
        imports = []
        for imp_name, _key in parsed["imports"]:
            imports.append(ImportedModule(
                NUM[imp_name],
                code=old_base[imp_name],
                data=data_base[imp_name],
                entries=mods[imp_name]["entries"],
            ))
        fixup_bl(codes[name], fix_p, code_base=old_base[name], imports=imports)
        fixup_ldr_str_add(codes[name], fix_d, NUM[name], None, imports=imports)

    seeds = {("Modules", mods["Modules"]["entry_point"] // 4)}
    for index, inst in enumerate(codes["Kernel"]):
        got = _f1_r15(inst)
        if got is None or got[0] != 9:
            continue
        addr = old_base["Kernel"] + index * 4
        target = (addr - got[1]) & 0xFFFFFFFF
        try:
            mod, word = _locate(target, old_base, lengths)
        except SystemExit:
            continue
        if _sub_sp(codes[mod][word]):
            seeds.add((mod, word))
    time_index, time_load = _kernel_time(mods["Kernel"]["code"], mods["Kernel"]["entries"])
    (mark_pno, mark_index), (scan_pno, scan_index) = _mark_scan(
        mods["Kernel"]["code"], mods["Kernel"]["entries"]
    )
    seeds.add(("Kernel", time_index))
    seeds.add(("Kernel", mark_index))
    seeds.add(("Kernel", scan_index))
    # Blink calls WriteInt and Close, which the boot path does not.
    # Those entries have to be packed or the read-back of the rate stops.
    files_mod = mods["Files"]
    files_limit = (
        len(files_mod["type_descriptors"]) * 4 + files_mod["data_size"]
    )
    blink_fix = payload["Blink5"]["fix_org"][0]
    blink_code = payload["Blink5"]["code"]
    called = set()
    adr = blink_fix * 4
    seen_fix = set()
    while adr and adr not in seen_fix:
        seen_fix.add(adr)
        inst = blink_code[adr // 4]
        if (inst // 0x100000) % 0x10 == 4:
            called.add((inst // 0x1000) % 0x100)
        disp = inst % 0x1000
        if disp == 0:
            break
        adr -= disp * 4
    if len(called) < 3:
        raise SystemExit(f"Blink5 calls Files {sorted(called)}")
    for pno in sorted(called):
        if pno >= len(files_mod["entries"]):
            raise SystemExit(f"Files entry {pno} is past the table")
        entry = files_mod["entries"][pno]
        index = entry // 4
        if not (
            entry >= files_limit
            and entry % 4 == 0
            and 0 <= index < len(codes["Files"])
            and _sub_sp(codes["Files"][index])
        ):
            raise SystemExit(
                f"Blink calls Files entry {pno} at {entry:#x}, not a procedure"
            )
        seeds.add(("Files", index))

    def targets_of(seen):
        extra = set()
        for name, index in seen:
            got = _f1_r15(codes[name][index])
            if got is None:
                continue
            addr = old_base[name] + index * 4
            target = (addr - got[1]) if got[0] == 9 else (addr + got[1])
            target &= 0xFFFFFFFF
            try:
                extra.add(_locate(target, old_base, lengths))
            except SystemExit:
                pass
        for name, sites in proc_sites.items():
            for index, mno, vno in sites:
                if (name, index) not in seen:
                    continue
                imp_name = mods[name]["imports"][mno - 1][0]
                entry = mods[imp_name]["entries"][vno]
                if entry % 4:
                    raise SystemExit(f"{imp_name} entry {vno} is {entry}")
                extra.add((imp_name, entry // 4))
        return extra

    seen: set[tuple[str, int]] = set()
    pending = set(seeds)
    while pending - seen:
        seen = _walk(codes, old_base, lengths, pending)
        pending |= targets_of(seen)
    muls = []
    floats = []
    for name in ORDER:
        for index in range(lengths[name]):
            if (name, index) not in seen:
                continue
            inst = codes[name][index]
            if (inst >> 30) > 1:
                continue
            op = (inst >> 16) & 0xF
            if op == 10:
                muls.append((name, index, inst))
            elif op >= 12:
                floats.append((name, index, op, inst))
    if floats:
        # Still not executed as floating point. The words stay as they are.
        print(f"[ok] {len(floats)} floating-point ops remain in the reachable image")
    print(f"[ok] {len(muls)} multiplies left for the hardware multiplier")
    for name, index, inst in muls:
        kind = "F1" if (inst >> 30) == 1 else "F0"
        u = (inst >> 29) & 1
        v = (inst >> 28) & 1
        rd = (inst >> 24) & 0xF
        rb = (inst >> 20) & 0xF
        extra = f" imm={inst & 0xFFFF:#x}" if kind == "F1" else f" rc={inst & 0xF}"
        print(
            f"    {name}+{index} {kind} {'U' if u else ''}MUL "
            f"r{rd}, r{rb},{extra} v={v} {inst:#010x}"
        )

    new_at: dict[tuple[str, int], int] = {}
    packed: list[tuple[str, int, int]] = []
    addr = CORE_BASE
    for name in ORDER:
        for index in sorted(i for n, i in seen if n == name):
            new_at[(name, index)] = addr
            packed.append((name, index, addr))
            addr += 4
    if addr > INIT_BASE:
        raise SystemExit(f"packed code ends at {addr:#x}, init window is {INIT_BASE:#x}")

    words = []
    word_pos: dict[tuple[str, int], int] = {}
    for name, index, new in packed:
        inst = codes[name][index]
        old = old_base[name] + index * 4
        if (inst >> 30) == 3 and ((inst >> 29) & 1):
            target = (old + 4 + _sx24(inst) * 4) & 0xFFFFFFFF
            loc = _locate(target, old_base, lengths)
            if loc not in new_at:
                raise SystemExit(f"{name}+{index} branches to unpacked {target:#x}")
            off = (new_at[loc] - new - 4) // 4
            if off < -(1 << 23) or off >= (1 << 23):
                raise SystemExit(f"branch from {new:#x} to {new_at[loc]:#x} does not fit")
            inst = ((inst & 0xFF000000) | (off & 0xFFFFFF)) & 0xFFFFFFFF
        got = _f1_r15(codes[name][index])
        if got is not None:
            target = (old - got[1]) if got[0] == 9 else (old + got[1])
            target &= 0xFFFFFFFF
            try:
                loc = _locate(target, old_base, lengths)
            except SystemExit:
                loc = None
            if loc is not None:
                if loc not in new_at:
                    raise SystemExit(f"R15 target {target:#x} was not packed")
                new_imm = (new - new_at[loc]) if got[0] == 9 else (new_at[loc] - new)
                if not 0 <= new_imm <= 0xFFFF:
                    raise SystemExit(f"R15 immediate {new_imm:#x} at {new:#x} does not fit")
                # Keep rd, rb, and op. Clear v so the immediate is zero-extended.
                inst = (inst & 0xEFFF0000) | new_imm
        word_pos[(name, index)] = len(words)
        words.append(inst)
    if len(words) * 4 != addr - CORE_BASE:
        raise SystemExit(f"packed {len(words)} words but addresses span {addr - CORE_BASE} bytes")

    for name, sites in proc_sites.items():
        for index, mno, vno in sites:
            if (name, index) not in new_at:
                continue
            imp_name = mods[name]["imports"][mno - 1][0]
            entry = mods[imp_name]["entries"][vno] // 4
            if (imp_name, entry) not in new_at:
                raise SystemExit(f"{name} takes the address of unpacked {imp_name} entry {vno}")
            offset = new_at[(imp_name, entry)] - data_base[imp_name]
            if not 0 <= offset <= 0xFFFF:
                raise SystemExit(f"procedure offset {offset:#x} does not fit")
            at = word_pos[(name, index)]
            words[at] = (words[at] & 0xFFFF0000) | (offset & 0xFFFF)

    for key, label in (
        (("Kernel", time_index), "Time"),
        (("Kernel", time_load), "Time's timer load"),
        (("Kernel", mark_index), "Mark"),
        (("Kernel", scan_index), "Scan"),
    ):
        if key not in new_at:
            raise SystemExit(f"Kernel.{label} was not packed")
    time_addr = new_at[("Kernel", time_index)]
    time_pno = next(
        i for i, entry in enumerate(mods["Kernel"]["entries"])
        if entry % 4 == 0 and entry // 4 == time_index
    )
    kernel_words = list(mods["Kernel"]["entries"])
    kernel_words[time_pno] = time_addr
    kernel_words[mark_pno] = new_at[("Kernel", mark_index)]
    kernel_words[scan_pno] = new_at[("Kernel", scan_index)]
    body = new_at[("Modules", mods["Modules"]["entry_point"] // 4)]
    modules_code = new_at[("Modules", 0)] if ("Modules", 0) in new_at else min(
        new_at[k] for k in new_at if k[0] == "Modules"
    )
    desc = _desc(mods, data_base, modules_code, kernel_at, modules_ent)
    files_mod = mods["Files"]
    files_limit = len(files_mod["type_descriptors"]) * 4 + files_mod["data_size"]
    files_words = _absolute_entries(
        "Files", files_mod["entries"], codes["Files"], new_at, files_limit
    )
    _check_files_calls(payload["Blink5"]["code"], payload["Blink5"]["fix_org"][0], files_words)
    code_sum, blink_at, blink_words = _placed_sum(
        payload["AMemoryMappedToggle"], payload["Blink5"], kernel_words,
        data_base["Modules"], modules_entries,
        files_words, data_base["Files"],
    )
    planted_sum = (code_sum + (1 if break_arm else 0)) & 0xFFFFFFFF
    # String at SB+0x70 is what the body passes to Load.
    string_at = data_base["Modules"] + len(mods["Modules"]["type_descriptors"]) * 4 + mods["Modules"]["data_size"]
    blob = _blob(mods["Modules"])
    rel = string_at - data_base["Modules"]
    if blob[rel : rel + 8] != b"Blink5\x00\x00":
        raise SystemExit(f"Modules string at +{rel:#x} is {blob[rel : rel + 8]!r}")

    pairs = _pairs(data_base, mods, desc_at, desc, {})
    pairs.append((SUM_ADDR, planted_sum))
    kdesc = bytearray(_kernel_desc(mods, data_base, kernel_ent))
    struct.pack_into("<I", kdesc, 32, files_at)
    for i in range(0, len(kdesc), 4):
        word = int.from_bytes(kdesc[i : i + 4], "little")
        if word:
            pairs.append((kernel_at + i, word))
    fdesc = bytearray(DESC_SIZE)
    fdesc[0:6] = b"Files\x00"
    struct.pack_into(
        "<IIIIII", fdesc, 36,
        mods["Files"]["key"], NUM["Files"], mods["Files"]["file_size"], 0,
        data_base["Files"], 0,
    )
    struct.pack_into("<I", fdesc, 68, files_ent)
    for i in range(0, len(fdesc), 4):
        word = int.from_bytes(fdesc[i : i + 4], "little")
        if word:
            pairs.append((files_at + i, word))
    for i, word in enumerate(kernel_words):
        if word:
            pairs.append((kernel_ent + i * 4, word & 0xFFFFFFFF))
    for i, word in enumerate(modules_entries):
        if word:
            pairs.append((modules_ent + i * 4, word & 0xFFFFFFFF))
    for i, word in enumerate(files_words):
        if word:
            pairs.append((files_ent + i * 4, word & 0xFFFFFFFF))
    stream = []
    for dest, value in pairs:
        stream.extend((dest, value & 0xFFFFFFFF))
    stream.append(0)
    planted = {dest: value for dest, value in pairs}
    for addr, value in ((0x0C, MEMLIM), (0x10, ALLOC), (0x14, desc_at), (0x18, STACK)):
        if planted.get(addr) != value:
            raise SystemExit(f"address {addr:#x} is {planted.get(addr)}, wanted {value:#x}")
    if 0x20 in planted:
        raise SystemExit("the stub writes MT[0]; Kernel.Init installs the trap there")

    if uart_disk:
        stub = _uart_bootstrap(static_end)
    else:
        stub = _bootstrap(static_end)

    names = (b"AMemoryMappedToggle.rsc", b"Blink5.rsc")
    pages = {}
    for sec, page in _file_pages(names[0], payload["AMemoryMappedToggle"]["raw"], AMMT_SEC, None):
        pages[sec] = page
    for sec, page in _file_pages(names[1], payload["Blink5"]["raw"], BLINK_SEC, BLINK_CONT):
        pages[sec] = page
    # Sector 116 is Blink5's continuation when the object file spills.
    # The rate file takes the next free page, so the page index stays dense.
    rate_sec = RATE_SEC if BLINK_CONT in pages else BLINK_CONT
    pages[rate_sec] = rate_page(max_iter, rate_sec)
    other = rate_page(max_iter + 2 if max_iter <= 0x7FFD else max_iter - 2, rate_sec)
    if _page_sum(pages[rate_sec]) != _page_sum(other):
        raise SystemExit("Blink.Rate's word sum depends on the delay")
    entries = [(names[0], AMMT_SEC), (RATE_NAME, rate_sec), (names[1], BLINK_SEC)]
    if entries != sorted(entries):
        raise SystemExit(f"directory names are not in order: {entries}")
    pages[DIR_ROOT] = _dir_page(entries)
    raw_sector = rom_words(pages)
    if BLINK_CONT not in pages and any(raw_sector[768:1024]):
        raise SystemExit("sector image uses a fourth page")
    rate_at = (
        20 + 36 + len(words) * 4 + len(stream) * 4
        + (rate_sec // 29 - 1) * SECTOR + HEADER_SIZE
    )

    rom = [(w & 0xFFFFFFFF) for w in stub]
    rom.extend([HALT_WORD] * (BOOT_ROM - len(rom)))
    used = len(stub)
    nrom = BOOT_ROM
    # The core, the init stream, and the sectors live in the disk.
    # The ROM is the bootstrap only.
    map_sector_words = 0
    map_sector_pairs = 0
    map_core_rom = 0
    map_init_rom = 0
    map_sector_rom = 0
    light = _light(payload["AMemoryMappedToggle"])
    info = {
        "stub_words": len(stub),
        "core_base": CORE_BASE,
        "core_words": len(words),
        "core_rom": map_core_rom,
        "init_base": INIT_BASE,
        "init_words": len(stream),
        "init_rom": map_init_rom,
        "body_lo": BODY_LO,
        "body_hi": BODY_HI,
        "body": body,
        "light": light,
        "sector_rom": map_sector_rom,
        "sector_words": map_sector_words,
        "sector_pairs": map_sector_pairs,
        "rom_words": nrom,
        "used": used,
        "delay_word": max_iter,
        "time": time_addr,
        "delay_index": rate_at,
        "rate_sec": rate_sec,
        "rate_at": rate_at,
        "desc": desc_at,
        "arm_addr": ARM_ADDR,
        "arm_word": ARM_WORD,
        "code_sum": code_sum,
        "planted_sum": planted_sum,
        "blink_at": blink_at,
        "blink_words": blink_words,
        "break_arm": int(break_arm),
        "flash_boot": int(flash_boot),
        "uart_disk": int(uart_disk),
        "data": data_base,
        "string": string_at,
        "counts": {name: sum(1 for n, _i in seen if n == name) for name in ORDER},
        "words": rom,
        # The disk image is these three chunks. `words` in the ROM is the
        # same code and the same init stream; `sector_pages` is the three
        # 1024-byte pages before they are packed into sparse pairs.
        "code_words": list(words),
        "init_stream": list(stream),
        "sector_pages": dict(pages),
    }
    if disk_boot:
        info = _finalize_flash(info)
        got = struct.unpack_from("<ii", info["disk"], info["rate_at"])
        if got != (max_iter, -max_iter):
            raise SystemExit(f"rate bytes at {info['rate_at']} are {got}")
    return info


def write_map(info: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = (
        "stub_words", "core_base", "core_words", "core_rom",
        "init_base", "init_words", "init_rom",
        "body_lo", "body_hi", "body", "light",
        "sector_rom", "sector_words", "sector_pairs", "rom_words", "delay_word", "desc", "string",
        "arm_addr", "arm_word", "time",
    )
    with open(path, "w") as out:
        out.write("split=1\n")
        for key in fields:
            out.write(f"{key}={info[key]}\n")
        if "disk_checksum" in info:
            out.write(f"disk_checksum={info['disk_checksum']}\n")
            out.write(f"flash_boot={info['flash_boot']}\n")
            out.write(f"uart_disk={info.get('uart_disk', 0)}\n")


def write_words(words: list[int], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as out:
        for word in words:
            out.write(f"{word:08x}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-iter", type=int, default=WAIT_MS,
                        help="milliseconds between toggles (even; hardware is 1000)")
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=ROM_WORDS)
    parser.add_argument("--out", default=os.path.join(ROOT, "sim", "visualizer", "imem", "modules.words"))
    parser.add_argument("--break-arm", action="store_true",
                        help="Plant the code checksum plus one, so the LED stays dark")
    parser.add_argument("--flash-boot", action="store_true",
                        help="ROM is the disk bootstrap. Write sim/out/disk.bin")
    parser.add_argument("--uart-disk", action="store_true",
                        help="ROM is the UART bootstrap. Same disk.bin, stored in DDR3")
    parser.add_argument("--no-collect", action="store_true",
                        help="Leave the collector call out, so the eighth on-edge stops")
    args = parser.parse_args()
    n = args.mov_iter if args.mov_iter is not None else args.max_iter
    info = link(n, break_arm=args.break_arm, flash_boot=args.flash_boot,
                uart_disk=args.uart_disk, no_collect=args.no_collect)
    write_words(info["words"], args.out)
    write_map(info, MAP_PATH)
    counts = " ".join(f"{name} {info['counts'][name]}" for name in ORDER)
    print(
        f"[ok] ROM {info['used']}/{info['rom_words']} "
        f"stub {info['stub_words']} code {info['core_words']} "
        f"init {info['init_words']} sector {info['sector_words']}"
    )
    print(f"[ok] reachable {counts}")
    print(
        f"[ok] body {info['body']:#x} light {info['light']:#x} "
        f"desc {info['desc']:#x} string {info['string']:#x} "
        f"wait {info['delay_word']:08x} time {info['time']:#x}"
    )
    print(
        f"[ok] arm {info['arm_addr']:#x} word {info['arm_word']:08x} "
        f"sum {info['code_sum']:08x} planted {info['planted_sum']:08x} "
        f"blink {info['blink_at']:#x} words {info['blink_words']}"
        + (" BREAK" if info["break_arm"] else "")
    )
    print(f"[ok] map {MAP_PATH}")
    print(
        f"[ok] heap {STACK:#x}..{MEMLIM:#x} bytes {HEAP_BYTES} "
        f"exhaust rise {EXHAUST_RISES}"
        + (" NO-COLLECT" if args.no_collect else "")
    )
    if args.flash_boot or args.uart_disk:
        disk_path = os.path.join(ROOT, "sim", "out", "disk.bin")
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        with open(disk_path, "wb") as out:
            out.write(info["disk"])
        print(
            f"[ok] disk {disk_path} bytes {len(info['disk'])} "
            f"checksum {info['disk_checksum']:08x} "
            f"arm {info['arm_word']:08x} boot {info['stub_words']}"
        )
        delay = info["delay_word"]
        neg = (-delay) & 0xFFFFFFFF
        raw = struct.pack("<ii", delay, -delay)
        print(
            f"[ok] rate {delay} ms sector {info['rate_sec']} "
            f"at {info['rate_at']:#x} bytes {raw.hex(' ')} "
            f"words {delay:08x} {neg:08x}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
