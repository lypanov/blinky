#!/usr/bin/env python3
"""GetSector, Search, and ReadString for the modules image.

The procedures are the Kernel / FileDir / Files sequences, in the free
words after Modules.Check. Directory sector 29 replaces the table at
0x600. The file bytes come back through the SPI window (-48 data,
-44 control) into a buffer, and the existing rider walks those bytes.
R5, R7, R8, R2, R9, R10, and R12 stay as the files block left them.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from build_hyperram_imem import (  # noqa: E402
    Asm,
    cond_branch,
    f0,
    f1,
    ldb,
    ldw,
    load_const,
    mhi,
    mov_imm,
    stw,
)
from build_files_imem import ammt_rsc, blink5_rsc  # noqa: E402
from sector_image import (  # noqa: E402
    AMMT_NAME,
    BLINK_NAME,
    DIR_MARK,
    DIR_ROOT,
    HEADER_MARK,
    HEADER_SIZE,
    Card,
    pages,
    write_hex,
)

BASE = 0x9E8
DIR_BUF = 0x3000
FILE_BUF = 0x3400
FILE_DATA = FILE_BUF + HEADER_SIZE
NAME_AMMT = 0x2C00
NAME_BLINK = 0x2C20
# Link words and the search locals. Below the deposited names.
LINK_CMD = 0x2BD0
LINK_RD = 0x2BD4
LINK_GET = 0x2BD8
LINK_OPEN = 0x2BDC
NAME_SLOT = 0x2BE0
DADR = 0x2BE4
FOUND = 0x2BE8
I_SLOT = 0x2BEC
TMP_L = 0x2BF0
TMP_R = 0x2BF4
BLOCK_SAVE = 0x2BF8
STATUS = 0x2BFC
BT_R15 = 0xC700000F
MOV_H_R4 = 0x24000000
BNE = 9
BEQ = 1
BPL = 8
MI = 0
ALWAYS = 7
HEX_PATH = os.path.join(
    os.path.dirname(__file__), "visualizer", "imem", "sector.hex"
)
# The files block may write these. The sector routines may not.
KEPT = {2, 5, 7, 8, 9, 10, 12, 13, 14}


def _stw(ra: int, rb: int, off: int) -> int:
    if not -0x80000 <= off < 0x80000:
        raise ValueError(off)
    return 0xA0000000 | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | (off & 0xFFFFF)


def _ldw(ra: int, rb: int, off: int) -> int:
    if not -0x80000 <= off < 0x80000:
        raise ValueError(off)
    return 0x80000000 | ((ra & 0xF) << 24) | ((rb & 0xF) << 20) | (off & 0xFFFFF)


def _bl(a: Asm, name: str) -> None:
    def fn(pc: int, name: str = name) -> int:
        off = (a.labels[name] - (pc + 4)) // 4
        if not -0x800000 <= off < 0x800000:
            raise ValueError(f"BL {name} from {pc:#x}")
        return 0xF7000000 | (off & 0xFFFFFF)

    a.at(fn)


def _babs(a: Asm, target: int, cond: int = ALWAYS) -> None:
    def fn(pc: int, target: int = target, cond: int = cond) -> int:
        return cond_branch(pc, target, cond)

    a.at(fn)


def _store(a: Asm, addr: int, reg: int) -> None:
    # The pointer is R11. Saving R11 itself has to copy it first.
    src = reg
    if reg == 11:
        a.word(f0(0, 0, 0, 11))
        src = 0
    for word in load_const(11, addr):
        a.word(word)
    a.word(stw(src, 11, 0))


def _load(a: Asm, addr: int, rd: int) -> None:
    for word in load_const(11, addr):
        a.word(word)
    a.word(ldw(rd, 11, 0))


def _ret(a: Asm, addr: int) -> None:
    _load(a, addr, 15)
    a.word(BT_R15)


def _words_of(text: bytes) -> list[int]:
    raw = text + b"\0"
    raw = raw + bytes((-len(raw)) % 4)
    return list(struct.unpack("<" + "I" * (len(raw) // 4), raw))


def _names(a: Asm) -> None:
    """Zero both 32-byte names, then store the nonzero words."""
    a.label("names")
    a.word(mov_imm(3, NAME_AMMT))
    a.word(mov_imm(4, 16))
    a.word(mov_imm(0, 0))
    a.label("nz")
    a.word(stw(0, 3, 0))
    a.word(f1(8, 3, 3, 4))
    a.word(f1(9, 4, 4, 1))
    a.branch("nz", BNE)
    for addr, text in ((NAME_AMMT, AMMT_NAME), (NAME_BLINK, BLINK_NAME)):
        for i, word in enumerate(_words_of(text)):
            if word == 0:
                continue
            for w in load_const(0, word):
                a.word(w)
            a.word(mov_imm(3, addr + i * 4))
            a.word(stw(0, 3, 0))
    a.word(BT_R15)


def _spi(a: Asm) -> None:
    # R0 is the control word or the transmitted word. R1 comes back.
    a.label("spi_ctrl")
    a.word(mov_imm(11, 0))
    a.word(_stw(0, 11, -44))
    a.word(BT_R15)
    a.label("spi_byte")
    a.word(mov_imm(11, 0))
    a.word(_stw(0, 11, -48))
    a.label("spi_poll")
    a.word(_ldw(1, 11, -44))
    a.word(f1(3, 1, 1, 1))
    a.branch("spi_poll", BPL)
    a.word(_ldw(1, 11, -48))
    a.word(BT_R15)


def _spicmd(a: Asm) -> None:
    """R4 = command byte (0x40|cmd), R6 = argument. R6 is kept."""
    a.label("spicmd")
    _store(a, LINK_CMD, 15)
    a.label("flush_idle")
    a.word(mov_imm(0, 0))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(f1(9, 0, 1, 0xFF))
    a.branch("flush_idle", BNE)
    a.label("flush_sel")
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(f1(9, 0, 1, 0xFF))
    a.branch("flush_sel", BNE)
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(f0(0, 0, 0, 4))
    _bl(a, "spi_byte")
    # R4 is free once the command byte has gone out. spi_byte returns in R1.
    a.word(mov_imm(4, 24))
    a.label("cmd_arg")
    a.word(f0(3, 0, 6, 4))
    _bl(a, "spi_byte")
    a.word(f1(9, 4, 4, 8))
    a.branch("cmd_arg", BPL)
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(mov_imm(4, 32))
    a.label("cmd_resp")
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(f1(4, 0, 1, 0x80))
    a.branch("cmd_done", BEQ)
    a.word(f1(9, 4, 4, 1))
    a.branch("cmd_resp", BNE)
    a.label("cmd_done")
    _ret(a, LINK_CMD)


def _readsd(a: Asm) -> None:
    """R6 = block, R3 = destination. R3 advances 512. R6 stays the block."""
    a.label("readsd")
    _store(a, LINK_RD, 15)
    _store(a, BLOCK_SAVE, 6)
    a.word(mov_imm(6, 0))
    a.word(mov_imm(4, 0x7A))
    _bl(a, "spicmd")
    _store(a, STATUS, 1)
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    _load(a, STATUS, 4)
    a.word(f1(9, 0, 4, 0))
    a.branch("shift_mul", BNE)
    a.word(f1(3, 0, 1, 7))
    a.branch("shift_ok", MI)
    a.label("shift_mul")
    _load(a, BLOCK_SAVE, 6)
    a.word(f1(1, 6, 6, 9))
    _store(a, BLOCK_SAVE, 6)
    a.label("shift_ok")
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(mov_imm(0, 0))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    _load(a, BLOCK_SAVE, 6)
    a.word(mov_imm(4, 0x51))
    _bl(a, "spicmd")
    a.word(f1(9, 0, 1, 0))
    a.branch("rd_ok", BEQ)
    a.branch("fail", ALWAYS)
    a.label("rd_ok")
    a.label("token")
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(f1(9, 0, 1, 0xFE))
    a.branch("token", BNE)
    a.word(mov_imm(0, 5))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(4, 128))
    a.label("fast")
    for word in load_const(0, 0xFFFFFFFF):
        a.word(word)
    _bl(a, "spi_byte")
    a.word(stw(1, 3, 0))
    a.word(f1(8, 3, 3, 4))
    a.word(f1(9, 4, 4, 1))
    a.branch("fast", BNE)
    a.word(mov_imm(0, 1))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    a.word(mov_imm(0, 0))
    _bl(a, "spi_ctrl")
    a.word(mov_imm(0, 0xFF))
    _bl(a, "spi_byte")
    _ret(a, LINK_RD)


def _get_sector(a: Asm) -> None:
    """R1 = Oberon sector, R3 = destination. DIV 29, then two halves."""
    a.label("get_sector")
    _store(a, LINK_GET, 15)
    a.word(f0(0, 0, 0, 1))
    a.word(f1(11, 0, 0, 29))
    a.word(MOV_H_R4)
    a.word(f0(0, 6, 0, 0))
    a.word(f1(9, 0, 4, 0))
    a.branch("gs_ok", BEQ)
    a.branch("fail", ALWAYS)
    a.label("gs_ok")
    a.word(f1(1, 6, 6, 1))
    a.word(mhi(0, 0x8))
    a.word(f0(8, 6, 6, 0))
    _bl(a, "readsd")
    a.word(f1(8, 6, 6, 1))
    _bl(a, "readsd")
    _ret(a, LINK_GET)


def _entry(a: Asm) -> None:
    """R0 = entry index. R3 comes back as the name address. Keeps R6 and R11."""
    a.label("entry")
    a.word(f0(0, 1, 0, 0))
    a.word(f1(1, 3, 1, 5))
    a.word(f1(1, 0, 1, 3))
    a.word(f0(8, 3, 3, 0))
    a.word(f1(8, 3, 3, DIR_BUF + 64))
    a.word(BT_R15)


def _cmp(a: Asm) -> None:
    """R4 = query, R3 = entry name. R0 is the first difference, or 0.

    R6 and R11 are the search bounds. They come back unchanged.
    """
    a.label("cmp")
    _store(a, TMP_L, 11)
    _store(a, TMP_R, 6)
    a.word(mov_imm(11, 32))
    a.label("cmp_loop")
    a.word(ldb(0, 4, 0))
    a.word(ldb(1, 3, 0))
    a.word(f0(9, 0, 0, 1))
    a.branch("cmp_diff", BNE)
    a.word(f1(8, 4, 4, 1))
    a.word(f1(8, 3, 3, 1))
    a.word(f1(9, 11, 11, 1))
    a.branch("cmp_loop", BNE)
    a.word(mov_imm(0, 0))
    a.branch("cmp_ret", ALWAYS)
    a.label("cmp_diff")
    a.label("cmp_ret")
    # R11 is L. Load R first; the last load is the one that leaves R11.
    # The loads write N and Z, so subtract zero and let the difference decide.
    _load(a, TMP_R, 6)
    _load(a, TMP_L, 11)
    a.word(f1(9, 0, 0, 0))
    a.word(BT_R15)


def _open(a: Asm, hold: int, root: int) -> None:
    a.label("open_ammt")
    a.word(mov_imm(4, NAME_AMMT))
    a.branch("open", ALWAYS)
    a.label("open_blink")
    a.word(mov_imm(4, NAME_BLINK))
    a.label("open")
    _store(a, LINK_OPEN, 15)
    _store(a, NAME_SLOT, 4)
    a.word(mov_imm(0, root))
    _store(a, DADR, 0)
    a.word(mov_imm(0, 0))
    _store(a, FOUND, 0)
    a.label("search")
    _load(a, DADR, 1)
    a.word(f1(9, 0, 1, 0))
    _babs(a, hold, BEQ)
    a.word(mov_imm(3, DIR_BUF))
    _bl(a, "get_sector")
    a.word(mov_imm(11, DIR_BUF))
    a.word(ldw(0, 11, 0))
    for word in load_const(1, DIR_MARK):
        a.word(word)
    a.word(f0(9, 0, 0, 1))
    a.branch("fail", BNE)
    a.word(mov_imm(11, DIR_BUF))
    a.word(ldw(6, 11, 4))
    a.word(mov_imm(11, 0))
    a.label("bin")
    a.word(f0(9, 0, 11, 6))
    a.branch("bin_done", BPL)
    a.word(f0(8, 0, 11, 6))
    a.word(f1(2, 0, 0, 1))
    # R11 is L. R0 is i. Point the stores with R1.
    a.word(mov_imm(1, I_SLOT))
    a.word(stw(0, 1, 0))
    _bl(a, "entry")
    a.word(mov_imm(1, NAME_SLOT))
    a.word(ldw(4, 1, 0))
    _bl(a, "cmp")
    a.branch("take_le", MI)
    a.branch("take_le", BEQ)
    _load(a, I_SLOT, 0)
    a.word(f1(8, 11, 0, 1))
    a.branch("bin", ALWAYS)
    a.label("take_le")
    # R11 is L. Point with R0 so the load of i does not replace it.
    a.word(mov_imm(0, I_SLOT))
    a.word(ldw(6, 0, 0))
    a.branch("bin", ALWAYS)
    a.label("bin_done")
    a.word(mov_imm(11, DIR_BUF))
    a.word(ldw(0, 11, 4))
    a.word(f0(9, 0, 6, 0))
    a.branch("not_here", BPL)
    a.word(f0(0, 0, 0, 6))
    _bl(a, "entry")
    _store(a, I_SLOT, 3)
    _load(a, NAME_SLOT, 4)
    _bl(a, "cmp")
    a.branch("not_here", BNE)
    _load(a, I_SLOT, 3)
    a.word(ldw(0, 3, 32))
    _store(a, FOUND, 0)
    a.branch("found", ALWAYS)
    a.label("not_here")
    a.word(f1(9, 0, 6, 0))
    a.branch("use_p0", BEQ)
    a.word(f1(9, 0, 6, 1))
    _bl(a, "entry")
    a.word(ldw(0, 3, 36))
    a.branch("have_dadr", ALWAYS)
    a.label("use_p0")
    a.word(mov_imm(11, DIR_BUF))
    a.word(ldw(0, 11, 8))
    a.label("have_dadr")
    _store(a, DADR, 0)
    a.word(f1(9, 1, 0, 0))
    a.branch("search", BNE)
    _babs(a, hold, ALWAYS)
    a.label("found")
    _load(a, FOUND, 1)
    a.word(mov_imm(3, FILE_BUF))
    _bl(a, "get_sector")
    a.word(mov_imm(11, FILE_BUF))
    a.word(ldw(0, 11, 0))
    for word in load_const(1, HEADER_MARK):
        a.word(word)
    a.word(f0(9, 0, 0, 1))
    a.branch("fail", BNE)
    _load(a, NAME_SLOT, 4)
    a.word(mov_imm(3, FILE_DATA))
    a.label("rstr")
    a.word(ldb(0, 3, 0))
    a.word(ldb(1, 4, 0))
    a.word(f0(9, 0, 0, 1))
    _babs(a, hold, BNE)
    a.word(ldb(0, 4, 0))
    a.word(f1(8, 3, 3, 1))
    a.word(f1(8, 4, 4, 1))
    a.word(f1(9, 0, 0, 0))
    a.branch("rstr", BNE)
    a.word(mov_imm(3, FILE_DATA))
    _ret(a, LINK_OPEN)


def _check_kept(prog: list[int], base: int) -> None:
    for i, word in enumerate(prog):
        top = word >> 28
        rd = (word >> 24) & 0xF
        writes = top in (0, 1, 2, 4, 5, 6, 8, 9)
        if writes and rd in KEPT:
            raise SystemExit(f"sector word at {base + i * 4:#x} writes R{rd}")


def assemble_sector(hold: int, root: int = DIR_ROOT) -> tuple[list[int], dict[str, int]]:
    a = Asm()
    _names(a)
    _open(a, hold, root)
    _get_sector(a)
    _readsd(a)
    _spicmd(a)
    _spi(a)
    _entry(a)
    _cmp(a)
    a.label("fail")
    # Trap's load reads data memory, not the pROM. Plant the same word
    # it is about to execute, the way an ASSERT does. Trap 7 holds.
    # The good path does not fetch this sequence.
    a.at(lambda pc: mov_imm(1, a.labels["fail_bl"]))
    for word in load_const(0, 0xD700007C):
        a.word(word)
    a.word(stw(0, 1, 0))
    a.label("fail_bl")
    a.word(0xD700007C)
    prog = a.encode(BASE)
    end = BASE + len(prog) * 4
    if end > 0x1000:
        raise SystemExit(f"sector code ends at {end:#x}, page 0x10 is the loop")
    _check_kept(prog, BASE)
    if a.labels["names"] != BASE:
        raise SystemExit("names is not the sector entry")
    return prog, dict(a.labels)


def _run(prog: list[int], labels: dict[str, int], hold: int, entry: str,
         regs: list[int], mem: bytearray, card: Card, limit: int = 400000) -> int:
    """One call. Returns the PC it stopped on. SPI completes in the write."""
    imem = {BASE + i * 4: word for i, word in enumerate(prog)}
    flag = {"n": 0, "z": 0}
    hreg = 0
    spi_rx = 0xFF
    pc = labels[entry]
    ret = regs[15]
    for _step in range(limit):
        if pc == hold or pc == ret or pc not in imem:
            return pc
        word = imem[pc]
        if word == 0xD700007C:
            return pc
        top = word >> 28
        rd = (word >> 24) & 0xF
        rb = (word >> 20) & 0xF
        op = (word >> 16) & 0xF
        rc = word & 0xF
        imm = word & 0xFFFF
        if top in (0xC, 0xD, 0xE, 0xF):
            cond = (word >> 24) & 0xF
            cc = cond & 7
            cc_true = (flag["n"], flag["z"], 0, 0, 0, 0, 0, 1)[cc]
            take = ((cond >> 3) & 1) ^ cc_true
            link = top & 1
            nxt = pc + 4
            if take and link:
                regs[15] = nxt
            if take and top >= 0xE:
                off = word & 0xFFFFFF
                if off & 0x800000:
                    off -= 0x1000000
                pc = nxt + off * 4
            elif take:
                pc = regs[rc] & ~3
            else:
                pc = nxt
            continue
        if top in (8, 9, 0xA, 0xB):
            off = word & 0xFFFFF
            if off & 0x80000:
                off -= 0x100000
            addr = (regs[rb] + off) & 0xFFFFFFFF
            if top in (8, 9):
                if addr == 0xFFFFFFD0:
                    value = spi_rx & 0xFFFFFFFF
                elif addr == 0xFFFFFFD4:
                    value = 1
                elif top == 8:
                    value = int.from_bytes(mem[addr : addr + 4], "little")
                else:
                    value = mem[addr]
                regs[rd] = value
                flag["n"] = (value >> 31) & 1
                flag["z"] = int(value == 0)
            elif addr == 0xFFFFFFD0:
                card.write_data(regs[rd])
                spi_rx = card.rx & 0xFFFFFFFF
            elif addr == 0xFFFFFFD4:
                card.write_ctrl(regs[rd])
            else:
                raw = regs[rd] & (0xFF if top == 0xB else 0xFFFFFFFF)
                width = 1 if top == 0xB else 4
                mem[addr : addr + width] = raw.to_bytes(width, "little")
            pc += 4
            continue
        if top == 2:
            regs[rd] = hreg & 0xFFFFFFFF
            flag["n"] = (hreg >> 31) & 1
            flag["z"] = int(hreg == 0)
            pc += 4
            continue
        operand = regs[rc] if top == 0 else imm
        if top == 6 and op == 0:
            operand = (imm << 16) & 0xFFFFFFFF
            op = 0
            bval = 0
        else:
            bval = regs[rb] & 0xFFFFFFFF
        if op == 11:
            if operand == 0:
                raise SystemExit(f"DIV by 0 at {pc:#x}")
            q, hreg = divmod(bval, operand)
            regs[rd] = q
            flag["n"] = 0
            flag["z"] = int(q == 0)
            pc += 4
            continue
        if op == 1:
            result = (bval << (operand & 31)) & 0xFFFFFFFF
        elif op == 2:
            signed = bval - 0x100000000 if bval & 0x80000000 else bval
            result = (signed >> (operand & 31)) & 0xFFFFFFFF
        elif op == 3:
            sh = operand & 31
            result = bval if sh == 0 else ((bval >> sh) | (bval << (32 - sh))) & 0xFFFFFFFF
        elif op == 4:
            result = bval & operand
        elif op == 6:
            result = bval | operand
        elif op == 8:
            result = (bval + operand) & 0xFFFFFFFF
        elif op == 9:
            result = (bval - operand) & 0xFFFFFFFF
        elif op == 0:
            result = operand & 0xFFFFFFFF
        else:
            raise SystemExit(f"op {op} at {pc:#x} word {word:#x}")
        regs[rd] = result
        flag["n"] = (result >> 31) & 1
        flag["z"] = int(result == 0)
        pc += 4
    raise SystemExit(f"{entry} did not return in {limit} steps, pc {pc:#x}")


def rehearse(prog: list[int], labels: dict[str, int], hold: int) -> None:
    table = pages()
    card = Card([0] * 1024)
    # The ROM the card reads is the same hex the hardware loads.
    from sector_image import rom_words
    card.words = rom_words(table)
    mem = bytearray(0x4000)
    regs = [0] * 16
    kept = {2: 0xA5A5A5A2, 5: 0xA5A5A5A5, 7: 0xA5A5A5A7, 8: 0xA5A5A5A8,
            9: 0xA5A5A5A9, 10: 0xA5A5A5AA, 12: 0x20, 14: 0xA000}
    regs[15] = 0x4
    for reg, val in kept.items():
        regs[reg] = val
    stopped = _run(prog, labels, hold, "names", regs, mem, card)
    if stopped != 0x4:
        raise SystemExit(f"names stopped at {stopped:#x}")
    for entry, sec, blob in (
        ("open_ammt", 58, ammt_rsc()),
        ("open_blink", 87, blink5_rsc()),
    ):
        regs[15] = 0x4
        stopped = _run(prog, labels, hold, entry, regs, mem, card)
        if stopped != 0x4:
            raise SystemExit(f"{entry} stopped at {stopped:#x}")
        if regs[3] != FILE_DATA:
            raise SystemExit(f"{entry} left R3 {regs[3]:#x}")
        got = bytes(mem[FILE_DATA : FILE_DATA + len(blob)])
        if got != blob:
            raise SystemExit(f"{entry} file bytes mismatch at {FILE_DATA:#x}")
        if int.from_bytes(mem[FILE_BUF : FILE_BUF + 4], "little") != HEADER_MARK:
            raise SystemExit(f"{entry} header mark missing")
        if sec == 58 and int.from_bytes(mem[DIR_BUF : DIR_BUF + 4], "little") != DIR_MARK:
            raise SystemExit("directory mark missing")
        for reg, val in kept.items():
            if regs[reg] != val:
                raise SystemExit(f"{entry} wrote R{reg}")
    # A sector that is not a multiple of 29 takes the trap, not the LED loop.
    regs[1] = 30
    regs[3] = DIR_BUF
    regs[15] = 0x4
    stopped = _run(prog, labels, hold, "get_sector", regs, mem, card)
    if stopped != labels["fail_bl"]:
        raise SystemExit(f"remainder stopped at {stopped:#x}, not the trap")
    print("[ok] sector rehearsal", "ammt", len(ammt_rsc()), "blink", len(blink5_rsc()))


def main() -> int:
    prog, labels = assemble_sector(0x1D8C)
    print(f"[ok] sector code {len(prog)} words {BASE:#x}..{BASE + len(prog) * 4:#x}")
    for name in ("names", "open_ammt", "open_blink", "open", "get_sector", "fail"):
        print(f"  {name} {labels[name]:#x}")
    rehearse(prog, labels, 0x1D8C)
    write_hex(HEX_PATH)
    print(f"[ok] {HEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
