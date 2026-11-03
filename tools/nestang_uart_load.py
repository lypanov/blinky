#!/usr/bin/env python3
"""One-shot NESTang v0.4 UART ROM loader.

The in-tree C loader (loader/nes_loader.cpp) always enters a gamepad loop
after sendNES(), and on Linux that select() has a NULL timeout — so
`timeout(1)` kills the process. When stdout is fully buffered (no TTY),
the "transmitted" line never appears even if the ROM bytes were written.

This sender does not touch gamepads. It opens the BL702 UART (ttyUSB1),
sends the 0x35 reset sequence, then the iNES bytes to address 0x37, and
exits. Packets use n<=255 so the 8-bit count field equals the payload
length (count==0 means 256 bytes on the FPGA).

Packet (hw_uart.v UartDemux):
  checksum | address | count | (count data bytes, or 256 if count==0)
Checksum is 8-bit such that sum(all bytes) == 0.

v0.4 NES_Tang20k: FREQ=32_250_000, BAUDRATE=921600. Integer division
gives CLKS_PER_BIT=34, so the FPGA's actual bit clock is
32250000/34 = 948529 baud. --baud 948529 uses termios2 BOTHER to match.
uart_rx's 8-bit counter cannot do 115200 at this FREQ (279 clocks).

Pins (nestang_dock.cst): UART_TXD=M11, UART_RXD=T13 on the BL702 USB-UART.
"""
from __future__ import annotations

import argparse
import array
import ctypes
import fcntl
import os
import sys
import termios
import time


NCCS = 19
BOTHER = 0o010000
CBAUD = 0o010017
TCGETS2 = 0x802C542A
TCSETS2 = 0x402C542B
TIOCMGET = 0x5415
TIOCMSET = 0x5418
TIOCM_DTR = 0x002
TIOCM_RTS = 0x004


class Termios2(ctypes.Structure):
    _fields_ = [
        ("c_iflag", ctypes.c_uint),
        ("c_oflag", ctypes.c_uint),
        ("c_cflag", ctypes.c_uint),
        ("c_lflag", ctypes.c_uint),
        ("c_line", ctypes.c_ubyte),
        ("c_cc", ctypes.c_ubyte * NCCS),
        ("c_ispeed", ctypes.c_uint),
        ("c_ospeed", ctypes.c_uint),
    ]


def format_packet(addr: int, data: bytes) -> bytes:
    n = len(data)
    if not 1 <= n <= 255:
        raise ValueError(f"payload must be 1..255 bytes, got {n}")
    total = (addr + n + sum(data)) & 0xFF
    return bytes([(-total) & 0xFF, addr & 0xFF, n]) + data


def _set_raw_cflag(cflag: int) -> int:
    cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    return cflag


def open_tty(path: str, baud: int) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[2] = _set_raw_cflag(attrs[2])
        attrs[3] = 0  # lflag
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        standard = getattr(termios, f"B{baud}", None)
        if standard is not None:
            attrs[4] = standard
            attrs[5] = standard
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            used = f"termios B{baud}"
        else:
            # Any baud (incl. FPGA 32250000/34 = 948529) via termios2 BOTHER.
            attrs[4] = termios.B38400
            attrs[5] = termios.B38400
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            _set_custom_baud(fd, baud)
            used = "termios2 BOTHER"

        buf = array.array("I", [0])
        fcntl.ioctl(fd, TIOCMGET, buf, True)
        buf[0] |= TIOCM_DTR | TIOCM_RTS
        fcntl.ioctl(fd, TIOCMSET, buf, True)
        termios.tcflush(fd, termios.TCIOFLUSH)
        print(f"opened {path} baud={baud} ({used}) DTR+RTS 8N1 -crtscts", flush=True)
        return fd
    except Exception:
        os.close(fd)
        raise


