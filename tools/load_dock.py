#!/usr/bin/env python3
"""SRAM-load a bitstream and UART disk onto the Primer 20K Dock.

Never flashes. Never opens the Nano 4K. See docs/load-boards.md.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from send_dock_disk import open_channel, read_some  # noqa: E402

DOCK_PORT = "3-3.1.1"
NANO_PORT = "3-3.3"
BIND = "/usr/local/sbin/blinky-bind-dock-uart"
BOARD = "tangprimer20k"

# Child / parent exit codes.
OK = 0
USAGE = 2
EYE_FAIL = 10
NO_WAIT = 11
NOT_ARMED = 12
LOAD_FAIL = 13
BIND_FAIL = 14
UART_FAIL = 15
WRONG_BOARD = 16


def log(msg: str) -> None:
    print(msg, flush=True)


def printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 or b in (9, 10, 13) else "." for b in data)


def classify_line(line: str) -> str:
    s = line.strip()
    if not s:
        return "empty"
    if s.startswith("..0080") and s.rstrip().endswith("F 4B"):
        return "eye_fail"
    if len(s) >= 17 and s.startswith("C."):
        mask = s[7:17]
        if mask == "FFFFFFFFFF":
            return "armed"
        if s.startswith("C.0440") and mask == "0000000000":
            if " G A55A" in s:
                return "wait"
            return "wait_bad_g"
        if not s.startswith("C.0440"):
            return "trained_moved"
    return "other"


def sysfs_usb(port: str) -> tuple[int, int]:
    base = Path("/sys/bus/usb/devices") / port
    if not base.is_dir():
        sys.exit(f"USB port {port} is not on the bus")
    bus = int((base / "busnum").read_text())
    addr = int((base / "devnum").read_text())
    return bus, addr


def bind_uart() -> None:
    try:
        subprocess.run(["sudo", "-n", BIND], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log(
            "bind failed. Use sudo -n /usr/local/sbin/blinky-bind-dock-uart "
            "(passwordless). sudo -n true is the wrong check."
        )
        raise SystemExit(BIND_FAIL) from exc


def sram_load(bus: int, addr: int, bitstream: Path) -> None:
    busdev = f"{bus:03d}:{addr:03d}"
    cmd = [
        "openFPGALoader",
        "--busdev-num",
        busdev,
        "-b",
        BOARD,
        "-m",
        str(bitstream),
    ]
    log(f"SRAM load {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stdout + proc.stderr
    if proc.returncode != 0:
        log(text[-800:])
        raise SystemExit(LOAD_FAIL)
    if "write to ram" not in text.lower():
        log("openFPGALoader did not say 'write to ram'; refusing")
        log(text[-800:])
        raise SystemExit(LOAD_FAIL)
    if "100.00%" not in text and "100%" not in text:
        log("SRAM load did not reach 100%")
        log(text[-800:])
        raise SystemExit(LOAD_FAIL)
    log(f"SRAM load ok bus {busdev}")


def send_disk(ftdi, ctx, path: Path) -> int:
    payload = path.read_bytes()
    sent = 0
    buf = ctypes.create_string_buffer(4096)
    while sent < len(payload):
        data = read_some(ftdi, ctx, buf)
        chunk = payload[sent : sent + 256]
        raw = ctypes.create_string_buffer(chunk)
        n = ftdi.ftdi_write_data(ctx, ctypes.cast(raw, ctypes.c_void_p), len(chunk))
        if n < 0:
            sys.exit(f"write failed {n}")
        sent += n
        if n == 0:
            time.sleep(0.001)
        # Keep RX drained so the FTDI does not stall, but do not print it.
        if data:
            pass
    return sent


def read_lines(ftdi, ctx, buf, acc: bytes):
    data = read_some(ftdi, ctx, buf)
    if not data:
        return acc, []
    acc += data
    lines = []
    while b"\n" in acc:
        raw, acc = acc.split(b"\n", 1)
        text = printable(raw).strip()
        if text:
            lines.append(text)
    return acc, lines


def drain_rx(ftdi, ctx, seconds: float) -> None:
    """Drop leftover status from the previous image after a SRAM load."""
    buf = ctypes.create_string_buffer(4096)
    acc = b""
    end = time.time() + seconds
    while time.time() < end:
        acc, _ = read_lines(ftdi, ctx, buf, acc)
        time.sleep(0.02)


def wait_for_disk(ftdi, ctx, seconds: float) -> tuple[str, str]:
    buf = ctypes.create_string_buffer(4096)
    acc = b""
    end = time.time() + seconds
    stuck = 0
    moved = 0
    bad_g = 0
    last = ""
    while time.time() < end:
        acc, lines = read_lines(ftdi, ctx, buf, acc)
        if not lines:
            time.sleep(0.02)
            continue
        for line in lines:
            last = line
            kind = classify_line(line)
            if kind == "wait":
                return kind, line
            if kind == "armed":
                # Previous image still draining. Not this load.
                continue
            if kind == "eye_fail":
                stuck += 1
                moved = 0
                bad_g = 0
                if stuck >= 4:
                    return kind, line
                continue
            stuck = 0
            if kind == "trained_moved":
                moved += 1
                if moved >= 3:
                    return kind, line
                continue
            moved = 0
            if kind == "wait_bad_g":
                bad_g += 1
                if bad_g >= 3:
                    return kind, line
                continue
            bad_g = 0
    return "timeout", last


def wait_armed(ftdi, ctx, seconds: float) -> tuple[bool, str]:
    """After this load's wait and disk send, the next full mask is this boot."""
    buf = ctypes.create_string_buffer(4096)
    acc = b""
    end = time.time() + seconds
    last = ""
    while time.time() < end:
        acc, lines = read_lines(ftdi, ctx, buf, acc)
        if not lines:
            time.sleep(0.02)
            continue
        for line in lines:
            last = line
            if classify_line(line) == "armed":
                return True, line
    return False, last


