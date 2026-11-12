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
    KEPT,
    LIMIT,
    MEMLIM,
    SHORT_MEMLIM,
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
    PAYLOAD_LIMIT,
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


def _check_first_store(words: list[int]) -> None:
    """The body's first store is stage 1 at -84. Straight-line MOVs until then."""
    w0 = words[0]
    if (w0 >> 24) != 0xE7:
        raise SystemExit(f"BootLoad word 0 is {w0:08X}")
    off = w0 & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    pc = 1 + off
    reg = [0] * 16
    for _ in range(12):
        if not 0 <= pc < len(words):
            raise SystemExit("BootLoad ran off the image before its first store")
        w = words[pc]
        top = w >> 28
        if top in (0xA, 0xB):
            ra = (w >> 24) & 0xF
            rb = (w >> 20) & 0xF
            disp = w & 0xFFFFF
            if disp & 0x80000:
                disp -= 0x100000
            addr = (reg[rb] + disp) & 0xFFFFFFFF
            data = reg[ra] & (0xFF if top == 0xB else 0xFFFFFFFF)
            if addr != 0xFFFFFFAC or (data & 0x1FF) != 0x1:
                raise SystemExit(
                    f"BootLoad first store is {data:#x} at {addr:#x}, want stage 1 at -84"
                )
            return
        if top not in (4, 5):
            raise SystemExit(f"BootLoad word {pc} is {w:08X} before the status store")
        rd = (w >> 24) & 0xF
        rb = (w >> 20) & 0xF
        op = (w >> 16) & 0xF
        imm = w & 0xFFFF
        if top == 5 and imm & 0x8000:
            simm = imm - 0x10000
        else:
            simm = imm
        if op == 0 and top in (4, 5):
            reg[rd] = simm & 0xFFFFFFFF
        elif op == 8 and top in (4, 5):
            reg[rd] = (reg[rb] + simm) & 0xFFFFFFFF
        else:
            raise SystemExit(f"BootLoad word {pc} is {w:08X} before the status store")
        pc += 1
    raise SystemExit("BootLoad has no status store in the first instructions of the body")


def _compile_boot(env: dict[str, str], uart: int, memlim: int | None = None) -> list[int]:
    src = open(os.path.join(ROOT, "oberon", "src", "BootLoad.Mod"), "r", encoding="ascii").read()
    mem_text = f"MemLim = {MEMLIM:X}H"
    disk_text = f"DiskOrg = {DISK_DDR:X}H"
    if mem_text not in src or "stackOrg = 18000H" not in src or disk_text not in src:
        raise SystemExit(
            f"BootLoad.Mod constants are not {mem_text}, stack 18000H, {disk_text}"
        )
    if MEMLIM != 0x28000 or STACK != 0x18000 or DISK_DDR != 0x29000 or KEPT != 1247:
        raise SystemExit(
            f"heap constants {STACK:#x}..{MEMLIM:#x} disk {DISK_DDR:#x} kept {KEPT} "
            "do not match BootLoad.Mod"
        )
    if memlim is None:
        memlim = MEMLIM
    if memlim != MEMLIM:
        src = src.replace(mem_text, f"MemLim = {memlim:X}H", 1)
        if src.count(f"MemLim = {memlim:X}H") != 1:
            raise SystemExit(f"short MemLim {memlim:#x} did not land in BootLoad")
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

    for imm, label in ((-72, "word port"), (-68, "sector base"), (-48, "SPI data"), (-44, "SPI ctrl"), (-84, "status")):
        if movs(imm) < 1:
            raise SystemExit(f"BootLoad has no MOV of {label}")
    if movs(-60) or movs(-80):
        raise SystemExit("BootLoad touches the button or the screen")
    _check_first_store(words)
    if not any((w & 0xFFFF) == 0xE7FF for w in words):
        raise SystemExit("BootLoad does not build the halt word")
    return words


