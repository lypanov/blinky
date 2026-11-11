#!/usr/bin/env python3
"""Build the Nano 4K flash disk.

The file is the bytes that land at flash address 0x200000. It is a data
file, not a bitstream. The region is 0x200000–0x3FFFFF.

Header, 5 little-endian words. The checksum does not cover these.

  +0x00  magic      0x314B5344   bytes 44 53 4B 31 ('D','S','K','1')
  +0x04  version    1
  +0x08  build      0xE1
  +0x0C  length     payload bytes, a multiple of 4
  +0x10  checksum   sum of the payload words, little-endian, mod 2^32

Payload, `length` bytes, checksummed. A 9-word directory, then the
inner core, then the sector pages.

  +0x00  core_base     0x18000  HyperRAM address of the first code word
  +0x04  core_bytes    packed code size
  +0x08  body          Modules entry, absolute
  +0x0C  init_bytes    init stream size, including the terminating 0
  +0x10  sector_bytes  1024, the size of one page
  +0x14  sector_count  4, or 5 when Blink5 continues on sector 116
  +0x18  sec0          29   directory
  +0x1C  sec1          58   AMemoryMappedToggle.rsc
  +0x20  sec2          87   Blink5.rsc header

  code     core_bytes, the packed words, first word at core_base
  init     init_bytes, (dest, value) pairs, then a 0 dest
  sectors  sector_count pages of sector_bytes, in sector-index order.
           The fourth page is Blink5's continuation when that object
           file spills. Blink.Rate is the next page. Its first word is
           the millisecond delay and the next word is the negation, so
           two delays have one checksum. The directory stays nine words.

The code and the init stream are the words the stub copies today. The
pages are the sectors SpiSector serves. Blink reads its wait from
Blink.Rate. The hardware file carries 1000 ms.

The 4K reads this file from the NOR at 0x200000. The Dock bootstrap
receives the same bytes over the UART and stores them in DDR3.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "sim"))

from link_inner import CORE_BASE, link  # noqa: E402
from sector_image import (  # noqa: E402
    AMMT_SEC,
    BLINK_CONT,
    BLINK_SEC,
    DIR_MARK,
    DIR_ROOT,
    HEADER_MARK,
    HEADER_SIZE,
    RATE_NAME,
    SECTOR,
    _name32,
)

MAGIC = 0x314B5344
VERSION = 1
BUILD = 0xE1
HEADER_WORDS = 5
HEADER_BYTES = HEADER_WORDS * 4
DIR_WORDS = 9
FLASH_BASE = 0x200000
FLASH_LIMIT = 0x400000
SECTORS = (DIR_ROOT, AMMT_SEC, BLINK_SEC)


def checksum(payload: bytes) -> int:
    if len(payload) % 4:
        raise SystemExit(f"payload is {len(payload)} bytes, not a multiple of 4")
    total = 0
    for i in range(0, len(payload), 4):
        total = (total + int.from_bytes(payload[i : i + 4], "little")) & 0xFFFFFFFF
    return total


def _words(values: list[int]) -> bytes:
    return b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in values)


def _pages_from_pairs(info: dict) -> bytes:
    """The ROM stores only the non-zero sector words. Expand them."""
    words = [0] * (3 * (SECTOR // 4))
    rom = info["words"]
    base = info["sector_rom"]
    count = info["sector_words"]
    if count % 2:
        raise SystemExit(f"sector pair list is {count} words")
    for i in range(0, count, 2):
        index = rom[base + i]
        value = rom[base + i + 1]
        if not 0 <= index < len(words):
            raise SystemExit(f"sector pair index {index} is outside the three pages")
        if words[index]:
            raise SystemExit(f"sector pair index {index} is stored twice")
        words[index] = value & 0xFFFFFFFF
    return _words(words)


def build(info: dict) -> bytes:
    if "disk" in info:
        image = info["disk"]
        if image[:4] != struct.pack("<I", MAGIC):
            raise SystemExit("boot disk has no DSK1 magic")
        if checksum(image[HEADER_BYTES:]) != int.from_bytes(image[16:20], "little"):
            raise SystemExit("boot disk checksum does not match the payload")
        return image
    code = info["code_words"]
    stream = info["init_stream"]
    pages = info["sector_pages"]
    if info["core_base"] != CORE_BASE:
        raise SystemExit(f"core base {info['core_base']:#x}")
    if len(code) != info["core_words"]:
        raise SystemExit("code word count does not match the ROM")
    if len(stream) != info["init_words"]:
        raise SystemExit("init stream length does not match the ROM")
    # The flash bootstrap and the Dock UART bootstrap both keep the core
    # out of the ROM. The ROM slice check is the in-ROM image only.
    if not info.get("flash_boot") and not info.get("uart_disk"):
        rom = info["words"]
        if rom[info["core_rom"] : info["core_rom"] + len(code)] != code:
            raise SystemExit("packed code is not the ROM slice")
        if rom[info["init_rom"] : info["init_rom"] + len(stream)] != stream:
            raise SystemExit("init stream is not the ROM slice")
    if not stream or stream[-1] != 0:
        raise SystemExit("init stream does not end with a zero dest")
    order = sorted(pages)
    for i, sec in enumerate(order):
        if sec != (i + 1) * 29:
            raise SystemExit(f"sector {sec} is not page {i}")
    raw_pages = b""
    for sec in order:
        page = pages[sec]
        if len(page) != SECTOR:
            raise SystemExit(f"sector {sec} is {len(page)} bytes")
        raw_pages += page
    if not info.get("flash_boot") and not info.get("uart_disk") and raw_pages != _pages_from_pairs(info):
        raise SystemExit("sector pages are not the ROM pairs expanded")
    if int.from_bytes(pages[DIR_ROOT][:4], "little") != DIR_MARK:
        raise SystemExit("directory page has no directory mark")
    for sec in (AMMT_SEC, BLINK_SEC):
        if int.from_bytes(pages[sec][:4], "little") != HEADER_MARK:
            raise SystemExit(f"sector {sec} has no file mark")
    rate_secs = [
        sec for sec in order
        if pages[sec][4 : 4 + len(RATE_NAME) + 1] == RATE_NAME + b"\0"
    ]
    if len(rate_secs) != 1:
        raise SystemExit(f"Blink.Rate pages {rate_secs}")
    if int.from_bytes(pages[rate_secs[0]][:4], "little") != HEADER_MARK:
        raise SystemExit("Blink.Rate has no file mark")
    directory = struct.pack(
        "<9I",
        CORE_BASE,
        len(code) * 4,
        info["body"],
        len(stream) * 4,
        SECTOR,
        len(order),
        SECTORS[0],
        SECTORS[1],
        SECTORS[2],
    )
    if len(directory) != DIR_WORDS * 4:
        raise SystemExit("directory size")
    payload = directory + _words(code) + _words(stream) + raw_pages
    if len(payload) != 36 + len(code) * 4 + len(stream) * 4 + len(raw_pages):
        raise SystemExit("payload size")
    header = struct.pack("<5I", MAGIC, VERSION, BUILD, len(payload), checksum(payload))
    image = header + payload
    if FLASH_BASE + len(image) > FLASH_LIMIT:
        raise SystemExit(
            f"disk is {len(image)} bytes at {FLASH_BASE:#x}, past {FLASH_LIMIT:#x}"
        )
    return image


def set_rate(image: bytes, delay_ms: int) -> bytes:
    """Rewrite Blink.Rate. The negation keeps the payload checksum."""
    if delay_ms % 2 or not 1 <= delay_ms <= 0x7FFF:
        raise SystemExit(f"rate {delay_ms} must be a positive even millisecond count")
    needle = struct.pack("<I", HEADER_MARK) + _name32(RATE_NAME)
    at = image.find(needle)
    if at < 0 or image.find(needle, at + 1) >= 0:
        raise SystemExit("Blink.Rate header is not unique")
    buf = bytearray(image)
    struct.pack_into("<ii", buf, at + HEADER_SIZE, delay_ms, -delay_ms)
    if checksum(bytes(buf[HEADER_BYTES:])) != int.from_bytes(image[16:20], "little"):
        raise SystemExit("rate edit changed the checksum")
    return bytes(buf)


def parse(image: bytes) -> dict:
    if len(image) < HEADER_BYTES:
        raise SystemExit("disk is shorter than the header")
    magic, version, build, length, sum_ = struct.unpack_from("<5I", image, 0)
    payload = image[HEADER_BYTES:]
    if magic != MAGIC or version != VERSION or build != BUILD:
        raise SystemExit(f"header {magic:#x} {version} {build:#x}")
    if length != len(payload) or checksum(payload) != sum_:
        raise SystemExit("checksum or length does not match the payload")
    if length < DIR_WORDS * 4:
        raise SystemExit("payload has no directory")
    fields = struct.unpack_from("<9I", payload, 0)
    return {
        "magic": magic,
        "version": version,
        "build": build,
        "length": length,
        "checksum": sum_,
        "core_base": fields[0],
        "core_bytes": fields[1],
        "body": fields[2],
        "init_bytes": fields[3],
        "sector_bytes": fields[4],
        "sector_count": fields[5],
        "sectors": fields[6:9],
        "total": len(image),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(ROOT, "sim", "out", "disk.bin"))
    parser.add_argument("--max-iter", type=int, default=1000)
    args = parser.parse_args()
    info = link(args.max_iter, flash_boot=True)
    image = build(info)
    magic, version, build_id, length, sum_ = struct.unpack_from("<5I", image, 0)
    if (magic, version, build_id) != (MAGIC, VERSION, BUILD) or length != len(image) - HEADER_BYTES:
        raise SystemExit("round trip moved the header")
    if checksum(image[HEADER_BYTES:]) != sum_:
        raise SystemExit("round trip moved the checksum")
    got = {
        "checksum": sum_,
        "magic": magic,
        "version": version,
        "build": build_id,
        "length": length,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as out:
        out.write(image)
    end = FLASH_BASE + len(image)
    print(
        f"[ok] disk {args.out} bytes {len(image)} "
        f"flash {FLASH_BASE:#x}..{end:#x} checksum {got['checksum']:08x}"
    )
    print(
        f"[ok] magic {got['magic']:08x} version {got['version']} build {got['build']:#x} "
        f"payload {got['length']}"
    )
    print(
        f"[ok] boot image {info['core_words'] * 4} bytes "
        f"body {info['body']:#x} root {info['desc']:#x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