def child_boot(bitstream: Path, disk: Path, wait_s: float, armed_s: float) -> int:
    bus, addr = sysfs_usb(DOCK_PORT)
    nano = Path("/sys/bus/usb/devices") / NANO_PORT
    if nano.is_dir():
        nbus = int((nano / "busnum").read_text())
        naddr = int((nano / "devnum").read_text())
        if (nbus, naddr) == (bus, addr):
            log("Dock port resolved to the Nano; refusing")
            return WRONG_BOARD
    bind_uart()
    log("UART bound")
    sram_load(bus, addr, bitstream)
    try:
        ftdi, ctx = open_channel(addr)
    except SystemExit as exc:
        log(f"UART open failed: {exc}")
        return UART_FAIL
    drain_rx(ftdi, ctx, 0.25)
    kind, sample = wait_for_disk(ftdi, ctx, wait_s)
    if kind != "wait":
        log(f"no wait ({kind}): {sample}")
        return EYE_FAIL if kind == "eye_fail" else NO_WAIT
    log(f"wait {sample[:160]}")
    sent = send_disk(ftdi, ctx, disk)
    log(f"sent {sent} bytes")
    ok, sample = wait_armed(ftdi, ctx, armed_s)
    if not ok:
        log(f"not armed: {sample[:160]}")
        return NOT_ARMED
    log(f"armed {sample[:160]}")
    return OK


def self_test() -> int:
    cases = [
        (
            "wait",
            "C.0440 0000000000 00000000 0000BFEB 0140000001400000 "
            "0000BFEB 00000000 00000000 000C 000A E0 FF00 G A55A C0 0B C1 0D BO 0E F AB",
        ),
        (
            "armed",
            "C.3B68 FFFFFFFFFF 00000000 00001DB4 AFE00000AFE00000 "
            "0000811B 00000000 00000000 000C 000A E0 FF00 G A55A C0 0B C1 0D BO 0E F AB",
        ),
        (
            "eye_fail",
            "..0080 0000000000 00000000 00000000 000F15FE000F15FE "
            "00000000 00000000 00000000 000B 000C E0 0000 G 020C C0 02 C1 0C BO 10 F 4B",
        ),
        (
            "trained_moved",
            "C.04B8 0000000000 00000000 0000BFFD CD000000CD000000 "
            "0000BFFD 00000000 00000000 000C 000A E0 FF5A G A55A C0 03 C1 0D BO 0E F AB",
        ),
        (
            "wait_bad_g",
            "C.0440 0000000000 00000000 0000BFEB 01FF000001FF0000 "
            "0000BFEB 00000000 00000000 000C 000A E0 A55A G FF5A C0 00 C1 01 BO 18 F AB",
        ),
        (
            "trained_moved",
            "C.00F4 0000000000 00000000 0000BFB9 0000000000000000 "
            "0000BFBB 00000000 00000000 000C 000A E0 A55A G 855A C0 00 C1 01 BO 18 F AB",
        ),
    ]
    failed = 0
    for want, line in cases:
        got = classify_line(line)
        if got != want:
            log(f"self-test {want!r} got {got!r}")
            failed += 1
    if failed:
        return 1
    log("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("bitstream", nargs="?", type=Path, help="Dock .fs (SRAM)")
    parser.add_argument("disk", nargs="?", type=Path, help="UART disk.bin")
    parser.add_argument("--tries", type=int, default=16, help="SRAM-load retries")
    parser.add_argument(
        "--wait-s",
        type=float,
        default=12.0,
        help="seconds to listen for C.0440 after each load",
    )
    parser.add_argument(
        "--armed-s",
        type=float,
        default=40.0,
        help="seconds to wait for mask FFFFFFFFFF after the disk",
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.bitstream is None or args.disk is None:
        parser.error("bitstream and disk are required")
    bitstream = args.bitstream.resolve()
    disk = args.disk.resolve()
    if not bitstream.is_file():
        parser.error(f"no bitstream {bitstream}")
    if not disk.is_file():
        parser.error(f"no disk {disk}")
    if bitstream.suffix != ".fs":
        parser.error("bitstream must be a .fs file")

    if args.child:
        return child_boot(bitstream, disk, args.wait_s, args.armed_s)

    if os.environ.get("OPENFPGALOADER_FLASH") == "1":
        log("OPENFPGALOADER_FLASH is set; refusing")
        return USAGE

    child_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        str(bitstream),
        str(disk),
        "--wait-s",
        str(args.wait_s),
        "--armed-s",
        str(args.armed_s),
    ]
    retryable = {EYE_FAIL, NO_WAIT, NOT_ARMED, UART_FAIL}
    last = NO_WAIT
    for i in range(1, args.tries + 1):
        log(f"try {i}/{args.tries}")
        proc = subprocess.run(child_cmd)
        last = proc.returncode
        if last == OK:
            log("ok")
            log(
                "next: webcam /dev/video2 for the LED. Capture card /dev/video0 "
                "YUYV 1024x768 only after the arm word. Grey luma ~139 is not armed."
            )
            return OK
        if last not in retryable:
            return last
        time.sleep(0.3)
    log(f"gave up after {args.tries} tries, last rc={last}")
    return last


if __name__ == "__main__":
    raise SystemExit(main())