def _with_index_trap(text: str) -> str:
    """The module body indexes past an array of 4.

    The index is a variable, so ORG emits the runtime check: trap 1,
    condition CC. Load calls this body before ThisCommand, so Blink.Run
    is never entered. The arm prologue is left off this disk, and the
    entry stays on this body, so the store at 0x7C0 never runs.
    """
    var = "  VAR last, now, wait, keys, n, due, half, thousand: INTEGER;\n"
    body = "BEGIN\nEND Blink.\n"
    if text.count(var) != 1 or text.count(body) != 1:
        raise SystemExit("Blink.Mod has no single place for the index trap")
    text = text.replace(
        var,
        var + "    sample: ARRAY 4 OF INTEGER;\n    idx: INTEGER;\n",
        1,
    )
    return text.replace(
        body,
        "BEGIN\n"
        "  idx := 4;\n"
        "  sample[idx] := 0\n"
        "END Blink.\n",
        1,
    )


def _check_index_trap(code: list[int], entry: int) -> None:
    """One BLR, condition CC, trap number 1, in the body that is the entry."""
    if entry % 4:
        raise SystemExit(f"index-trap entry {entry:#x} is not a word")
    start = entry // 4
    hits = [i for i, word in enumerate(code) if (word & 0xFF0000FF) == 0xDA00001C]
    if len(hits) != 1:
        raise SystemExit(f"index trap encodings {len(hits)}, wanted one")
    at = hits[0]
    if not start <= at < start + 40:
        raise SystemExit(f"index trap at word {at}, entry word {start}")
    arm = [
        i for i, word in enumerate(code)
        if (word & 0xF0FF0000) in (0x40000000, 0x50000000) and (word & 0xFFFF) == 0x07C0
    ]
    if arm:
        raise SystemExit(f"index-trap Blink loads the arm address at {arm}")
    print(f"[ok] index trap word {at} entry {start} insn {code[at]:08X}")


def _check_trap_status(code: list[int]) -> None:
    """The failed trap stores the status byte at -84. Trap 0 does not."""
    ports = [i for i, word in enumerate(code) if (word & 0xF0FFFFFF) == 0x5000FFAC]
    if len(ports) != 1:
        raise SystemExit(f"Kernel has {len(ports)} MOV -84, wanted the trap status store")
    print(f"[ok] trap status store at Kernel word {ports[0]}")


def _board_text(name: str, dock: bool) -> str:
    """The 4K constants are the source. The Dock replaces those lines."""
    text = open(os.path.join(ROOT, "tests", f"{name}.Mod"), "r", encoding="ascii").read()
    if not dock:
        return text
    reps = {
        "Display": [(
            "width = 256; height = 120; base = -131072;",
            "width = 512; height = 384; base = -98304;",
        )],
        "Blink5": [
            (
                "sqX = 75; sqY = 55; sqW = 5; sqH = 5;",
                "sqX = 150; sqY = 110; sqW = 10; sqH = 10;",
            ),
            ("mkX = 80; mkY = 55;", "mkX = 143; mkY = 110;"),
            ("tx = 64; ty = 40;", "tx = 96; ty = 96;"),
        ],
        "Fonts": [('This("Tiny4x6.Fnt")', 'This("Oberon10.Scn.Fnt")')],
    }.get(name)
    if reps is None:
        return text
    for old, new in reps:
        if text.count(old) != 1:
            raise SystemExit(f"{name}.Mod has no single line {old}")
        text = text.replace(old, new, 1)
    return text


def _font_bytes(name: str, damage: bool) -> bytes:
    """A font file. Damage sets NofRuns to 17 so run[16] traps."""
    data = bytearray(open(os.path.join(ROOT, "tests", name), "rb").read())
    if len(data) < 16 or data[0] != 0xDB:
        raise SystemExit(f"{name} is not a font file")
    if damage:
        if data[14] == 17:
            raise SystemExit(f"{name} NofRuns is already 17")
        data[14] = 17
    return bytes(data)


