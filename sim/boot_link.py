#!/usr/bin/env python3
"""Boot file from Norebo's CoreLinker, ROM from oberon/src/BootLoad.Mod.

The published 2013 sources have no separate linker. CoreLinker.Mod in the
pinned Norebo tree is Modules.Load turned into a file. LinkDisk writes the
directory sector and the image. BootLoad copies that image to address 0.
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from inner_core import ORDER, load_inner  # noqa: E402
from link_inner import (  # noqa: E402
    ARM_ADDR,
    ARM_WORD,
    DISK_DDR,
    FLASH_BASE,
    HALT_WORD,
    HEAP_BYTES,
    LIMIT,
    MEMLIM,
    STACK,
    SUM_ADDR,
    _append_arm,
    _arm_prologue,
    _drop_collect,
    _mark_scan,
)
from rsc_parser import parse_rsc  # noqa: E402
from sector_image import (  # noqa: E402
    DIR_MARK,
    HEADER_SIZE,
    SECTOR,
    _dir_page,
    _file_pages,
    rate_page,
)

DESC = 80
MT_ORG = 0x20
DIR_MARK_DISK = 0x9B1EA38D
MAGIC = 0x314B5344
VERSION = 1
BUILD = 0xE1
HEADER_BYTES = 20
BOOT_ROM = 512
PAGE_LIMIT = 80
NEXT = 32
KEY = 36
NUM = 40
SIZE = 44
REFCNT = 48
DATA = 52
CODE = 56
IMP = 60
CMD = 64
ENT = 68
PTR = 72


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


class Mem:
    def __init__(self, image: bytes, limit: int) -> None:
        self.b = bytearray(limit)
        self.b[: len(image)] = image

    def get(self, addr: int) -> int:
        return int.from_bytes(self.b[addr : addr + 4], "little")

    def put(self, addr: int, value: int) -> None:
        self.b[addr : addr + 4] = _u32(value).to_bytes(4, "little")

    def put_byte(self, addr: int, value: int) -> None:
        self.b[addr] = value & 0xFF


class Cursor:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.i = 0

    def byte(self) -> int:
        value = self.d[self.i]
        self.i += 1
        return value

    def word(self) -> int:
        value = _s32(int.from_bytes(self.d[self.i : self.i + 4], "little"))
        self.i += 4
        return value

    def chars(self) -> str:
        end = self.d.index(0, self.i)
        text = self.d[self.i : end].decode("ascii")
        self.i = end + 1
        return text


def _name_at(mem: Mem, addr: int) -> str:
    raw = bytes(mem.b[addr : addr + 32])
    return raw.split(b"\0", 1)[0].decode("ascii")


def _find(mem: Mem, root: int, name: str) -> int:
    seen = set()
    mod = root
    while mod and mod not in seen:
        seen.add(mod)
        if _name_at(mem, mod) == name:
            return mod
        mod = mem.get(mod + NEXT)
    return 0


def _load(mem: Mem, root: int, alloc: int, name: str, files: dict[str, bytes]) -> tuple[int, int]:
    """Modules.Load, without calling the body. Returns the new root and AllocPtr."""
    have = _find(mem, root, name)
    if have:
        return root, alloc
    cur = Cursor(files[name])
    got = cur.chars()
    if got != name:
        raise SystemExit(f"{name}.rsc starts with {got}")
    key = cur.word()
    version = cur.byte()
    if version != 1:
        raise SystemExit(f"{name} version {version}")
    size = cur.word()
    imports = []
    while cur.d[cur.i] != 0:
        imp = cur.chars()
        imp_key = cur.word()
        imports.append((imp, imp_key))
        root, alloc = _load(mem, root, alloc, imp, files)
        found = _find(mem, root, imp)
        if not found:
            raise SystemExit(f"{name} import {imp} did not load")
        if _s32(mem.get(found + KEY)) != imp_key:
            raise SystemExit(
                f"{name} import {imp} key {imp_key:#x} != {_s32(mem.get(found + KEY)):#x}"
            )
    cur.byte()
    need = size + DESC
    if alloc + need >= LIMIT:
        raise SystemExit(f"{name} needs {need} bytes at {alloc:#x}, limit is {LIMIT:#x}")
    base = alloc
    alloc = ((base + need + 0x100) // 0x20) * 0x20
    num = mem.get(root + NUM) + 1
    raw_name = name.encode("ascii") + bytes(32)
    mem.b[base : base + 32] = raw_name[:32]
    mem.put(base + NEXT, root)
    mem.put(base + KEY, key)
    mem.put(base + NUM, num)
    mem.put(base + SIZE, alloc - base)
    mem.put(base + REFCNT, 0)
    p = base + DESC
    mem.put(base + DATA, p)
    mem.put(MT_ORG + num * 4, p)
    n = cur.word()
    if n % 4:
        raise SystemExit(f"{name} type descriptors are {n} bytes")
    while n > 0:
        mem.put(p, cur.word())
        p += 4
        n -= 4
    n = cur.word()
    if n % 4:
        raise SystemExit(f"{name} variables are {n} bytes")
    while n > 0:
        mem.put(p, 0)
        p += 4
        n -= 4
    n = cur.word()
    while n > 0:
        mem.put_byte(p, cur.byte())
        p += 1
        n -= 1
    if p % 4:
        raise SystemExit(f"{name} code would start at {p:#x}")
    mem.put(base + CODE, p)
    n = cur.word()
    while n > 0:
        mem.put(p, cur.word())
        p += 4
        n -= 1
    mem.put(base + IMP, p)
    for imp, _imp_key in imports:
        mem.put(p, _find(mem, base, imp))
        p += 4
    mem.put(base + CMD, p)
    ch = cur.byte()
    while ch != 0:
        while True:
            mem.put_byte(p, ch)
            p += 1
            ch = cur.byte()
            if ch == 0:
                break
        while p % 4:
            mem.put_byte(p, 0)
            p += 1
        mem.put(p, cur.word())
        p += 4
        ch = cur.byte()
    while True:
        mem.put_byte(p, 0)
        p += 1
        if p % 4 == 0:
            break
    mem.put(base + ENT, p)
    n = cur.word()
    while n > 0:
        mem.put(p, cur.word())
        p += 4
        n -= 1
    mem.put(base + PTR, p)
    data = mem.get(base + DATA)
    w = cur.word()
    while w >= 0:
        mem.put(p, data + w)
        p += 4
        w = cur.word()
    mem.put(p, 0)
    p += 4
    fix_p, fix_d, fix_t = cur.word(), cur.word(), cur.word()
    entry = cur.word()
    if cur.byte() != ord("O"):
        raise SystemExit(f"{name} has no O marker")
    if p > base + size + DESC:
        raise SystemExit(f"{name} copy ends at {p:#x}, allocation is {base + size + DESC:#x}")
    _fix(mem, base, fix_p, fix_d, fix_t)
    print(
        f"[ok] load {name} num {num} at {base:#x} data {data:#x} "
        f"code {mem.get(base + CODE):#x} entry {entry:#x}"
    )
    return base, alloc


def _fix(mem: Mem, base: int, fix_p: int, fix_d: int, fix_t: int) -> None:
    code = mem.get(base + CODE)
    data = mem.get(base + DATA)
    imp = mem.get(base + IMP)
    num = mem.get(base + NUM)
    adr = code + fix_p * 4
    seen = set()
    while adr != code:
        if adr in seen:
            raise SystemExit(f"fixup P at {base:#x} looped")
        seen.add(adr)
        inst = mem.get(adr)
        mno = (inst // 0x100000) % 0x10
        pno = (inst // 0x1000) % 0x100
        disp = inst % 0x1000
        other = mem.get(imp + (mno - 1) * 4)
        dest = mem.get(mem.get(other + ENT) + pno * 4) + mem.get(other + CODE)
        offset = (dest - adr - 4) // 4
        mem.put(adr, (offset % 0x1000000) + 0xF7000000)
        adr -= disp * 4
    adr = code + fix_d * 4
    seen = set()
    while adr != code:
        if adr in seen:
            raise SystemExit(f"fixup D at {base:#x} looped")
        seen.add(adr)
        inst = mem.get(adr)
        mno = (inst // 0x100000) % 0x10
        disp = inst % 0x1000
        if mno == 0:
            mem.put(adr, ((inst // 0x1000000) * 0x10 + 12) * 0x100000 + num * 4)
        else:
            other = mem.get(imp + (mno - 1) * 4)
            v = mem.get(other + NUM)
            mem.put(adr, ((inst // 0x1000000) * 0x10 + 12) * 0x100000 + v * 4)
            nxt = mem.get(adr + 4)
            vno = nxt % 0x100
            offset = _s32(mem.get(mem.get(other + ENT) + vno * 4))
            if (nxt // 0x100) % 2:
                offset += mem.get(other + CODE) - mem.get(other + DATA)
            high = (_s32(nxt) // 0x10000) * 0x10000
            mem.put(adr + 4, high + offset)
        adr -= disp * 4
    adr = data + fix_t * 4
    seen = set()
    while adr != data:
        if adr in seen:
            raise SystemExit(f"fixup T at {base:#x} looped")
        seen.add(adr)
        inst = mem.get(adr)
        mno = (inst // 0x1000000) % 0x10
        vno = (inst // 0x1000) % 0x1000
        disp = inst % 0x1000
        if mno == 0:
            inst = data + vno
        else:
            other = mem.get(imp + (mno - 1) * 4)
            offset = _s32(mem.get(mem.get(other + ENT) + vno * 4))
            inst = mem.get(other + DATA) + offset
        mem.put(adr, inst)
        adr -= disp * 4


def _code_sum(mem: Mem, base: int) -> tuple[int, int, int]:
    code = mem.get(base + CODE)
    end = mem.get(base + IMP)
    total = 0
    addr = code
    while addr < end:
        total = _u32(total + mem.get(addr))
        addr += 4
    return total, code, (end - code) // 4


def _norebo() -> dict[str, str]:
    script = f"""
