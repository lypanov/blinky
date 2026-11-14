#!/usr/bin/env python3
"""SRAM-load a bitstream and write the NOR disk onto the Tang Nano 4K.

Never writes a bitstream to flash. Never opens the Primer 20K Dock.
The only flash write is the disk data file at 0x200000. See docs/load-boards.md.
"""
from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

NANO_PORT = "3-3.3"
DOCK_PORT = "3-3.1.1"
BOARD = "tangnano4k"
FLASH_BASE = 0x200000
FLASH_LIMIT = 0x400000
GUARD_OFF = 0x1FFF00
GUARD_SIZE = 256
MAGIC = 0x314B5344
HEADER_LEN = 20

OK = 0
USAGE = 2
LOAD_FAIL = 13
WRONG_BOARD = 16
DISK_HEADER = 17
NOR_FAIL = 18
GUARD_FAIL = 19
READBACK_FAIL = 20


def log(msg: str) -> None:
    print(msg, flush=True)


def sysfs_usb(port: str) -> tuple[int, int]:
    base = Path("/sys/bus/usb/devices") / port
    if not base.is_dir():
        sys.exit(f"USB port {port} is not on the bus")
    bus = int((base / "busnum").read_text())
    addr = int((base / "devnum").read_text())
    return bus, addr


def busdev(bus: int, addr: int) -> str:
    return f"{bus:03d}:{addr:03d}"


def checksum_payload(payload: bytes) -> int:
    total = 0
    for i in range(0, len(payload), 4):
        total = (total + int.from_bytes(payload[i : i + 4], "little")) & 0xFFFFFFFF
    return total


def parse_disk(data: bytes) -> dict:
    if len(data) < HEADER_LEN:
        raise ValueError(f"disk is {len(data)} bytes, shorter than the 20-byte header")
    magic, version, build, length, sum_ = struct.unpack_from("<5I", data, 0)
    payload = data[HEADER_LEN:]
    got = checksum_payload(payload)
    return {
        "magic": magic,
        "version": version,
        "build": build,
        "length": length,
        "checksum": sum_,
        "got": got,
        "size": len(data),
    }


def check_disk(path: Path) -> dict:
    if path.suffix in {".fs", ".bit"}:
        raise SystemExit(f"refusing {path.name}: that is a bitstream, not a disk")
    data = path.read_bytes()
    end = FLASH_BASE + len(data)
    if end > FLASH_LIMIT:
        raise SystemExit(
            f"disk ends at {end:#x}, past the NOR window {FLASH_LIMIT:#x}"
        )
    info = parse_disk(data)
    if info["magic"] != MAGIC or info["version"] != 1:
        raise SystemExit(
            f"bad disk header magic={info['magic']:#x} version={info['version']}"
        )
    if info["length"] != len(data) - HEADER_LEN:
        raise SystemExit("length field does not match the file")
    if info["got"] != info["checksum"]:
        raise SystemExit(
            f"checksum {info['got']:08x} != header {info['checksum']:08x}"
        )
    log(
        f"disk {path} {info['size']} bytes build {info['build']:#x} "
        f"checksum {info['checksum']:08x}"
    )
    return info


def run_ofl(dev: str, extra: list[str], fail_code: int) -> str:
    cmd = ["openFPGALoader", "--busdev-num", dev, "-b", BOARD, *extra]
    log(" ".join(cmd))
    # NOR verify is minutes. Swallowing stdout looks like a hang.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line)
    rc = proc.wait()
    text = "".join(lines)
    if rc != 0:
        raise SystemExit(fail_code)
    return text


def dump_flash(dev: str, offset: int, size: int, dest: Path) -> None:
    run_ofl(
        dev,
        [
            "--external-flash",
            "--dump-flash",
            "-o",
            f"{offset:#x}",
            "--file-size",
            str(size),
            str(dest),
        ],
        NOR_FAIL,
    )
    if not dest.is_file() or dest.stat().st_size != size:
        log(f"dump {dest} is missing or {dest.stat().st_size if dest.exists() else 0} bytes")
        raise SystemExit(NOR_FAIL)