# The source file is still tests/Blink5.Mod. The module name is Blink,
# so the command string is Blink.Run and the object is Blink.rsc.
_UNITS = (
    ("AMemoryMappedToggle", "AMemoryMappedToggle"),
    ("Display", "Display"),
    ("Fonts", "Fonts"),
    ("Texts", "Texts"),
    ("Blink", "Blink5"),
    ("Oberon", "Oberon"),
)


def _compile_files(env: dict[str, str], index_trap: bool = False,
                   dock: bool = False, bad_command: bool = False) -> dict[str, bytes]:
    # Isolated from sim/payload. Norebo loads every module it imports from
    # the working directory before the command. Oberon.rsc would run
    # Blink5.Go. Texts imports Fonts, and a Fonts.rsc left here is loaded
    # with the inner-core Files key, which norebo rejects. Compiled
    # objects are parked until every compile has finished.
    work = os.path.join(ROOT, "sim", "out", "bootfiles")
    os.makedirs(work, exist_ok=True)
    for name in os.listdir(work):
        if name.endswith((".rsc", ".smb", ".Mod")):
            os.remove(os.path.join(work, name))
    cache = os.path.join(ROOT, "sim", "inner-core")
    for name in ORDER:
        src = os.path.join(cache, f"{name}.smb")
        open(os.path.join(work, f"{name}.smb"), "wb").write(open(src, "rb").read())
    for dest, src_name in _UNITS:
        src = os.path.join(ROOT, "tests", f"{src_name}.Mod")
        if src_name == "Texts":
            body = open(src, "r", encoding="ascii").read()
        else:
            body = _board_text(src_name, dock)
        open(os.path.join(work, f"{dest}.Mod"), "w", encoding="ascii").write(body)
    if index_trap:
        path = os.path.join(work, "Blink.Mod")
        patched = _with_index_trap(open(path, encoding="utf-8").read())
        open(path, "w", encoding="utf-8").write(patched)
    if bad_command:
        path = os.path.join(work, "Oberon.Mod")
        body = open(path, encoding="utf-8").read()
        old = 'Call("Blink.Run", r)'
        if body.count(old) != 1:
            raise SystemExit("Oberon.Mod has no single Blink.Run call")
        open(path, "w", encoding="utf-8").write(body.replace(old, 'Call("Blink.Ran", r)', 1))
    run_env = dict(os.environ)
    run_env.update(NOREBO_BIN=env["bin"], NOREBO_ROOT=env["root"], NOREBO_PATH=env["path"])
    parked = os.path.join(work, "parked")
    os.makedirs(parked, exist_ok=True)
    text = ""
    for dest, _src_name in _UNITS:
        for fn in list(os.listdir(work)):
            if fn.endswith(".rsc"):
                os.replace(os.path.join(work, fn), os.path.join(parked, fn))
        text += _run([env["bin"], "ORP.Compile", f"{dest}.Mod/s"], work, run_env)
    for fn in list(os.listdir(parked)):
        if fn.endswith(".rsc"):
            os.replace(os.path.join(parked, fn), os.path.join(work, fn))
    print(text, end="" if text.endswith("\n") else "\n")
    out = {}
    for dest, _src_name in _UNITS:
        path = os.path.join(work, f"{dest}.rsc")
        raw = open(path, "rb").read()
        if len(raw) > PAYLOAD_LIMIT:
            raise SystemExit(
                f"{dest}.rsc is {len(raw)} bytes; "
                f"the header's 64 sector slots hold {PAYLOAD_LIMIT}"
            )
        out[dest] = raw
    return out


def _checksum(payload: bytes) -> int:
    total = 0
    for i in range(0, len(payload), 4):
        total = _u32(total + int.from_bytes(payload[i : i + 4], "little"))
    return total


