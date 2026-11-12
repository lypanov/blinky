#!/usr/bin/env python3
"""Append a VINDSTYRKA CSV row every 30 minutes from the ESP32-C6 console.

The firmware already prints Zigbee reports. This process only reads them.
It does not flash, and it does not toggle the USB-JTAG reset sequence.

Opens only this device, with DTR and RTS cleared together:

  /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_40:4C:CA:40:5B:18-if00
  USB 303a:1001, serial 40:4C:CA:40:5B:18

Never opens the M5Paper (CP210x 10c4:ea60, serial 0214228B, /dev/ttyUSB0)
or the MaixDock.

CSV:  /home/bot/fpga/blinky/esp32c6/logs/vindstyrka.csv
Raw:  /home/bot/fpga/blinky/esp32c6/logs/vindstyrka-reports.log

Stop the user service with:

  systemctl --user stop vindstyrka-overnight-log.service
  systemctl --user disable vindstyrka-overnight-log.service
"""

from __future__ import annotations

import csv
import errno
import fcntl
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import traceback
import tty
from datetime import datetime
from pathlib import Path

BYID = (
    "/dev/serial/by-id/"
    "usb-Espressif_USB_JTAG_serial_debug_unit_40:4C:CA:40:5B:18-if00"
)
C6_VENDOR = "303a"
C6_PRODUCT = "1001"
C6_SERIAL = "40:4C:CA:40:5B:18"
M5_SERIAL = "0214228B"
FORBIDDEN_VENDORS = {"10c4", "1a86"}
FORBIDDEN_PATHS = {"/dev/ttyUSB0", "/dev/ttyUSB1"}

LOG_DIR = Path("/home/bot/fpga/blinky/esp32c6/logs")
CSV_PATH = LOG_DIR / "vindstyrka.csv"
RAW_PATH = LOG_DIR / "vindstyrka-reports.log"
STATE_PATH = LOG_DIR / "vindstyrka-state.json"
LOCK_PATH = LOG_DIR / "vindstyrka.lock"

ROW_INTERVAL_SEC = 30 * 60
REOPEN_WAIT_SEC = 2.0

# Linux tty modem-control ioctls. Both lines move in one TIOCMSET so the
# USB-JTAG peripheral never sees the DTR-low / RTS-high reset step.
TIOCMGET = getattr(termios, "TIOCMGET", 0x5415)
TIOCMSET = getattr(termios, "TIOCMSET", 0x5418)
TIOCEXCL = getattr(termios, "TIOCEXCL", 0x540C)
TIOCM_DTR = getattr(termios, "TIOCM_DTR", 0x002)
TIOCM_RTS = getattr(termios, "TIOCM_RTS", 0x004)

FIELDS = ("temperature_c", "humidity_pct", "pm25_ugm3", "voc_index")
HEADER = (
    "local_time",
    "temperature_c",
    "humidity_pct",
    "pm25_ugm3",
    "voc_index",
    "temperature_updated",
    "humidity_updated",
    "pm25_updated",
    "voc_updated",
)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
REPORTS = (
    (
        "temperature_c",
        re.compile(
            r"Temperature (-?\d+\.\d{2}) C \(measuredValue -?\d+\) "
            r"from 0x[0-9a-fA-F]+ via report$"
        ),
    ),
    (
        "humidity_pct",
        re.compile(
            r"Humidity (\d+\.\d{2}) % \(measuredValue \d+\) "
            r"from 0x[0-9a-fA-F]+ via report$"
        ),
    ),
    (
        "pm25_ugm3",
        re.compile(
            r"PM2\.5 (-?\d+\.\d{2}) ug/m3 \(bits 0x[0-9a-fA-F]+\) "
            r"from 0x[0-9a-fA-F]+ via report$"
        ),
    ),
    (
        "voc_index",
        re.compile(
            r"VOC index (-?\d+\.\d{2}) \(bits 0x[0-9a-fA-F]+\) "
            r"from 0x[0-9a-fA-F]+ via report$"
        ),
    ),
)
BOOT_MARKERS = (
    "ESP-ROM:",
    "boot: ESP-IDF",
    "cpu_start:",
    "VINDSTYRKA coordinator",
    "rst:0x",
    "waiting for download",
)