def write_nor(dev: str, disk: Path) -> None:
    size = disk.stat().st_size
    with tempfile.TemporaryDirectory(prefix="blinky-nano-") as tmp:
        tmp_path = Path(tmp)
        before = tmp_path / "guard_before.bin"
        after = tmp_path / "guard_after.bin"
        readback = tmp_path / "disk_readback.bin"
        log(f"guard dump {GUARD_OFF:#x} ({GUARD_SIZE} bytes)")
        dump_flash(dev, GUARD_OFF, GUARD_SIZE, before)
        text = run_ofl(
            dev,
            [
                "-f",
                "--external-flash",
                "-o",
                f"{FLASH_BASE:#x}",
                "--verify",
                str(disk),
            ],
            NOR_FAIL,
        )
        if "100.00%" not in text and "100%" not in text:
            log("NOR write did not reach 100%")
            log(text[-800:])
            raise SystemExit(NOR_FAIL)
        log(f"read-back {size} bytes at {FLASH_BASE:#x}")
        dump_flash(dev, FLASH_BASE, size, readback)
        if readback.read_bytes() != disk.read_bytes():
            log("read-back does not match the disk file")
            raise SystemExit(READBACK_FAIL)
        log("read-back matches")
        dump_flash(dev, GUARD_OFF, GUARD_SIZE, after)
        if after.read_bytes() != before.read_bytes():
            log(f"bytes at {GUARD_OFF:#x} changed; refusing")
            raise SystemExit(GUARD_FAIL)
        log(f"bytes below {FLASH_BASE:#x} are unchanged")


def sram_load(dev: str, bitstream: Path) -> None:
    text = run_ofl(dev, ["-m", str(bitstream)], LOAD_FAIL)
    low = text.lower()
    if "write to ram" not in low:
        log("openFPGALoader did not say 'write to ram'; refusing")
        log(text[-800:])
        raise SystemExit(LOAD_FAIL)
    if "100.00%" not in text and "100%" not in text:
        log("SRAM load did not reach 100%")
        log(text[-800:])
        raise SystemExit(LOAD_FAIL)
    log(f"SRAM load ok bus {dev}")


def load(bitstream: Path, disk: Path, sram_only: bool) -> int:
    nbus, naddr = sysfs_usb(NANO_PORT)
    dock = Path("/sys/bus/usb/devices") / DOCK_PORT
    if dock.is_dir():
        dbus = int((dock / "busnum").read_text())
        daddr = int((dock / "devnum").read_text())
        if (dbus, daddr) == (nbus, naddr):
            log("Nano port resolved to the Dock; refusing")
            return WRONG_BOARD
        log(f"Dock is {busdev(dbus, daddr)} on {DOCK_PORT}; not opening it")
    nano = busdev(nbus, naddr)
    log(f"Nano is {nano} on {NANO_PORT}")
    if sram_only:
        log("skipping NOR write (--sram-only)")
    else:
        check_disk(disk)
        write_nor(nano, disk)
    sram_load(nano, bitstream)
    log("ok")
    log(
        "next: webcam /dev/video2 --roi nano4k for the LED. "
        "Capture card /dev/video0 YUYV 720x480 only after the arm word. "
        "Do not convert YUYV to RGB to judge luma."
    )
    return OK


def self_test() -> int:
    payload = bytes([i % 256 for i in range(64)])
    total = checksum_payload(payload)
    good = struct.pack("<5I", MAGIC, 1, 0xE1, len(payload), total) + payload
    info = parse_disk(good)
    failed = 0

    def expect(cond: bool, name: str) -> None:
        nonlocal failed
        if not cond:
            log(f"self-test failed: {name}")
            failed += 1

    expect(info["magic"] == MAGIC, "magic")
    expect(info["version"] == 1, "version")
    expect(info["build"] == 0xE1, "build")
    expect(info["got"] == total, "checksum")
    bad_magic = struct.pack("<5I", 0xDEAD, 1, 0xE1, len(payload), total) + payload
    expect(parse_disk(bad_magic)["magic"] != MAGIC, "bad magic")
    bad_sum = struct.pack("<5I", MAGIC, 1, 0xE1, len(payload), total ^ 1) + payload
    expect(parse_disk(bad_sum)["got"] != parse_disk(bad_sum)["checksum"], "bad sum")
    if failed:
        return 1
    log("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("bitstream", nargs="?", type=Path, help="Nano .fs (SRAM)")
    parser.add_argument("disk", nargs="?", type=Path, help="NOR disk.bin at 0x200000")
    parser.add_argument(
        "--sram-only",
        action="store_true",
        help="skip the NOR write when the disk is already on the chip",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.bitstream is None:
        parser.error("bitstream is required")
    if not args.sram_only and args.disk is None:
        parser.error("disk is required unless --sram-only")
    bitstream = args.bitstream.resolve()
    disk = args.disk.resolve() if args.disk else Path("/dev/null")
    if not bitstream.is_file():
        parser.error(f"no bitstream {bitstream}")
    if not args.sram_only and not disk.is_file():
        parser.error(f"no disk {disk}")
    if bitstream.suffix != ".fs":
        parser.error("bitstream must be a .fs file")
    if os.environ.get("OPENFPGALOADER_FLASH") == "1":
        log("OPENFPGALOADER_FLASH is set; refusing")
        return USAGE
    return load(bitstream, disk, args.sram_only)


if __name__ == "__main__":
    raise SystemExit(main())
