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
    BLINK_SEC,
    DIR_ROOT,
    HEADER_SIZE,
    SECTOR,
    _dir_page,
    _header,
    rom_words,
)

CORE_BASE = 0x18000
INIT_BASE = 0x20000
STUB_PC = 0x80
MEMLIM = 0x14000
ALLOC = 0x2000
STACK = 0xC000
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


def _bad_math(inst: int) -> int | None:
    if (inst >> 30) > 1:
        return None
    op = (inst >> 16) & 0xF
    if op == 10 or op >= 12:
        return op
    return None


def _mem(store: bool, ra: int, rb: int, off: int) -> int:
    base = 0xA0000000 if store else 0x80000000
    return base | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | (off & 0xFFFFF)


def _expand_mul(inst: int) -> list[int] | None:
    """Immediate multiply. The core has no multiplier. R11 is saved.

    40 is the directory stride. 29 is AllocSector's sector size. The next
    instruction overwrites N and Z, and H is not read.
    """
    if (inst >> 30) != 1 or ((inst >> 29) & 1) or ((inst >> 16) & 0xF) != 10:
        return None
    if (inst >> 28) & 1:
        raise SystemExit(f"signed MUL {inst:#x}")
    rd = (inst >> 24) & 0xF
    rb = (inst >> 20) & 0xF
    imm = inst & 0xFFFF
    if rd != rb or rd >= 10 or imm not in (29, 40):
        raise SystemExit(f"cannot rewrite MUL {inst:#x}")
    scratch = 11
    save = _mem(True, scratch, 14, -4)
    restore = _mem(False, scratch, 14, -4)
    if imm == 40:
        return [
            save,
            f1(1, scratch, rd, 5),
            f1(1, rd, rd, 3),
            f0(8, rd, rd, scratch),
            restore,
        ]
    return [
        save,
        f1(1, scratch, rd, 5),
        f0(9, scratch, scratch, rd),
        f0(9, scratch, scratch, rd),
        f0(9, rd, scratch, rd),
        restore,
    ]


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
        if len(parsed["raw"]) > SECTOR - HEADER_SIZE:
            raise SystemExit(f"{name}.rsc is {len(parsed['raw'])} bytes; one sector holds {SECTOR - HEADER_SIZE}")
        mods[name] = parsed
    print(text, end="")
    return mods


def _mhi_imm1(word: int) -> bool:
    return (word & 0xF0F00000) == 0x60000000 and (word & 0xFFFF) == 1


def _low_half(word: int, rd: int) -> bool:
    """The second half of a 32-bit constant: IOR or ADD into the same register."""
    if (word >> 28) not in (4, 5):
        return False
    if ((word >> 24) & 0xF) != rd or ((word >> 20) & 0xF) != rd:
        return False
    return ((word >> 16) & 0xF) in (6, 8)


def _delay_mhi(code: list[int]) -> int:
    """The 65536 assignment is the bare MHI. MemLim and the root are MHI plus a low half."""
    hits = []
    for i, word in enumerate(code):
        if not _mhi_imm1(word):
            continue
        rd = (word >> 24) & 0xF
        nxt = code[i + 1] if i + 1 < len(code) else 0
        if not _low_half(nxt, rd):
            hits.append(i)
    if len(hits) != 1:
        raise SystemExit(f"Blink5 has {len(hits)} bare MHI 1 words, wanted the 65536 assignment")
    return hits[0]


def _patch_delay(raw: bytes, code: list[int], n: int) -> tuple[bytes, int, int]:
    index = _delay_mhi(code)
    rd = (code[index] >> 24) & 0xF
    if n == 65536:
        word = code[index]
    elif 0 <= n <= 0xFFFF:
        word = f1(0, rd, 0, n)
    else:
        raise SystemExit(f"maxIterations {n} does not fit one instruction")
    origin, ncode = _code_origin(raw)
    if ncode != len(code):
        raise SystemExit(f"Blink5 code length {ncode} != {len(code)}")
    buf = bytearray(raw)
    struct.pack_into("<I", buf, origin + index * 4, word)
    return bytes(buf), word, index


