#!/usr/bin/env python3
"""Directory sector 29 and the two file headers it names.

Sector numbers are multiples of 29, which is what Kernel.GetSector
divides by. The SPI model stores these bytes as little-endian words:
a fast read returns the next four bytes, low byte first, which is the
word ReadSD stores. There is no card. The window is the model.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from build_files_imem import ammt_rsc, blink5_rsc  # noqa: E402

DIR_MARK = 0x9B1EA38D
HEADER_MARK = 0x9BA71D86
HEADER_SIZE = 352
SECTOR = 1024
DIR_ROOT = 29
AMMT_SEC = 58
BLINK_SEC = 87
# Blink5's second page, when the object file does not fit the header.
# SpiSector's page index is the sector number divided by 29. Five
# pages cover the directory, the two modules, Blink5's continuation,
# and Blink.Rate.
BLINK_CONT = 116
RATE_SEC = 145
RATE_NAME = b"Blink.Rate"
FS_OFFSET = 0x80000
# Word ROM. Sector k/29 lives at word (k/29 - 1) << 8.
ROM_WORDS = 1280

AMMT_NAME = b"AMemoryMappedToggle"
BLINK_NAME = b"Blink5"


def _name32(text: bytes) -> bytes:
    raw = text + b"\0"
    if len(raw) > 32:
        raise SystemExit(f"name {text!r} does not fit a directory entry")
    return raw + bytes(32 - len(raw))


def _header(name: bytes, payload: bytes, sector: int) -> bytes:
    pages = _file_pages(name, payload, sector, None)
    if len(pages) != 1:
        raise SystemExit(f"{name!r} needs a continuation sector")
    return pages[0][1]


def _file_pages(name: bytes, payload: bytes, sector: int, cont: int | None) -> list[tuple[int, bytes]]:
    """Header page, and a second page when the object file passes byte 672.

    File length includes the 352-byte header. aleng * 1024 + bleng is that
    length. sec[0] is the header. sec[1] is the continuation. A file this
    short has no index page.
    """
    if sector % 29:
        raise SystemExit(f"sector {sector} is not a multiple of 29")
    room = SECTOR - HEADER_SIZE
    if len(payload) <= room:
        buf = bytearray(SECTOR)
        struct.pack_into("<I", buf, 0, HEADER_MARK)
        buf[4:36] = _name32(name)
        struct.pack_into("<III", buf, 36, 0, HEADER_SIZE + len(payload), 0)
        struct.pack_into("<I", buf, 96, sector)
        buf[HEADER_SIZE : HEADER_SIZE + len(payload)] = payload
        return [(sector, bytes(buf))]
    if cont is None:
        raise SystemExit(f"{name!r} is {len(payload)} bytes and has no continuation sector")
    if cont % 29:
        raise SystemExit(f"continuation sector {cont} is not a multiple of 29")
    rest = payload[room:]
    if len(rest) > SECTOR:
        raise SystemExit(f"{name!r} needs more than one continuation sector")
    total = HEADER_SIZE + len(payload)
    aleng, bleng = divmod(total, SECTOR)
    if bleng == 0:
        aleng -= 1
        bleng = SECTOR
    buf = bytearray(SECTOR)
    struct.pack_into("<I", buf, 0, HEADER_MARK)
    buf[4:36] = _name32(name)
    struct.pack_into("<III", buf, 36, aleng, bleng, 0)
    struct.pack_into("<I", buf, 96, sector)
    struct.pack_into("<I", buf, 100, cont)
    buf[HEADER_SIZE:] = payload[:room]
    page = bytearray(SECTOR)
    page[: len(rest)] = rest
    return [(sector, bytes(buf)), (cont, bytes(page))]


def rate_page(delay_ms: int, sector: int) -> bytes:
    """One sector. The file is the delay and its negation.

    Files.ReadInt returns the first word. The two words sum to 0, so
    the disk checksum does not depend on the delay.
    """
    if delay_ms % 2 or not 1 <= delay_ms <= 0x7FFF:
        raise SystemExit(f"rate {delay_ms} must be a positive even millisecond count")
    payload = struct.pack("<ii", delay_ms, -delay_ms)
    built = _file_pages(RATE_NAME, payload, sector, None)
    if len(built) != 1:
        raise SystemExit("Blink.Rate spilled past its header sector")
    page = built[0][1]
    got, neg = struct.unpack_from("<ii", page, HEADER_SIZE)
    if got != delay_ms or (got + neg) & 0xFFFFFFFF != 0:
        raise SystemExit(f"rate pair {got} {neg} is not checksum-neutral")
    return page


def _dir_page(entries: list[tuple[bytes, int]]) -> bytes:
    buf = bytearray(SECTOR)
    struct.pack_into("<III", buf, 0, DIR_MARK, len(entries), 0)
    off = 64
    for name, adr in entries:
        if adr % 29:
            raise SystemExit(f"entry {name!r} sector {adr} is not a multiple of 29")
        buf[off : off + 32] = _name32(name)
        struct.pack_into("<II", buf, off + 32, adr, 0)
        off += 40
    return bytes(buf)


def pages() -> dict[int, bytes]:
    """Oberon sector number to 1024 bytes. Names are in Oberon order."""
    ammt = ammt_rsc()
    blink = blink5_rsc()
    built = {
        DIR_ROOT: _dir_page([(AMMT_NAME, AMMT_SEC), (BLINK_NAME, BLINK_SEC)]),
        AMMT_SEC: _header(AMMT_NAME, ammt, AMMT_SEC),
        BLINK_SEC: _header(BLINK_NAME, blink, BLINK_SEC),
    }
    for sec, page in built.items():
        if len(page) != SECTOR:
            raise SystemExit(f"sector {sec} is {len(page)} bytes")
    return built


def rom_words(table: dict[int, bytes] | None = None) -> list[int]:
    table = pages() if table is None else table
    words = [0] * ROM_WORDS
    for sec, page in table.items():
        index = sec // 29
        if index < 1 or index > 5:
            raise SystemExit(f"sector {sec} is outside the five-page image")
        base = (index - 1) * 256
        for i in range(0, SECTOR, 4):
            words[base + i // 4] = int.from_bytes(page[i : i + 4], "little")
    return words


def write_hex(path: str, words: list[int] | None = None) -> None:
    words = rom_words() if words is None else words
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as out:
        for word in words:
            out.write(f"{word:08x}\n")


def word_at(words: list[int], sec: int, byte_off: int) -> int:
    index = sec // 29
    base = (index - 1) * 256
    return words[base + byte_off // 4]


class Card:
    """Byte/word SPI responder for SDShift and ReadSD.

    phase: 0 idle, 1 command, 2 CMD58 response, 3 CMD17 token,
    4 data words, 5 checksum bytes. A data write clocks. A control
    write only latches select and the fast bit. Ready is the caller's
    problem; this object completes the transfer on the write.
    """

    def __init__(self, words: list[int]):
        self.words = words
        self.ctrl = 0
        self.rx = 0xFF
        self.phase = 0
        self.cmd = 0
        self.arg = 0
        self.nargs = 0
        self.idx = 0
        self.block = 0

    def write_ctrl(self, value: int) -> None:
        self.ctrl = value & 0xF

    def write_data(self, value: int) -> None:
        if self.phase == 4 and (self.ctrl & 4):
            self.rx = self._word()
        else:
            self.rx = self._byte(value & 0xFF)

    def _word(self) -> int:
        rel = self.block - FS_OFFSET
        index = rel >> 1
        half = rel & 1
        if 1 <= index <= 5:
            addr = (index - 1) * 256 + half * 128 + self.idx
            got = self.words[addr]
        else:
            got = 0
        self.idx += 1
        if self.idx == 128:
            self.phase = 5
            self.idx = 0
        return got

    def _byte(self, tx: int) -> int:
        phase = self.phase
        if phase == 0:
            if 0x40 <= tx <= 0x7F:
                self.cmd = tx & 0x3F
                self.arg = 0
                self.nargs = 0
                self.phase = 1
            return 0xFF
        if phase == 1:
            if self.nargs < 4:
                self.arg = ((self.arg << 8) | tx) & 0xFFFFFFFF
                self.nargs += 1
                return 0xFF
            self.block = self.arg
            self.idx = 0
            if self.cmd == 58:
                self.phase = 2
            elif self.cmd == 17:
                self.phase = 3
            else:
                self.phase = 0
            return 0xFF
        if phase == 2:
            seq = (0x00, 0xC0, 0xFF, 0x80, 0x00)
            got = seq[self.idx]
            self.idx += 1
            if self.idx == len(seq):
                self.phase = 0
                self.idx = 0
            return got
        if phase == 3:
            if self.idx == 0:
                self.idx = 1
                return 0x00
            self.phase = 4
            self.idx = 0
            return 0xFE
        if phase == 5:
            self.idx += 1
            if self.idx == 2:
                self.phase = 0
                self.idx = 0
            return 0xFF
        return 0xFF


def _xfer(card: Card, ctrl: int, data: int) -> int:
    card.write_ctrl(ctrl)
    card.write_data(data)
    return card.rx & 0xFFFFFFFF


def read_sd(card: Card, block: int) -> bytes:
    """The bytes Kernel.ReadSD stores for one 512-byte half."""
    def idle() -> int:
        return _xfer(card, 0, 0xFFFFFFFF)

    def spi(n: int) -> int:
        return _xfer(card, 1, n & 0xFFFFFFFF)

    def spicmd(cmd: int, arg: int) -> int:
        while idle() != 0xFF:
            pass
        while spi(0xFF) != 0xFF:
            pass
        spi((cmd % 64) + 64)
        for shift in (24, 16, 8, 0):
            spi((arg >> shift) & 0xFF)
        spi(0xFF)
        data = 0xFF
        for _ in range(32):
            data = spi(0xFF)
            if data < 0x80:
                break
        return data

    # SDShift. CMD58 argument is 0. An SDHC OCR keeps the block number.
    status = spicmd(58, 0)
    ocr0 = spi(0xFF)
    if status != 0 or (ocr0 & 0x40) == 0:
        block *= 512
    spi(0xFF)
    spi(0xFF)
    idle()
    data = spicmd(17, block)
    if data != 0:
        raise SystemExit(f"CMD17 status {data:#x}")
    while spi(0xFF) != 0xFE:
        pass
    card.write_ctrl(5)
    out = bytearray()
    for _ in range(128):
        word = card.write_data(0xFFFFFFFF) or card.rx
        # write_data already stored rx. ctrl stays 5.
        out += (card.rx & 0xFFFFFFFF).to_bytes(4, "little")
    spi(0xFF)
    spi(0xFF)
    idle()
    if len(out) != 512:
        raise SystemExit(f"half sector is {len(out)} bytes")
    return bytes(out)


def get_sector(card: Card, sec: int) -> bytes:
    q, r = divmod(sec, 29)
    if r:
        raise SystemExit(f"sector {sec} leaves a remainder")
    block = q * 2 + FS_OFFSET
    return read_sd(card, block) + read_sd(card, block + 1)


def check_pages() -> None:
    table = pages()
    words = rom_words(table)
    page = table[DIR_ROOT]
    mark, count, p0 = struct.unpack_from("<III", page, 0)
    if (mark, count, p0) != (DIR_MARK, 2, 0):
        raise SystemExit(f"directory header {(mark, count, p0)}")
    for i, (name, adr) in enumerate(((AMMT_NAME, AMMT_SEC), (BLINK_NAME, BLINK_SEC))):
        off = 64 + i * 40
        got = page[off : off + 32].split(b"\0", 1)[0]
        sec, desc = struct.unpack_from("<II", page, off + 32)
        if got != name or sec != adr or desc != 0:
            raise SystemExit(f"entry {i} {got!r} {sec:#x} {desc:#x}")
    for sec, name in ((AMMT_SEC, AMMT_NAME), (BLINK_SEC, BLINK_NAME)):
        head = table[sec]
        hmark = struct.unpack_from("<I", head, 0)[0]
        hname = head[4:36].split(b"\0", 1)[0]
        if hmark != HEADER_MARK or hname != name:
            raise SystemExit(f"header {sec} {hmark:#x} {hname!r}")
        payload = ammt_rsc() if sec == AMMT_SEC else blink5_rsc()
        if head[HEADER_SIZE : HEADER_SIZE + len(payload)] != payload:
            raise SystemExit(f"sector {sec} payload is not the .rsc")
        if word_at(words, sec, 0) != HEADER_MARK:
            raise SystemExit(f"ROM lost the mark of sector {sec}")
    card = Card(words)
    got = get_sector(card, DIR_ROOT)
    if got != table[DIR_ROOT]:
        raise SystemExit("GetSector(29) did not return the directory page")
    for sec in (AMMT_SEC, BLINK_SEC):
        # A fresh card, so the command parser starts idle.
        got = get_sector(Card(words), sec)
        if got != table[sec]:
            raise SystemExit(f"GetSector({sec}) did not return the header")
    print(
        "[ok] sector pages",
        f"dir {DIR_ROOT}",
        f"ammt {AMMT_SEC}",
        f"blink {BLINK_SEC}",
        f"rom {sum(1 for w in words if w)} nonzero words",
    )


if __name__ == "__main__":
    check_pages()
