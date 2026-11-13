#!/usr/bin/env python3
"""Send disk.bin to the Dock on FTDI channel B, without resetting the chip.

Bus 3, interface B, 115200 8N1. The device address changes; pass --addr.
ftdi_usb_open calls ftdi_usb_reset, and that reset drops a trained DDR3. This opens the
device with libusb and does not call ftdi_usb_reset.

A listen prints the training line. A send writes the file on the same
open handle, so the read never closes. Do not send until a line starts
with C. --gap waits after each 4-byte word so that store shows up.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time


def _lib(name: str):
    return ctypes.CDLL(name)


def open_channel(addr: int):
    usb = _lib("libusb-1.0.so.0")
    ftdi = _lib("libftdi1.so.2")
    usb.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    usb.libusb_init.restype = ctypes.c_int
    usb.libusb_get_device_list.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ]
    usb.libusb_get_device_list.restype = ctypes.c_ssize_t
    usb.libusb_free_device_list.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
    usb.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
    usb.libusb_get_bus_number.restype = ctypes.c_uint8
    usb.libusb_get_device_address.argtypes = [ctypes.c_void_p]
    usb.libusb_get_device_address.restype = ctypes.c_uint8
    usb.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    usb.libusb_open.restype = ctypes.c_int
    usb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    usb.libusb_claim_interface.restype = ctypes.c_int
    usb.libusb_kernel_driver_active.argtypes = [ctypes.c_void_p, ctypes.c_int]
    usb.libusb_kernel_driver_active.restype = ctypes.c_int
    usb.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
    usb.libusb_detach_kernel_driver.restype = ctypes.c_int
    ftdi.ftdi_new.restype = ctypes.c_void_p
    ftdi.ftdi_set_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ftdi.ftdi_set_interface.restype = ctypes.c_int
    ftdi.ftdi_set_usbdev.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    ftdi.ftdi_set_baudrate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ftdi.ftdi_set_baudrate.restype = ctypes.c_int
    ftdi.ftdi_set_line_property.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int
    ]
    ftdi.ftdi_set_line_property.restype = ctypes.c_int
    ftdi.ftdi_set_latency_timer.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
    ftdi.ftdi_set_latency_timer.restype = ctypes.c_int
    ftdi.ftdi_read_data.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    ftdi.ftdi_read_data.restype = ctypes.c_int
    ftdi.ftdi_write_data.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    ftdi.ftdi_write_data.restype = ctypes.c_int
    ftdi.ftdi_get_error_string.argtypes = [ctypes.c_void_p]
    ftdi.ftdi_get_error_string.restype = ctypes.c_char_p

    ctx_usb = ctypes.c_void_p()
    if usb.libusb_init(ctypes.byref(ctx_usb)) != 0:
        sys.exit("libusb_init failed")
    devs = ctypes.POINTER(ctypes.c_void_p)()
    n = usb.libusb_get_device_list(ctx_usb, ctypes.byref(devs))
    if n < 0:
        sys.exit("libusb_get_device_list failed")
    found = None
    for i in range(n):
        dev = devs[i]
        if usb.libusb_get_bus_number(dev) == 3 and usb.libusb_get_device_address(dev) == addr:
            found = dev
            break
    if found is None:
        sys.exit(f"FTDI bus 3 address {addr} is not open")
    handle = ctypes.c_void_p()
    if usb.libusb_open(found, ctypes.byref(handle)) != 0:
        sys.exit("libusb_open failed")
    usb.libusb_free_device_list(devs, 1)

    ctx = ftdi.ftdi_new()
    if ftdi.ftdi_set_interface(ctx, 2) != 0:
        sys.exit("ftdi_set_interface failed")
    ftdi.ftdi_set_usbdev(ctx, handle)
    # ftdi_usb_open would set the chip type and then reset the UART.
    # The type has to be set or reads fail. The reset is skipped.
    class Desc(ctypes.Structure):
        _layout_ = "ms"
        _pack_ = 1
        _fields_ = [
            ("bLength", ctypes.c_uint8),
            ("bDescriptorType", ctypes.c_uint8),
            ("bcdUSB", ctypes.c_uint16),
            ("bDeviceClass", ctypes.c_uint8),
            ("bDeviceSubClass", ctypes.c_uint8),
            ("bDeviceProtocol", ctypes.c_uint8),
            ("bMaxPacketSize0", ctypes.c_uint8),
            ("idVendor", ctypes.c_uint16),
            ("idProduct", ctypes.c_uint16),
            ("bcdDevice", ctypes.c_uint16),
        ]
    class Head(ctypes.Structure):
        _fields_ = [
            ("usb_ctx", ctypes.c_void_p),
            ("usb_dev", ctypes.c_void_p),
            ("usb_read_timeout", ctypes.c_int),
            ("usb_write_timeout", ctypes.c_int),
            ("type", ctypes.c_int),
            ("baudrate", ctypes.c_int),
            ("bitbang_enabled", ctypes.c_ubyte),
            ("readbuffer", ctypes.c_void_p),
            ("readbuffer_offset", ctypes.c_uint),
            ("readbuffer_remaining", ctypes.c_uint),
            ("readbuffer_chunksize", ctypes.c_uint),
            ("writebuffer_chunksize", ctypes.c_uint),
            ("max_packet_size", ctypes.c_uint),
        ]
    usb.libusb_get_device_descriptor.argtypes = [ctypes.c_void_p, ctypes.POINTER(Desc)]
    usb.libusb_get_device_descriptor.restype = ctypes.c_int
    desc = Desc()
    if usb.libusb_get_device_descriptor(found, ctypes.byref(desc)) != 0:
        sys.exit("device descriptor failed")
    kind = {
        0x200: 0, 0x400: 1, 0x500: 2, 0x600: 3,
        0x700: 4, 0x800: 5, 0x900: 6, 0x1000: 7,
    }.get(desc.bcdDevice)
    if kind is None:
        sys.exit(f"unknown FTDI bcdDevice {desc.bcdDevice:#x}")
    ctypes.cast(ctx, ctypes.POINTER(Head)).contents.type = kind
    # INTERFACE_B is libusb interface 1. Claim it. Do not reset the chip.
    if usb.libusb_kernel_driver_active(handle, 1) == 1:
        usb.libusb_detach_kernel_driver(handle, 1)
    rc = usb.libusb_claim_interface(handle, 1)
    if rc != 0:
        sys.exit(f"claim interface B failed rc={rc}")
    if ftdi.ftdi_set_baudrate(ctx, 115200) != 0:
        err = ftdi.ftdi_get_error_string(ctx)
        sys.exit("baud " + (err.decode() if err else ""))
    if ftdi.ftdi_set_line_property(ctx, 8, 0, 0) != 0:
        sys.exit("line property failed")
    ftdi.ftdi_set_latency_timer(ctx, 1)
    head = ctypes.cast(ctx, ctypes.POINTER(Head)).contents
    if head.max_packet_size == 0:
        head.max_packet_size = 512 if kind >= 4 else 64
    return ftdi, ctx


def read_some(ftdi, ctx, buf) -> bytes:
    n = ftdi.ftdi_read_data(ctx, ctypes.cast(buf, ctypes.c_void_p), len(buf))
    if n < 0:
        err = ftdi.ftdi_get_error_string(ctx)
        sys.exit("read failed " + (err.decode() if err else str(n)))
    if n == 0:
        return b""
    return buf.raw[:n]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addr", type=int, default=78, help="USB device address on bus 3")
    parser.add_argument("--listen", type=float, default=0, help="seconds to print RX")
    parser.add_argument("--send", help="file to write after --listen, on the same open")
    parser.add_argument(
        "--gap",
        type=float,
        default=0,
        help="seconds to wait after each 4-byte word, so a status line can show that store",
    )
    args = parser.parse_args()
    if args.listen <= 0 and not args.send:
        parser.error("pass --listen, --send, or both")
    ftdi, ctx = open_channel(args.addr)
    buf = ctypes.create_string_buffer(4096)
    if args.listen > 0:
        end = time.time() + args.listen
        while time.time() < end:
            data = read_some(ftdi, ctx, buf)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                time.sleep(0.02)
    if args.send:
        payload = open(args.send, "rb").read()
        sent = 0
        step = 4 if args.gap > 0 else 256
        while sent < len(payload):
            data = read_some(ftdi, ctx, buf)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            chunk = payload[sent:sent + step]
            raw = ctypes.create_string_buffer(chunk)
            n = ftdi.ftdi_write_data(ctx, ctypes.cast(raw, ctypes.c_void_p), len(chunk))
            if n < 0:
                sys.exit(f"write failed {n}")
            sent += n
            if n == 0 or args.gap > 0:
                time.sleep(args.gap if args.gap > 0 else 0.001)
        # Drain the lines that follow the boot.
        end = time.time() + 3
        while time.time() < end:
            data = read_some(ftdi, ctx, buf)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                time.sleep(0.02)
        print(f"\n[ok] sent {sent} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