# The LED arms only when Blink5 stores this word at this address.
ARM_ADDR = 0x7C0
ARM_WORD = 0xA11C0DE5
SUM_ADDR = 28
EXPECT_ROOT = 0x161A0
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
    if any(_mhi_imm1(word) and not _low_half(words[i + 1], (word >> 24) & 0xF)
           for i, word in enumerate(words) if _mhi_imm1(word)):
        # A bare MHI 1 here would be the delay assignment. The prologue has none.
        raise SystemExit("arm prologue contains the delay MHI")
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
    branch_at = (ncode + len(prologue)) * 4
    enter_loop = cond_branch(branch_at, 0, ALWAYS)
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
    if entry != 0:
        raise SystemExit(f"Blink5 entry {entry:#x} is not the compiled body")
    struct.pack_into("<I", buf, entry_at, ncode * 4)
    size = struct.unpack_from("<I", buf, spot["size_at"])[0]
    struct.pack_into("<I", buf, spot["size_at"], size + 4 * len(extra))
    if len(buf) > SECTOR - HEADER_SIZE:
        raise SystemExit(f"Blink5.rsc is {len(buf)} bytes; one sector holds {SECTOR - HEADER_SIZE}")
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


def _placed_sum(ammt: dict, blink: dict) -> tuple[int, int, int]:
    """Sum of Blink5's code words after Load's fixups. Returns sum, code address, word count."""
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
    fix_p, fix_d, fix_t = blink["fix_org"]
    if fix_t:
        raise SystemExit(f"Blink5 fixorgT {fix_t:#x}")
    fixup_bl(code, fix_p, code_base=blink_code, imports=[imp])
    fixup_ldr_str_add(code, fix_d, blink_num, None, imports=[imp])
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
    cursor = MEMLIM
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


def _desc(mods, data_base, code_base_modules: int) -> bytes:
    buf = bytearray(DESC_SIZE)
    buf[0:8] = b"Modules\x00"
    struct.pack_into("<IIIIII", buf, 36,
                      mods["Modules"]["key"],
                      NUM["Modules"],
                      mods["Modules"]["file_size"],
                      0,
                      data_base["Modules"],
                      code_base_modules)
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