def _set_custom_baud(fd: int, baud: int) -> None:
    t = Termios2()
    r = fcntl.ioctl(fd, TCGETS2, t)
    if r != 0:
        raise OSError("TCGETS2 failed")
    t.c_cflag &= ~CBAUD
    t.c_cflag |= BOTHER
    t.c_cflag = _set_raw_cflag(t.c_cflag)
    t.c_iflag = 0
    t.c_oflag = 0
    t.c_lflag = 0
    t.c_ispeed = baud
    t.c_ospeed = baud
    r = fcntl.ioctl(fd, TCSETS2, t)
    if r != 0:
        raise OSError("TCSETS2 failed")


def write_all(fd: int, data: bytes, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    view = memoryview(data)
    while view:
        try:
            n = os.write(fd, view)
        except BlockingIOError:
            n = 0
        if n:
            view = view[n:]
            continue
        if time.monotonic() > deadline:
            raise TimeoutError("UART write timed out")
        time.sleep(0.001)
    termios.tcdrain(fd)


def read_available(fd: int, n: int = 4096) -> bytes:
    try:
        return os.read(fd, n)
    except BlockingIOError:
        return b""


def send_addr(fd: int, addr: int, payload: bytes, chunk: int, gap_s: float) -> int:
    sent = 0
    for i in range(0, len(payload), chunk):
        part = payload[i : i + chunk]
        write_all(fd, format_packet(addr, part))
        sent += len(part)
        if gap_s:
            time.sleep(gap_s)
    return sent


def listen(fd: int, seconds: float) -> bytes:
    end = time.monotonic() + seconds
    chunks: list[bytes] = []
    while time.monotonic() < end:
        b = read_available(fd)
        if b:
            chunks.append(b)
            sys.stdout.write(b.decode("latin1", errors="replace"))
            sys.stdout.flush()
        else:
            time.sleep(0.01)
    return b"".join(chunks)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rom", nargs="?", help="iNES ROM path (omit to only listen)")
    p.add_argument("-c", "--port", default="/dev/ttyUSB1")
    p.add_argument("-b", "--baud", type=int, default=921600)
    p.add_argument("--chunk", type=int, default=64, help="payload bytes per packet (1-255)")
    p.add_argument("--gap-ms", type=float, default=0.5, help="delay between packets")
    p.add_argument("--listen", type=float, default=0.0, help="seconds to print FPGA TX first")
    p.add_argument("--listen-after", type=float, default=0.5)
    p.add_argument("--reset-ms", type=float, default=50.0)
    p.add_argument("--no-reset", action="store_true")
    args = p.parse_args()
    if not 1 <= args.chunk <= 255:
        p.error("chunk must be 1..255")

    fd = open_tty(args.port, args.baud)
    try:
        if args.listen > 0:
            print(f"listening {args.listen:.1f}s for FPGA TX…", flush=True)
            got = listen(fd, args.listen)
            print(f"\n[listen got {len(got)} bytes]", flush=True)

        if not args.rom:
            return 0

        rom = open(args.rom, "rb").read()
        if rom[:4] != b"NES\x1a":
            print(f"error: {args.rom} is not iNES (header {rom[:4]!r})", file=sys.stderr)
            return 2
        print(f"ROM {args.rom} {len(rom)} bytes PRG={rom[4]} CHR={rom[5]}", flush=True)

        if not args.no_reset:
            send_addr(fd, 0x35, b"\x01", 1, 0)
            time.sleep(args.reset_ms / 1000.0)
            send_addr(fd, 0x35, b"\x00", 1, 0)
            time.sleep(args.reset_ms / 1000.0)
            print("sent loader reset 0x35=1 then 0x35=0", flush=True)

        t0 = time.monotonic()
        n = send_addr(fd, 0x37, rom, args.chunk, args.gap_ms / 1000.0)
        dt = time.monotonic() - t0
        print(f"sent {n} bytes to 0x37 in {dt:.3f}s chunk={args.chunk} gap={args.gap_ms}ms", flush=True)

        if args.listen_after > 0:
            print(f"listening {args.listen_after:.1f}s after send…", flush=True)
            got = listen(fd, args.listen_after)
            print(f"\n[after got {len(got)} bytes]", flush=True)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