set -euo pipefail
source "{ROOT}/tools/norebo_env.sh"
norebo_export
printf '%s\\n' "$NOREBO_BIN" "$NOREBO_ROOT" "$NOREBO_PATH"
"""
    out = subprocess.check_output(["bash", "-c", script], text=True)
    binary, norebo_root, path = out.splitlines()
    return {"bin": binary, "root": norebo_root, "path": path}


def _run(cmd: list[str], cwd: str, env: dict[str, str]) -> str:
    got = subprocess.check_output(cmd, cwd=cwd, env=env, stderr=subprocess.STDOUT)
    text = got.decode("latin1", errors="replace")
    if "FAILED" in text:
        raise SystemExit(text)
    return text


def _link_core(env: dict[str, str]) -> bytes:
    load_inner()
    work = os.path.join(ROOT, "sim", "out", "bootlink")
    os.makedirs(work, exist_ok=True)
    cache = os.path.join(ROOT, "sim", "inner-core")
    for name in ORDER:
        raw = open(os.path.join(cache, f"{name}.rsc"), "rb").read()
        open(os.path.join(work, f"{name}.rsx"), "wb").write(raw)
    path = work + ":" + env["path"]
    run_env = dict(os.environ)
    run_env["NOREBO_BIN"] = env["bin"]
    run_env["NOREBO_ROOT"] = env["root"]
    run_env["NOREBO_PATH"] = path
    text = _run([env["bin"], "CoreLinker.LinkDisk", "Modules", "boot.dsk"], work, run_env)
    print(text, end="" if text.endswith("\n") else "\n")
    data = open(os.path.join(work, "boot.dsk"), "rb").read()
    if int.from_bytes(data[:4], "little") != DIR_MARK_DISK:
        raise SystemExit("CoreLinker boot file has no directory mark")
    if b"Blink5" in data:
        raise SystemExit("the boot image already contains Blink5")
    if data.count(b"Oberon\x00") != 1:
        raise SystemExit(f"Oberon occurs {data.count(b'Oberon' + bytes([0]))} times in the boot file")
    return data


def _compile_boot(env: dict[str, str], uart: int) -> list[int]:
    src = open(os.path.join(ROOT, "oberon", "src", "BootLoad.Mod"), "r", encoding="ascii").read()
    if "MemLim = 19D00H" not in src or "stackOrg = 18000H" not in src:
        raise SystemExit("BootLoad.Mod constants are not MemLim 19D00H and stack 18000H")
    if MEMLIM != 0x19D00 or STACK != 0x18000 or DISK_DDR != 0x21000:
        raise SystemExit(
            f"heap constants {STACK:#x}..{MEMLIM:#x} disk {DISK_DDR:#x} "
            "do not match BootLoad.Mod"
        )
    lines = []
    replaced = False
    for line in src.splitlines(True):
        if line.startswith("    Uart = ") and not replaced:
            lines.append(f"    Uart = {uart};\n")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise SystemExit("BootLoad.Mod has no Uart constant")
    work = os.path.join(ROOT, "sim", "out", "bootload")
    os.makedirs(work, exist_ok=True)
    open(os.path.join(work, "BootLoad.Mod"), "w", encoding="ascii").write("".join(lines))
    run_env = dict(os.environ)
    run_env.update(NOREBO_BIN=env["bin"], NOREBO_ROOT=env["root"], NOREBO_PATH=env["path"])
    text = _run([env["bin"], "ORP.Compile", "BootLoad.Mod"], work, run_env)
    print(text, end="" if text.endswith("\n") else "\n")
    data = open(os.path.join(work, "BootLoad.rsc"), "rb").read()
    off = data.index(0) + 1
    off += 5 + 4
    if data[off] != 0:
        raise SystemExit("BootLoad imports a module")
    off += 1
    td = struct.unpack_from("<I", data, off)[0]
    off += 4 + td
    off += 4
    strx = struct.unpack_from("<I", data, off)[0]
    off += 4 + strx
    ncode = struct.unpack_from("<I", data, off)[0]
    off += 4
    words = list(struct.unpack_from("<" + "I" * ncode, data, off))
    if not 1 <= len(words) <= BOOT_ROM:
        raise SystemExit(f"BootLoad is {len(words)} words")
    if (words[0] >> 24) != 0xE7:
        raise SystemExit(f"BootLoad word 0 is {words[0]:08X}")
    if words[-2:] != [0x40000000, 0xC7000000]:
        raise SystemExit("BootLoad does not return through R0")

    def movs(imm: int) -> int:
        return sum(1 for w in words if (w >> 28) == 5 and (w & 0xFFFF) == (imm & 0xFFFF))

    for imm, label in ((-72, "word port"), (-68, "sector base"), (-48, "SPI data"), (-44, "SPI ctrl")):
        if movs(imm) < 1:
            raise SystemExit(f"BootLoad has no MOV of {label}")
    if movs(-60) or movs(-80):
        raise SystemExit("BootLoad touches the button or the screen")
    if not any((w & 0xFFFF) == 0xE7FF for w in words):
        raise SystemExit("BootLoad does not build the halt word")
    return words


def _compile_files(env: dict[str, str]) -> dict[str, bytes]:
    # Isolated from sim/payload. Norebo's inner core loads module Oberon
    # from the working directory before the command, so a leftover
    # Oberon.rsc here would run Blink5.Go and never reach the compiler.
    work = os.path.join(ROOT, "sim", "out", "bootfiles")
    os.makedirs(work, exist_ok=True)
    for name in os.listdir(work):
        if name.endswith((".rsc", ".smb", ".Mod")):
            os.remove(os.path.join(work, name))
    cache = os.path.join(ROOT, "sim", "inner-core")
    for name in ORDER:
        src = os.path.join(cache, f"{name}.smb")
        open(os.path.join(work, f"{name}.smb"), "wb").write(open(src, "rb").read())
    for name in ("AMemoryMappedToggle", "Blink5", "Oberon"):
        src = os.path.join(ROOT, "tests", f"{name}.Mod")
        open(os.path.join(work, f"{name}.Mod"), "wb").write(open(src, "rb").read())
    run_env = dict(os.environ)
    run_env.update(NOREBO_BIN=env["bin"], NOREBO_ROOT=env["root"], NOREBO_PATH=env["path"])
    text = ""
    for name in ("AMemoryMappedToggle", "Blink5", "Oberon"):
        stale = os.path.join(work, "Oberon.rsc")
        if os.path.exists(stale):
            os.remove(stale)
        text += _run([env["bin"], "ORP.Compile", f"{name}.Mod/s"], work, run_env)
    print(text, end="" if text.endswith("\n") else "\n")
    out = {}
    for name in ("AMemoryMappedToggle", "Blink5", "Oberon"):
        path = os.path.join(work, f"{name}.rsc")
        raw = open(path, "rb").read()
        if len(raw) > SECTOR - HEADER_SIZE + SECTOR:
            raise SystemExit(f"{name}.rsc is {len(raw)} bytes and needs a third sector")
        out[name] = raw
    return out


def _checksum(payload: bytes) -> int:
    total = 0
    for i in range(0, len(payload), 4):
        total = _u32(total + int.from_bytes(payload[i : i + 4], "little"))
    return total


def make(max_iter: int, break_arm: bool = False, flash_boot: bool = False,
         uart_disk: bool = False, no_collect: bool = False) -> dict:
    if flash_boot == uart_disk:
        raise SystemExit("pass one of flash boot or the UART disk")
    if max_iter % 2 or not 1 <= max_iter <= 0x7FFF:
        raise SystemExit(f"rate {max_iter} must be a positive even millisecond count")
    env = _norebo()
    boot = _link_core(env)
    image = bytearray(boot[SECTOR:])
    if len(image) % 4:
        raise SystemExit(f"boot image is {len(image)} bytes")
    alloc = int.from_bytes(image[16:20], "little")
    root = int.from_bytes(image[20:24], "little")
    if alloc != len(image):
        raise SystemExit(f"AllocPtr {alloc:#x} is not the image length {len(image):#x}")
    if int.from_bytes(image[28:32], "little") != 0:
        raise SystemExit("address 28 is already used")
    files = _compile_files(env)
    blink = parse_rsc(os.path.join(ROOT, "sim", "out", "bootfiles", "Blink5.rsc"), output_format="quiet")
    blink["raw"] = files["Blink5"]
    names = [item[0] for item in blink["imports"]]
    if names != ["AMemoryMappedToggle", "Kernel", "Modules", "Files"]:
        raise SystemExit(f"Blink5 imports {names}")
    if no_collect:
        kernel = parse_rsc(os.path.join(ROOT, "sim", "inner-core", "Kernel.rsc"), output_format="quiet")
        mark, scan = _mark_scan(kernel["code"], kernel["entries"])
        kernel_mno = names.index("Kernel") + 1
        files["Blink5"] = _drop_collect(
            files["Blink5"], blink["code"], kernel_mno, {mark[0], scan[0]}
        )
    # Oberon is module 5, its import of nothing new leaves it as root, then
    # Blink5's first import is AMemoryMappedToggle (6) and Blink5 is 7.
    blink_mt = 0x20 + 7 * 4
    prologue = _arm_prologue(
        with_disk=True, memlim=MEMLIM, alloc=alloc, root=root, stack=STACK, blink_mt=blink_mt
    )
    files["Blink5"] = _append_arm(files["Blink5"], prologue)
    mem = Mem(bytes(image), LIMIT)
    root_now, alloc_now = _load(mem, root, alloc, "Oberon", files)
    if mem.get(root_now + NUM) != 5:
        raise SystemExit(f"Oberon is module {mem.get(root_now + NUM)}")
    root_now, alloc_now = _load(mem, root_now, alloc_now, "Blink5", files)
    if mem.get(root_now + NUM) != 7 or _name_at(mem, root_now) != "Blink5":
        raise SystemExit(f"root is {_name_at(mem, root_now)} num {mem.get(root_now + NUM)}")
    if alloc_now > LIMIT:
        raise SystemExit(f"allocation ends at {alloc_now:#x}, limit is {LIMIT:#x}")
    ammt = _find(mem, root_now, "AMemoryMappedToggle")
    if mem.get(ammt + NUM) != 6:
        raise SystemExit(f"AMemoryMappedToggle is module {mem.get(ammt + NUM)}")
    # No type descriptor: the exported light is the first variable.
    if mem.get(ammt + DATA) != ammt + DESC:
        raise SystemExit("AMemoryMappedToggle data is not the descriptor tail")
    light = mem.get(ammt + DATA)
    code_sum, blink_at, blink_words = _code_sum(mem, root_now)
    planted = _u32(code_sum + (1 if break_arm else 0))
    image[SUM_ADDR : SUM_ADDR + 4] = planted.to_bytes(4, "little")

    boot_pages = (len(image) + SECTOR - 1) // SECTOR
    which = 1 + boot_pages
    page_bytes: dict[int, bytes] = {}
    entries = []
    order = (
        (b"AMemoryMappedToggle.rsc", files["AMemoryMappedToggle"]),
        (b"Blink.Rate", None),
        (b"Blink5.rsc", files["Blink5"]),
        (b"Oberon.rsc", files["Oberon"]),
    )
    if list(order) != sorted(order, key=lambda item: item[0]):
        raise SystemExit("directory names are not in order")
    for filename, raw in order:
        sector = (which + 1) * 29
        if raw is None:
            page_bytes[sector] = rate_page(max_iter, sector)
            entries.append((filename, sector))
            which += 1
            continue
        cont = None
        if len(raw) > SECTOR - HEADER_SIZE:
            cont = (which + 2) * 29
        built = _file_pages(filename, raw, sector, cont)
        for sec, page in built:
            page_bytes[sec] = page
        entries.append((filename, sector))
        which += len(built)
    if which > PAGE_LIMIT:
        raise SystemExit(f"disk uses page {which}, the window ends at {PAGE_LIMIT}")
    payload = bytearray(_dir_page(entries))
    payload += bytes(image) + bytes(boot_pages * SECTOR - len(image))
    for w in range(1 + boot_pages, which):
        payload += page_bytes[(w + 1) * 29]
    if len(payload) != which * SECTOR:
        raise SystemExit("payload pages are not contiguous")
    # The last ReadSD of a short image reads at most 511 bytes of padding.
    spill = ((len(image) + 511) // 512) * 512
    if spill > boot_pages * SECTOR:
        raise SystemExit("the boot copy reads past the padded image")
    total = _checksum(bytes(payload))
    disk = struct.pack("<5I", MAGIC, VERSION, BUILD, len(payload), total) + bytes(payload)
    if FLASH_BASE + len(disk) >= 0x400000:
        raise SystemExit(f"disk ends at {FLASH_BASE + len(disk):#x}")
    if DISK_DDR + len(payload) >= 49152 * 4:
        raise SystemExit("UART disk does not fit the HyperRAM stand-in")
    rate_sec = next(sec for name, sec in entries if name == b"Blink.Rate")
    rate_at = HEADER_BYTES + (rate_sec // 29 - 1) * SECTOR + HEADER_SIZE
    got = struct.unpack_from("<ii", disk, rate_at)
    if got != (max_iter, -max_iter):
        raise SystemExit(f"rate bytes at {rate_at} are {got}")
    if int.from_bytes(disk[HEADER_BYTES : HEADER_BYTES + 4], "little") != DIR_MARK:
        raise SystemExit("payload does not start with the directory")
    branch = int.from_bytes(image[:4], "little")
    body = 4 + (branch & 0xFFFFFF) * 4
    string_at = image.find(b"Oberon\x00")
    if string_at < 0:
        raise SystemExit("the image has no Oberon string")
    rom_code = _compile_boot(env, 1 if uart_disk else 0)
    other = _compile_boot(env, 0 if uart_disk else 1)
    diffs = [i for i, (a, b) in enumerate(zip(rom_code, other)) if a != b]
    if not diffs or any((rom_code[i] & 0xFFFF0000) != 0x40000000 for i in diffs):
        raise SystemExit(f"flash and UART BootLoad differ at {diffs}")
    rom = list(rom_code) + [HALT_WORD] * (BOOT_ROM - len(rom_code))
    counts = {}
    mod = root
    while mod:
        counts[_name_at(Mem(bytes(image), LIMIT), mod)] = (
            int.from_bytes(image[mod + IMP : mod + IMP + 4], "little")
            - int.from_bytes(image[mod + CODE : mod + CODE + 4], "little")
        ) // 4
        mod = int.from_bytes(image[mod + NEXT : mod + NEXT + 4], "little")
    walk = root
    kernel_at = 0
    while walk:
        if bytes(image[walk : walk + 32]).split(b"\0", 1)[0] == b"Kernel":
            kernel_at = walk
            break
        walk = int.from_bytes(image[walk + NEXT : walk + NEXT + 4], "little")
    if not kernel_at:
        raise SystemExit("the boot image has no Kernel descriptor")
    kernel_code = int.from_bytes(image[kernel_at + CODE : kernel_at + CODE + 4], "little")
    kernel_imp = int.from_bytes(image[kernel_at + IMP : kernel_at + IMP + 4], "little")
    time_at = next(
        kernel_code + i * 4
        for i in range((kernel_imp - kernel_code) // 4)
        if int.from_bytes(image[kernel_code + i * 4 : kernel_code + i * 4 + 4], "little") == 0x5000FFC0
    )
    return {
        "stub_words": len(rom_code),
        "core_base": 0,
        "core_words": len(image) // 4,
        "core_rom": 0,
        "init_base": 0,
        "init_words": 0,
        "init_rom": 0,
        "body_lo": 0,
        "body_hi": LIMIT,
        "body": body,
        "light": light,
        "sector_rom": 0,
        "sector_words": 0,
        "sector_pairs": 0,
        "rom_words": BOOT_ROM,
        "used": len(rom_code),
        "delay_word": max_iter,
        "time": time_at,
        "delay_index": rate_at,
        "rate_sec": rate_sec,
        "rate_at": rate_at,
        "desc": root,
        "arm_addr": ARM_ADDR,
        "arm_word": _u32(ARM_WORD ^ total),
        "code_sum": code_sum,
        "planted_sum": planted,
        "blink_at": blink_at,
        "blink_words": blink_words,
        "break_arm": int(break_arm),
        "flash_boot": int(flash_boot),
        "uart_disk": int(uart_disk),
        "string": string_at,
        "counts": {name: counts[name] for name in ORDER},
        "words": rom,
        "disk": disk,
        "disk_checksum": total,
        "heap_bytes": HEAP_BYTES,
    }