def _plant(a: Asm, static_end: int, flash: bool) -> None:
    """Clear the static image, replay the init stream, then leave for the body.

    HyperRAM powers up as ones. The init stream stores only non-zero
    words. On the flash image the body address is in R5, saved before
    this runs, because the init pointer uses R1.
    """
    a.word(f1(0, 12, 0, 0x20))
    a.word(f1(0, 14, 0, STACK))
    a.word(f1(0, 0, 0, 0))
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

    One NOR word per load from -64. The pointer advances in the CPU.
    A failed check branches at the flag the compare just set. Later
    arithmetic is not allowed to sit between that compare and the branch.
    """
    a = Asm()
    a.word(f1(0, 0, 0, 0))
    a.word(f1(0, 4, 0, 0))
    for word in load_const(1, FLASH_BASE):
        a.word(word)
    a.word(stw(1, 0, _io(-64)))

    def expect(value: int) -> None:
        a.word(ldw(1, 0, _io(-64)))
        for word in load_const(2, value):
            a.word(word)
        a.word(f0(9, 3, 1, 2))
        a.branch("halt", 9)

    expect(FLASH_MAGIC)
    expect(1)
    expect(FLASH_BUILD)
    a.word(ldw(7, 0, _io(-64)))
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
    a.word(ldw(8, 0, _io(-64)))

    a.word(f1(0, 5, 0, DIR_AT))
    a.word(f1(0, 6, 0, 9))
    a.label("dir")
    a.word(f0(9, 3, 6, 0))
    a.branch("dirdone", 1)
    a.word(ldw(1, 0, _io(-64)))
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
        a.word(ldw(1, 0, _io(-64)))
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
    a.word(ldw(1, 0, _io(-64)))
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
    a.word(stw(1, 0, _io(-60)))
    a.word(ldw(5, 0, 0x68))
    _plant(a, static_end, flash=True)
    a.label("halt")
    a.word(HALT_WORD)
    boot = a.encode(STUB_PC)
    if len(boot) > 400:
        raise SystemExit(f"bootstrap is {len(boot)} words; it must stay under PC 0x800")
    if boot[-1] != HALT_WORD:
        raise SystemExit("bootstrap does not end on the halt word")
    return boot


def _uart_bootstrap(static_end: int) -> list[int]:
    """The flash bootstrap, with UART words instead of the NOR.

    Every word of disk.bin is stored at DISK_DDR as it arrives, so the
    file in DDR3 matches the bytes on the wire. The code and the init
    stream are also copied to the addresses the 4K uses. The sector
    pages stay in that image. -60 receives their DDR3 address. A bad
    magic, build, or checksum branches to the halt and never arms.
    """
    a = Asm()
    a.word(f1(0, 0, 0, 0))
    a.word(f1(0, 4, 0, 0))
    for word in load_const(9, DISK_DDR):
        a.word(word)

    def pull(rd: int) -> None:
        a.word(ldw(rd, 0, _io(-64)))
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
    a.word(stw(4, 0, CHECK_ADDR))
    for word in load_const(1, DISK_DDR + 20 + 36):
        a.word(word)
    a.word(ldw(2, 0, 0x64))
    a.word(ldw(3, 0, 0x6C))
    a.word(f0(8, 1, 1, 2))
    a.word(f0(8, 1, 1, 3))
    a.word(stw(1, 0, _io(-60)))
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
         uart_disk: bool = False) -> dict:
    if flash_boot and uart_disk:
        raise SystemExit("flash boot and the UART disk are different images")
    if not flash_boot and not uart_disk:
        raise SystemExit("the in-ROM image is retired; pass --flash-boot or --uart-disk")
    disk_boot = True
    mods = _load_modules()
    payload = _compile_payload()
    blink_key = payload["AMemoryMappedToggle"]["key"]
    got = [k for name, k in payload["Blink5"]["imports"] if name == "AMemoryMappedToggle"]
    if got != [blink_key]:
        raise SystemExit(f"Blink5 import key {got} != AMemoryMappedToggle {blink_key:#x}")
    prologue = _arm_prologue(with_disk=disk_boot)
    armed_raw = _append_arm(payload["Blink5"]["raw"], prologue)
    payload["Blink5"] = _reload_blink(armed_raw)
    raw, delay_word, delay_index = _patch_delay(
        payload["Blink5"]["raw"], payload["Blink5"]["code"], max_iter
    )
    payload["Blink5"]["raw"] = raw
    payload["Blink5"]["code"][delay_index] = delay_word
    with open(os.path.join(PAYLOAD, "Blink5.rsc"), "wb") as out:
        out.write(raw)

    data_base, _, desc_at = _assign(mods)
    if desc_at != EXPECT_ROOT:
        raise SystemExit(f"planted root {desc_at:#x} != prologue constant {EXPECT_ROOT:#x}")
    code_sum, blink_at, blink_words = _placed_sum(
        payload["AMemoryMappedToggle"], payload["Blink5"]
    )
    planted_sum = (code_sum + (1 if break_arm else 0)) & 0xFFFFFFFF
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
    rewritten = 0
    for name in ORDER:
        for index in range(lengths[name]):
            if (name, index) not in seen:
                continue
            if _bad_math(codes[name][index]) is not None:
                _expand_mul(codes[name][index])
                rewritten += 1
    if rewritten:
        print(f"[ok] {rewritten} immediate multiplies rewritten with R11 saved")

    new_at: dict[tuple[str, int], int] = {}
    packed: list[tuple[str, int, int]] = []
    addr = CORE_BASE
    for name in ORDER:
        for index in sorted(i for n, i in seen if n == name):
            new_at[(name, index)] = addr
            packed.append((name, index, addr))
            seq = _expand_mul(codes[name][index])
            addr += (len(seq) if seq else 1) * 4
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
        seq = _expand_mul(codes[name][index])
        if seq:
            words.extend(seq)
        else:
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

    body = new_at[("Modules", mods["Modules"]["entry_point"] // 4)]
    modules_code = new_at[("Modules", 0)] if ("Modules", 0) in new_at else min(
        new_at[k] for k in new_at if k[0] == "Modules"
    )
    desc = _desc(mods, data_base, modules_code)
    # String at SB+0x70 is what the body passes to Load.
    string_at = data_base["Modules"] + len(mods["Modules"]["type_descriptors"]) * 4 + mods["Modules"]["data_size"]
    blob = _blob(mods["Modules"])
    rel = string_at - data_base["Modules"]
    if blob[rel : rel + 8] != b"Blink5\x00\x00":
        raise SystemExit(f"Modules string at +{rel:#x} is {blob[rel : rel + 8]!r}")

    pairs = _pairs(data_base, mods, desc_at, desc, {})
    pairs.append((SUM_ADDR, planted_sum))
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

    static_end = desc_at + DESC_SIZE
    if uart_disk:
        stub = _uart_bootstrap(static_end)
    else:
        stub = _bootstrap(static_end)

    names = (b"AMemoryMappedToggle.rsc", b"Blink5.rsc")
    if names != tuple(sorted(names)):
        raise SystemExit("directory names are not in order")
    pages = {
        DIR_ROOT: _dir_page([(names[0], AMMT_SEC), (names[1], BLINK_SEC)]),
        AMMT_SEC: _header(names[0], payload["AMemoryMappedToggle"]["raw"], AMMT_SEC),
        BLINK_SEC: _header(names[1], payload["Blink5"]["raw"], BLINK_SEC),
    }
    raw_sector = rom_words(pages)
    if raw_sector[768:] != [0] * (len(raw_sector) - 768):
        raise SystemExit("sector image uses more than three pages")

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
        "delay_word": delay_word,
        "delay_index": delay_index,
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
    return info


def write_map(info: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = (
        "stub_words", "core_base", "core_words", "core_rom",
        "init_base", "init_words", "init_rom",
        "body_lo", "body_hi", "body", "light",
        "sector_rom", "sector_words", "sector_pairs", "rom_words", "delay_word", "desc", "string",
        "arm_addr", "arm_word",
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
    parser.add_argument("--max-iter", type=int, default=65536)
    parser.add_argument("--mov-iter", type=int, default=None)
    parser.add_argument("--pad", type=int, default=ROM_WORDS)
    parser.add_argument("--out", default=os.path.join(ROOT, "sim", "visualizer", "imem", "modules.words"))
    parser.add_argument("--break-arm", action="store_true",
                        help="Plant the code checksum plus one, so the LED stays dark")
    parser.add_argument("--flash-boot", action="store_true",
                        help="ROM is the disk bootstrap. Write sim/out/disk.bin")
    parser.add_argument("--uart-disk", action="store_true",
                        help="ROM is the UART bootstrap. Same disk.bin, stored in DDR3")
    args = parser.parse_args()
    n = args.mov_iter if args.mov_iter is not None else args.max_iter
    info = link(n, break_arm=args.break_arm, flash_boot=args.flash_boot,
                uart_disk=args.uart_disk)
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
        f"desc {info['desc']:#x} string {info['string']:#x} delay {info['delay_word']:08x}"
    )
    print(
        f"[ok] arm {info['arm_addr']:#x} word {info['arm_word']:08x} "
        f"sum {info['code_sum']:08x} planted {info['planted_sum']:08x} "
        f"blink {info['blink_at']:#x} words {info['blink_words']}"
        + (" BREAK" if info["break_arm"] else "")
    )
    print(f"[ok] map {MAP_PATH}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