stop_requested = False


class NotC6(Exception):
    pass


def local_iso(when=None):
    if when is None:
        moment = datetime.now().astimezone()
    else:
        moment = datetime.fromtimestamp(when).astimezone()
    return moment.isoformat(timespec="seconds")


def log(msg):
    print(f"{local_iso()} {msg}", flush=True)


def blank_readings():
    return {name: {"value": "", "updated": ""} for name in FIELDS}


def strip_line(raw):
    text = raw.replace("\x00", "")
    text = ANSI_RE.sub("", text)
    return text.strip()


def parse_report(line):
    """Return (field, value) for a Zigbee report line, else None.

    Lines ending in 'via read' are the one-shot setup reads, not reports.
    """
    text = strip_line(line)
    if "via report" not in text:
        return None
    payload = text.split("VINDSTYRKA:", 1)[-1].strip()
    for field, pattern in REPORTS:
        match = pattern.search(payload)
        if match:
            return field, match.group(1)
    return None


def validate_c6(real_path, props):
    """Refuse anything that is not the C6 console. Does not open a port."""
    if real_path in FORBIDDEN_PATHS or real_path.startswith("/dev/ttyUSB"):
        raise NotC6(f"refusing {real_path}")
    if not real_path.startswith("/dev/ttyACM"):
        raise NotC6(f"refusing non-ACM path {real_path}")
    vendor = props.get("ID_VENDOR_ID", "")
    product = props.get("ID_MODEL_ID", "")
    serial = props.get("ID_SERIAL_SHORT", "")
    if serial == M5_SERIAL or vendor in FORBIDDEN_VENDORS:
        raise NotC6(f"refusing vendor {vendor} serial {serial}")
    if vendor != C6_VENDOR or product != C6_PRODUCT or serial != C6_SERIAL:
        raise NotC6(
            f"identity {vendor}:{product} serial {serial} is not the C6"
        )
    if props.get("ID_VENDOR") != "Espressif":
        raise NotC6(f"vendor name {props.get('ID_VENDOR')!r} is not Espressif")


def udev_props(path):
    out = subprocess.check_output(
        ["udevadm", "info", "-q", "property", "-n", path],
        text=True,
    )
    props = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return props


def resolve_c6():
    """Return the by-id path once its target is the C6. None if it is absent.

    Raises NotC6 when a node is present but it is the wrong device.
    """
    if not os.path.exists(BYID):
        return None
    real = os.path.realpath(BYID)
    props = udev_props(BYID)
    validate_c6(real, props)
    return BYID


def modem_bits(fd):
    raw = fcntl.ioctl(fd, TIOCMGET, struct.pack("I", 0))
    return struct.unpack("I", raw)[0]


def set_both_false(fd):
    flags = modem_bits(fd) & ~(TIOCM_DTR | TIOCM_RTS)
    fcntl.ioctl(fd, TIOCMSET, struct.pack("I", flags))


def lines_are_clear(fd):
    flags = modem_bits(fd)
    return (flags & (TIOCM_DTR | TIOCM_RTS)) == 0


