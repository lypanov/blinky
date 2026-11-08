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


def _patch_delay(raw: bytes, code: list[int], n: int) -> bytes:
    hits = [i for i, word in enumerate(code) if (word & 0xF0F00000) == 0x60000000 and (word & 0xFFFF) == 1]
    if len(hits) != 1:
        raise SystemExit(f"Blink5 has {len(hits)} MHI 1 words, wanted the 65536 assignment")
    index = hits[0]
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


def link(max_iter: int) -> dict:
    mods = _load_modules()
    payload = _compile_payload()
    blink_key = payload["AMemoryMappedToggle"]["key"]
    got = [k for name, k in payload["Blink5"]["imports"] if name == "AMemoryMappedToggle"]
    if got != [blink_key]:
        raise SystemExit(f"Blink5 import key {got} != AMemoryMappedToggle {blink_key:#x}")
    raw, delay_word, delay_index = _patch_delay(
        payload["Blink5"]["raw"], payload["Blink5"]["code"], max_iter
    )
    payload["Blink5"]["raw"] = raw

    data_base, _, desc_at = _assign(mods)
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

    a = Asm()
    a.word(f1(0, 12, 0, 0x20))
    a.word(f1(0, 14, 0, STACK))
    # HyperRAM powers up as ones. The init stream stores only non-zero
    # words, so a NIL link or a zero variable would stay 0xFFFFFFFF and
    # Load would walk the module list forever. Clear the static image
    # first; the pairs below overwrite the live words.
    static_end = desc_at + DESC_SIZE
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
    a.at(lambda pc: cond_branch(pc, body, 7))
    stub = a.encode(STUB_PC)
    if a.labels["done"] + 0 != a.labels["done"]:
        raise SystemExit("stub labels")
    # The branch at done must reach the Modules body.
    done_pc = a.labels["done"]
    if cond_branch(done_pc, body, 7) != stub[(done_pc - STUB_PC) // 4]:
        raise SystemExit("stub branch does not encode the body")

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
    # The three pages are mostly zeros. A scan of the live pairs fits in
    # the same ROM; a flat 768-word image does not.
    nz = [(i, w) for i, w in enumerate(raw_sector[:768]) if w]
    sector = []
    for index, word in nz:
        sector.extend((index, word))

    rom = [0] * ROM_WORDS
    regions = [
        ("stub", 0, stub),
        ("code", len(stub), words),
        ("init", len(stub) + len(words), stream),
        ("sector", len(stub) + len(words) + len(stream), sector),
    ]
    used = 0
    for _name, at, chunk in regions:
        if at + len(chunk) > ROM_WORDS:
            raise SystemExit(
                f"ROM needs {at + len(chunk)} words, {ROM_WORDS} exist "
                f"(stub {len(stub)}, code {len(words)}, init {len(stream)}, sector {len(sector)})"
            )
        for i, word in enumerate(chunk):
            rom[at + i] = word & 0xFFFFFFFF
        used = at + len(chunk)
    light = _light(payload["AMemoryMappedToggle"])
    info = {
        "stub_words": len(stub),
        "core_base": CORE_BASE,
        "core_words": len(words),
        "core_rom": len(stub),
        "init_base": INIT_BASE,
        "init_words": len(stream),
        "init_rom": len(stub) + len(words),
        "body_lo": BODY_LO,
        "body_hi": BODY_HI,
        "body": body,
        "light": light,
        "sector_rom": len(stub) + len(words) + len(stream),
        "sector_words": len(sector),
        "sector_pairs": len(sector) // 2,
        "rom_words": ROM_WORDS,
        "used": used,
        "delay_word": delay_word,
        "delay_index": delay_index,
        "desc": desc_at,
        "data": data_base,
        "string": string_at,
        "counts": {name: sum(1 for n, _i in seen if n == name) for name in ORDER},
        "words": rom,
    }
    return info


def write_map(info: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = (
        "stub_words", "core_base", "core_words", "core_rom",
        "init_base", "init_words", "init_rom",
        "body_lo", "body_hi", "body", "light",
        "sector_rom", "sector_words", "sector_pairs", "rom_words", "delay_word", "desc", "string",
    )
    with open(path, "w") as out:
        out.write("split=1\n")
        for key in fields:
            out.write(f"{key}={info[key]}\n")


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
    args = parser.parse_args()
    n = args.mov_iter if args.mov_iter is not None else args.max_iter
    info = link(n)
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
    print(f"[ok] map {MAP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