def _hyper_bytes() -> int:
    path = os.path.join(ROOT, "sim", "HyperRamUserModel.v")
    text = open(path, "r", encoding="ascii").read()
    marker = "localparam integer WORDS = "
    line = next(item for item in text.splitlines() if item.strip().startswith(marker))
    words = int(line.split("=")[1].strip().rstrip(";"))
    return words * 4


def make(max_iter: int, break_arm: bool = False, flash_boot: bool = False,
         uart_disk: bool = False, no_collect: bool = False,
         index_trap: bool = False, short_heap: bool = False,
         bad_font: bool = False, bad_command: bool = False) -> dict:
    if flash_boot == uart_disk:
        raise SystemExit("pass one of flash boot or the UART disk")
    if index_trap and (no_collect or break_arm or bad_font or bad_command):
        raise SystemExit("the index trap is its own disk")
    if short_heap and (no_collect or break_arm or index_trap or bad_font or bad_command):
        raise SystemExit("the short heap is its own ROM, on the ordinary disk")
    if bad_font and (no_collect or break_arm or bad_command):
        raise SystemExit("the damaged font is its own disk")
    if bad_command and (no_collect or break_arm):
        raise SystemExit("the misspelt command is its own disk")
    if max_iter % 2 or not 1 <= max_iter <= 0x7FFF:
        raise SystemExit(f"rate {max_iter} must be a positive even millisecond count")
    env = _norebo()
    boot = _link_core(env)
    kernel = parse_rsc(os.path.join(ROOT, "sim", "inner-core", "Kernel.rsc"), output_format="quiet")
    _check_trap_status(kernel["code"])
    image = bytearray(boot[SECTOR:])
    if len(image) % 4:
        raise SystemExit(f"boot image is {len(image)} bytes")
    alloc = int.from_bytes(image[16:20], "little")
    root = int.from_bytes(image[20:24], "little")
    if alloc != len(image):
        raise SystemExit(f"AllocPtr {alloc:#x} is not the image length {len(image):#x}")
    if int.from_bytes(image[28:32], "little") != 0:
        raise SystemExit("address 28 is already used")
    files = _compile_files(
        env, index_trap=index_trap, dock=uart_disk, bad_command=bad_command,
    )
    blink = parse_rsc(os.path.join(ROOT, "sim", "out", "bootfiles", "Blink.rsc"), output_format="quiet")
    blink["raw"] = files["Blink"]
    names = [item[0] for item in blink["imports"]]
    if names != ["Files", "Fonts", "Texts", "Display", "AMemoryMappedToggle", "Kernel", "Modules"]:
        raise SystemExit(f"Blink imports {names}")
    if files["Blink"].count(b"Run\x00") != 1:
        raise SystemExit("Blink.rsc does not publish one command Run")
    if no_collect:
        kernel = parse_rsc(os.path.join(ROOT, "sim", "inner-core", "Kernel.rsc"), output_format="quiet")
        mark, scan = _mark_scan(kernel["code"], kernel["entries"])
        kernel_mno = names.index("Kernel") + 1
        files["Blink"] = _drop_collect(
            files["Blink"], blink["code"], kernel_mno, {mark[0], scan[0]}
        )
    # Oberon is module 5. Blink loads Texts, which loads Fonts first.
    # Fonts is 6, Texts 7, Display 8, AMemoryMappedToggle 9.
    # Blink itself is module 10.
    blink_mt = 0x20 + 10 * 4
    if index_trap:
        _check_index_trap(blink["code"], blink["entry_point"])
    else:
        # The entry table is the body, then kept*, then Run*.
        # Run* is also the one command. Its file offset is the third entry.
        run_at = files["Blink"].find(b"Run\x00")
        run_off = int.from_bytes(files["Blink"][run_at + 4 : run_at + 8], "little")
        if (
            len(blink["entries"]) != 3
            or blink["entries"][0] != blink["entry_point"]
            or blink["entries"][2] != run_off
        ):
            raise SystemExit(
                f"Blink entries {blink['entries']} entry {blink['entry_point']} "
                f"command {run_off:#x}"
            )
        kept_off = blink["entries"][1]
        if not isinstance(kept_off, int) or kept_off < 0:
            raise SystemExit(f"kept offset {kept_off!r} is not a byte offset")
        blink_src = open(os.path.join(ROOT, "tests", "Blink5.Mod"), "r", encoding="ascii").read()
        if f"WHILE kept < {KEPT} DO" not in blink_src or "ArmHook(7E37H)" not in blink_src:
            raise SystemExit("Blink.Mod does not publish the kept loop and the hook")
        prologue = _arm_prologue(
            with_disk=True, memlim=MEMLIM, alloc=alloc, root=root, stack=STACK,
            blink_mt=blink_mt, kept_off=kept_off,
        )
        files["Blink"] = _append_arm(files["Blink"], prologue)
    mem = Mem(bytes(image), LIMIT)
    root_now, alloc_now = _load(mem, root, alloc, "Oberon", files)
    if mem.get(root_now + NUM) != 5:
        raise SystemExit(f"Oberon is module {mem.get(root_now + NUM)}")
    root_now, alloc_now = _load(mem, root_now, alloc_now, "Blink", files)
    if mem.get(root_now + NUM) != 10 or _name_at(mem, root_now) != "Blink":
        raise SystemExit(f"root is {_name_at(mem, root_now)} num {mem.get(root_now + NUM)}")
    if alloc_now > LIMIT:
        raise SystemExit(f"allocation ends at {alloc_now:#x}, limit is {LIMIT:#x}")
    fonts = _find(mem, root_now, "Fonts")
    if mem.get(fonts + NUM) != 6:
        raise SystemExit(f"Fonts is module {mem.get(fonts + NUM)}")
    texts = _find(mem, root_now, "Texts")
    if mem.get(texts + NUM) != 7:
        raise SystemExit(f"Texts is module {mem.get(texts + NUM)}")
    display = _find(mem, root_now, "Display")
    if mem.get(display + NUM) != 8:
        raise SystemExit(f"Display is module {mem.get(display + NUM)}")
    ammt = _find(mem, root_now, "AMemoryMappedToggle")
    if mem.get(ammt + NUM) != 9:
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
    tiny = _font_bytes("Tiny4x6.Fnt", bad_font and not uart_disk)
    face = _font_bytes("Oberon10.Scn.Fnt", bad_font and uart_disk)
    order = (
        (b"AMemoryMappedToggle.rsc", files["AMemoryMappedToggle"]),
        (b"Blink.Rate", None),
        (b"Blink.rsc", files["Blink"]),
        (b"Display.rsc", files["Display"]),
        (b"Fonts.rsc", files["Fonts"]),
        (b"Oberon.rsc", files["Oberon"]),
        (b"Oberon10.Scn.Fnt", face),
        (b"Texts.rsc", files["Texts"]),
        (b"Tiny4x6.Fnt", tiny),
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
        room = SECTOR - HEADER_SIZE
        extra = 0 if len(raw) <= room else (len(raw) - room + SECTOR - 1) // SECTOR
        conts = [(which + 2 + i) * 29 for i in range(extra)]
        built = _file_pages(
            filename, raw, sector,
            conts[0] if conts else None,
            conts[1] if len(conts) > 1 else None,
            conts[2:] if len(conts) > 2 else None,
        )
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
    hyper_bytes = _hyper_bytes()
    if DISK_DDR + len(payload) >= hyper_bytes:
        raise SystemExit(
            f"UART disk ends at {DISK_DDR + len(payload):#x}, "
            f"the HyperRAM stand-in ends at {hyper_bytes:#x}"
        )
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
    published = SHORT_MEMLIM if short_heap else MEMLIM
    rom_code = _compile_boot(env, 1 if uart_disk else 0, published)
    other = _compile_boot(env, 0 if uart_disk else 1, published)
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