def configure_tty(fd):
    attrs = termios.tcgetattr(fd)
    attrs[tty.IFLAG] = 0
    attrs[tty.OFLAG] = 0
    attrs[tty.LFLAG] = 0
    cflag = attrs[tty.CFLAG]
    cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.HUPCL)
    if hasattr(termios, "CRTSCTS"):
        cflag &= ~termios.CRTSCTS
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[tty.CFLAG] = cflag
    attrs[tty.ISPEED] = termios.B115200
    attrs[tty.OSPEED] = termios.B115200
    # VMIN 1 + O_NONBLOCK: a second read with no bytes returns EAGAIN.
    # VMIN 0 makes that read return b"" which is not a disconnect.
    attrs[tty.CC][termios.VMIN] = 1
    attrs[tty.CC][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def open_c6(path):
    """Open path with DTR and RTS cleared. Caller has already validated path."""
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        try:
            fcntl.ioctl(fd, TIOCEXCL)
        except OSError as exc:
            log(f"TIOCEXCL failed: {exc}")
        set_both_false(fd)
        configure_tty(fd)
        set_both_false(fd)
        if not lines_are_clear(fd):
            set_both_false(fd)
        flags = modem_bits(fd)
        dtr = 1 if flags & TIOCM_DTR else 0
        rts = 1 if flags & TIOCM_RTS else 0
        log(f"opened {path} -> {os.path.realpath(path)} dtr={dtr} rts={rts}")
        if dtr or rts:
            log("WARNING DTR or RTS is still set after open")
        return fd
    except Exception:
        try:
            set_both_false(fd)
        except OSError:
            pass
        os.close(fd)
        raise


def close_c6(fd):
    if fd is None:
        return
    try:
        set_both_false(fd)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def initial_deadline(now, existing):
    if existing is None:
        return now + ROW_INTERVAL_SEC
    if existing > now + ROW_INTERVAL_SEC + 120:
        return now + ROW_INTERVAL_SEC
    return existing


def row_due(now, deadline):
    """Return (new_deadline, should_write). At most one row per call."""
    if now < deadline:
        return deadline, False
    nxt = deadline + ROW_INTERVAL_SEC
    if nxt <= now:
        nxt = now + ROW_INTERVAL_SEC
    return nxt, True


def load_state(now):
    readings = blank_readings()
    deadline = None
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            saved = data.get("readings") or {}
            for name in FIELDS:
                item = saved.get(name) or {}
                value = item.get("value") or ""
                updated = item.get("updated") or ""
                if value and updated:
                    readings[name] = {"value": str(value), "updated": str(updated)}
            raw_deadline = data.get("next_row_unix")
            if isinstance(raw_deadline, (int, float)):
                deadline = float(raw_deadline)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            log(f"ignoring unreadable state file: {exc}")
            deadline = None
    deadline = initial_deadline(now, deadline)
    return readings, deadline


def save_state(readings, deadline):
    payload = {
        "next_row_unix": deadline,
        "next_row_local": local_iso(deadline),
        "readings": readings,
    }
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def append_csv(readings, when_iso, path=CSV_PATH):
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(HEADER)
        writer.writerow(
            [when_iso]
            + [readings[name]["value"] for name in FIELDS]
            + [readings[name]["updated"] for name in FIELDS]
        )
        handle.flush()
        os.fsync(handle.fileno())


def append_raw(when_iso, line, path=RAW_PATH):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{when_iso}\t{line}\n")
        handle.flush()
        os.fsync(handle.fileno())


def note_boot(line):
    for marker in BOOT_MARKERS:
        if marker in line:
            log(f"WARNING console line looks like a reset: {line}")
            return


def apply_report(readings, line, when_iso):
    parsed = parse_report(line)
    if parsed is None:
        note_boot(line)
        return False
    field, value = parsed
    readings[field] = {"value": value, "updated": when_iso}
    append_raw(when_iso, strip_line(line))
    return True


def acquire_lock():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            log("lock is already held; exiting without opening a port")
            return None
        raise
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def handle_stop(signum, _frame):
    global stop_requested
    stop_requested = True
    log(f"signal {signum}, closing the port")


def port_gone(opened_real):
    if not os.path.exists(BYID):
        return True
    try:
        return os.path.realpath(BYID) != opened_real
    except OSError:
        return True


def read_available(fd, readings):
    changed = False
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                break
            raise
        if chunk == b"":
            # No bytes queued. The C6 console stays up; only a real errno
            # or a missing by-id node means the cable was replugged.
            break
        read_available.buf += chunk
        while b"\n" in read_available.buf:
            raw, read_available.buf = read_available.buf.split(b"\n", 1)
            line = raw.decode("utf-8", errors="replace")
            if apply_report(readings, line, local_iso()):
                changed = True
        if len(read_available.buf) > 16384:
            read_available.buf = read_available.buf[-4096:]
    return changed


read_available.buf = b""


def service_loop(readings, deadline, lock_fd):
    fd = None
    opened_real = None
    last_absent_log = 0.0
    while not stop_requested:
        now = time.time()
        deadline, due = row_due(now, deadline)
        if due:
            when = local_iso()
            append_csv(readings, when)
            save_state(readings, deadline)
            log(f"wrote {CSV_PATH} at {when}; next row {local_iso(deadline)}")
            continue

        if fd is None:
            try:
                path = resolve_c6()
            except (NotC6, subprocess.CalledProcessError, OSError) as exc:
                log(f"not opening a port: {exc}")
                time.sleep(REOPEN_WAIT_SEC)
                continue
            if path is None:
                if now - last_absent_log >= 30:
                    log("C6 port is absent; waiting to reopen")
                    last_absent_log = now
                time.sleep(REOPEN_WAIT_SEC)
                continue
            try:
                log(f"opening {path} with DTR and RTS clear")
                fd = open_c6(path)
                opened_real = os.path.realpath(path)
                read_available.buf = b""
            except OSError as exc:
                log(f"open failed: {exc}; waiting")
                fd = None
                time.sleep(REOPEN_WAIT_SEC)
            continue

        if port_gone(opened_real):
            log("C6 port disappeared; closing and waiting to reopen")
            close_c6(fd)
            fd = None
            opened_real = None
            time.sleep(REOPEN_WAIT_SEC)
            continue

        timeout = max(0.05, min(1.0, deadline - time.time()))
        try:
            readable, _, _ = select.select([fd], [], [], timeout)
        except (OSError, ValueError) as exc:
            log(f"select failed: {exc}; reopening later")
            close_c6(fd)
            fd = None
            continue
        if not readable:
            continue
        try:
            if read_available(fd, readings):
                save_state(readings, deadline)
        except OSError as exc:
            if exc.errno not in (
                errno.EIO,
                errno.ENODEV,
                errno.ENXIO,
                errno.EBADF,
                errno.ECONNRESET,
            ):
                log(f"read error {exc}; keeping the port open")
                time.sleep(REOPEN_WAIT_SEC)
                continue
            save_state(readings, deadline)
            log(f"read failed: {exc}; waiting to reopen")
            close_c6(fd)
            fd = None
            opened_real = None
            time.sleep(REOPEN_WAIT_SEC)

    close_c6(fd)
    os.close(lock_fd)


def run_service():
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    lock_fd = acquire_lock()
    if lock_fd is None:
        return 0
    os.chdir(LOG_DIR)
    now = time.time()
    readings, deadline = load_state(now)
    save_state(readings, deadline)
    log(
        f"pid {os.getpid()} logging to {CSV_PATH}; "
        f"first row at {local_iso(deadline)}"
    )
    try:
        service_loop(readings, deadline, lock_fd)
    except Exception:
        log(traceback.format_exc().rstrip())
        return 1
    log("stopped")
    return 0


def self_test():
    samples = [
        "I (42163) VINDSTYRKA: Temperature 27.00 C (measuredValue 2700) from 0x677c via report",
        "I (43193) VINDSTYRKA: Humidity 41.00 % (measuredValue 4100) from 0x677c via report",
        "I (43213) VINDSTYRKA: PM2.5 1.00 ug/m3 (bits 0x3f800000) from 0x677c via report",
        "I (207743) VINDSTYRKA: VOC index 102.00 (bits 0x42cc0000) from 0x677c via report",
        "I (44263) VINDSTYRKA: Temperature 19.00 C (measuredValue 1900) from 0x677c via read",
        "\x1b[0;32mI (1) VINDSTYRKA: Temperature -1.50 C (measuredValue -150) from 0x677c via report\x1b[0m",
        "I (1) VINDSTYRKA: Temperature invalid (measuredValue -32768) from 0x677c via report",
        "I (2) VINDSTYRKA: Humidity 100.00 % (measuredValue 10000) from 0x0001 via report",
    ]
    readings = blank_readings()
    parsed = [parse_report(sample) for sample in samples]
    assert parsed[0] == ("temperature_c", "27.00")
    assert parsed[1] == ("humidity_pct", "41.00")
    assert parsed[2] == ("pm25_ugm3", "1.00")
    assert parsed[3] == ("voc_index", "102.00")
    assert parsed[4] is None
    assert parsed[5] == ("temperature_c", "-1.50")
    assert parsed[6] is None
    assert parsed[7] == ("humidity_pct", "100.00")
    for sample, item in zip(samples, parsed):
        if item is None:
            continue
        field, value = item
        readings[field] = {"value": value, "updated": "t"}
    assert readings["temperature_c"]["value"] == "-1.50"
    assert readings["humidity_pct"]["value"] == "100.00"
    assert readings["pm25_ugm3"]["value"] == "1.00"
    assert readings["voc_index"]["value"] == "102.00"

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "vindstyrka.csv"
        raw_path = Path(tmp) / "vindstyrka-reports.log"
        append_csv(readings, "2026-11-12T23:50:00+01:00", csv_path)
        append_csv(readings, "2026-11-13T00:20:00+01:00", csv_path)
        append_raw("2026-11-12T23:50:00+01:00", samples[0], raw_path)
        text = csv_path.read_text(encoding="utf-8").splitlines()
        assert text[0].split(",") == list(HEADER)
        assert text[1].startswith("2026-11-12T23:50:00+01:00,-1.50,100.00,1.00,102.00,")
        assert len(text) == 3
        assert "via report" in raw_path.read_text(encoding="utf-8")

    good = {
        "ID_VENDOR_ID": C6_VENDOR,
        "ID_MODEL_ID": C6_PRODUCT,
        "ID_SERIAL_SHORT": C6_SERIAL,
        "ID_VENDOR": "Espressif",
    }
    validate_c6("/dev/ttyACM0", good)
    for path, props in (
        ("/dev/ttyUSB0", good),
        ("/dev/ttyUSB1", good),
        ("/dev/ttyACM0", {**good, "ID_SERIAL_SHORT": M5_SERIAL}),
        ("/dev/ttyACM0", {**good, "ID_VENDOR_ID": "10c4"}),
        ("/dev/ttyACM0", {**good, "ID_VENDOR_ID": "1a86"}),
        ("/dev/ttyS0", good),
    ):
        try:
            validate_c6(path, props)
        except NotC6:
            pass
        else:
            raise AssertionError(f"accepted {path} {props}")

    now = 1_000_000.0
    assert initial_deadline(now, None) == now + ROW_INTERVAL_SEC
    assert row_due(now, now + 10) == (now + 10, False)
    assert row_due(now + ROW_INTERVAL_SEC, now)[1] is True
    late_deadline, write = row_due(now + 5 * ROW_INTERVAL_SEC, now)
    assert write is True
    assert late_deadline == now + 5 * ROW_INTERVAL_SEC + ROW_INTERVAL_SEC
    print("self-test ok")
    return 0


def check_port():
    path = resolve_c6()
    if path is None:
        print("absent")
        return 1
    real = os.path.realpath(path)
    props = udev_props(path)
    print(
        f"{path} -> {real} "
        f"{props.get('ID_VENDOR_ID')}:{props.get('ID_MODEL_ID')} "
        f"{props.get('ID_SERIAL_SHORT')}"
    )
    return 0


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) == 2 and sys.argv[1] == "--check-port":
        return check_port()
    if len(sys.argv) != 1:
        print("usage: overnight_log.py [--self-test|--check-port]", file=sys.stderr)
        return 2
    return run_service()


if __name__ == "__main__":
    sys.exit(main())
