#!/usr/bin/env python3
"""Toggle the PWR LED on space, and scan for keyboards from the built-in one.

Space (press only) on the Pi 400 keyboard or on B.O.W toggles the PWR LED.
A press on the built-in keyboard also runs a short bluetoothctl scan and will
pair a new device only when it is named B.O.W or is a HID keyboard.
On SIGINT, SIGTERM, and normal exit, the LED trigger and brightness go back.
"""

import errno
import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime

EV_KEY = 0x01
KEY_SPACE = 57
EVENT = struct.Struct("llHHi")

EVIOCGID = 0x80084502
EVIOCGNAME = 0x81004506
EVIOCGPHYS = 0x81004507
EVIOCGUNIQ = 0x81004508

KEYBOARD_NAME = "Raspberry Pi Internal Keyboard"
KEYBOARD_VENDOR = 0x04D9
KEYBOARD_PRODUCT = 0x0007

BOW_NAME = "B.O.W"
BOW_MAC = "11:22:34:44:5B:F3"
SCAN_SECONDS = 12
SCAN_LOG = "/home/bot/bt-scan.log"
HID_UUIDS = {
    "00001124-0000-1000-8000-00805f9b34fb",
    "00001812-0000-1000-8000-00805f9b34fb",
}

PWR_LED = "/sys/class/leds/PWR"
CAPS_LED = "/sys/class/leds/input0::capslock"

_stop = False
_state = threading.Condition()
_scan_requests = 0
_bow_present = True
_next_reconnect = 0.0
_extra_lock = threading.Lock()
_extra_macs = set()
_extra_names = set()
_log_lock = threading.Lock()
_bt_proc = None
_bt_session = None


def _request_stop(_signum, _frame):
    global _stop
    _stop = True


def read_sysfs(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        data = os.read(fd, 4096)
    finally:
        os.close(fd)
    return data.decode("ascii", "replace")


def write_sysfs(path, text):
    data = str(text).encode("ascii")
    fd = os.open(path, os.O_WRONLY | os.O_CLOEXEC)
    try:
        written = os.write(fd, data)
    finally:
        os.close(fd)
    if written != len(data):
        raise OSError(errno.EIO, f"short write ({written}/{len(data)})", path)


def active_trigger(text):
    for part in text.split():
        if part.startswith("[") and part.endswith("]") and len(part) > 2:
            return part[1:-1]
    raise OSError(errno.EINVAL, f"no active trigger in {text!r}")


def led_writable(base):
    brightness = os.path.join(base, "brightness")
    trigger = os.path.join(base, "trigger")
    return os.access(brightness, os.W_OK) and os.access(trigger, os.W_OK)


class Led:
    def __init__(self):
        if led_writable(PWR_LED):
            self.base = PWR_LED
        elif led_writable(CAPS_LED):
            self.base = CAPS_LED
        else:
            fd = os.open(os.path.join(PWR_LED, "brightness"), os.O_WRONLY | os.O_CLOEXEC)
            os.close(fd)
            raise OSError(
                errno.EACCES,
                "LED brightness and trigger are not writable",
                PWR_LED,
            )
        self.brightness_path = os.path.join(self.base, "brightness")
        self.trigger_path = os.path.join(self.base, "trigger")
        self.orig_trigger = active_trigger(read_sysfs(self.trigger_path))
        self.orig_brightness = read_sysfs(self.brightness_path).strip()
        self._changed = False
        try:
            self._take_manual_control()
        except Exception as original:
            try:
                self.restore()
            except Exception as restore_error:
                raise restore_error from original
            raise

    def _take_manual_control(self):
        write_sysfs(self.trigger_path, "none")
        self._changed = True
        now = active_trigger(read_sysfs(self.trigger_path))
        if now != "none":
            raise OSError(
                errno.EIO,
                f"trigger still {now!r} after writing none",
                self.trigger_path,
            )
        # Changing the trigger drops the level. Write the level we found
        # so the LED stays as it was until a space press.
        write_sysfs(self.brightness_path, self.orig_brightness)
        self.on = read_sysfs(self.brightness_path).strip() != "0"

    def toggle(self):
        write_sysfs(self.brightness_path, "0" if self.on else "1")
        self.on = read_sysfs(self.brightness_path).strip() != "0"
        state = "on" if self.on else "off"
        print(f"space {state}", flush=True)
        return state

    def restore(self):
        if not self._changed:
            return
        self._changed = False
        errors = []
        try:
            write_sysfs(self.brightness_path, self.orig_brightness)
        except OSError as exc:
            errors.append(exc)
        try:
            write_sysfs(self.trigger_path, self.orig_trigger)
        except OSError as exc:
            errors.append(exc)
        if not errors:
            return
        if len(errors) == 1:
            raise errors[0]
        detail = "; ".join(str(exc) for exc in errors)
        raise OSError(errors[0].errno, detail, self.base)


def _ioctl_string(fd, request):
    raw = fcntl.ioctl(fd, request, b"\x00" * 256)
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


def has_key_code(base, code):
    key_path = os.path.join(base, "capabilities/key")
    if not os.path.isfile(key_path):
        return False
    words = read_sysfs(key_path).split()
    try:
        values = [int(word, 16) for word in words]
    except ValueError:
        return False
    values.reverse()
    index = code // 64
    if index >= len(values):
        return False
    return bool(values[index] & (1 << (code % 64)))


def _event_nodes(base):
    events = sorted(
        entry
        for entry in os.listdir(base)
        if entry.startswith("event") and os.path.isdir(os.path.join(base, entry))
    )
    return [os.path.join("/dev/input", entry) for entry in events]


def find_keyboard():
    matches = []
    root = "/sys/class/input"
    for node in sorted(os.listdir(root)):
        if not node.startswith("input"):
            continue
        base = os.path.join(root, node)
        name_path = os.path.join(base, "name")
        if not os.path.isfile(name_path):
            continue
        name = read_sysfs(name_path).strip()
        if name != KEYBOARD_NAME:
            continue
        vendor = int(read_sysfs(os.path.join(base, "id/vendor")), 16)
        product = int(read_sysfs(os.path.join(base, "id/product")), 16)
        phys = read_sysfs(os.path.join(base, "phys")).strip()
        if vendor != KEYBOARD_VENDOR or product != KEYBOARD_PRODUCT:
            continue
        if not phys.endswith("/input0"):
            continue
        events = _event_nodes(base)
        if len(events) != 1:
            raise OSError(errno.ENODEV, f"{node} event nodes {events}", base)
        matches.append(events[0])
    if len(matches) != 1:
        raise OSError(
            errno.ENODEV,
            f"expected one {KEYBOARD_NAME} 04d9:0007 input0, found {matches}",
            root,
        )
    return matches[0]


def tracked_role(name, uniq):
    """bow, paired, or None. B.O.W is the known folding keyboard."""
    if name == BOW_NAME or (uniq and uniq.lower() == BOW_MAC.lower()):
        return "bow"
    with _extra_lock:
        if uniq and uniq.upper() in _extra_macs:
            return "paired"
        if name and name in _extra_names:
            return "paired"
    return None


def remember_keyboard(mac, name):
    with _extra_lock:
        if mac:
            _extra_macs.add(mac.upper())
        if name and name != BOW_NAME:
            _extra_names.add(name)


def find_bow_events():
    """(path, role) for B.O.W and keyboards paired this session, after hot-plug."""
    found = []
    root = "/sys/class/input"
    if not os.path.isdir(root):
        return found
    for node in sorted(os.listdir(root)):
        if not node.startswith("input"):
            continue
        base = os.path.join(root, node)
        name_path = os.path.join(base, "name")
        if not os.path.isfile(name_path):
            continue
        name = read_sysfs(name_path).strip()
        uniq_path = os.path.join(base, "uniq")
        uniq = read_sysfs(uniq_path).strip() if os.path.isfile(uniq_path) else ""
        role = tracked_role(name, uniq)
        if role is None or not has_key_code(base, KEY_SPACE):
            continue
        for path in _event_nodes(base):
            found.append((path, role))
    return found


def open_input(path, role):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        name = _ioctl_string(fd, EVIOCGNAME).strip()
        phys = _ioctl_string(fd, EVIOCGPHYS).strip()
        try:
            uniq = _ioctl_string(fd, EVIOCGUNIQ).strip()
        except OSError:
            uniq = ""
        if role == "internal":
            ident = fcntl.ioctl(fd, EVIOCGID, b"\x00" * 8)
            _bustype, vendor, product, _version = struct.unpack_from("HHHH", ident)
            if (
                name != KEYBOARD_NAME
                or vendor != KEYBOARD_VENDOR
                or product != KEYBOARD_PRODUCT
                or not phys.endswith("/input0")
            ):
                raise OSError(
                    errno.ENODEV,
                    f"refusing {path}: name={name!r} id={vendor:04x}:{product:04x} phys={phys!r}",
                    path,
                )
        elif tracked_role(name, uniq) is None:
            raise OSError(
                errno.ENODEV,
                f"refusing {path}: name={name!r} uniq={uniq!r}",
                path,
            )
    except Exception:
        os.close(fd)
        raise
    return fd


class KeyboardWatch:
    def __init__(self):
        self.fds = {}

    def paths(self):
        return {path for _fd, (path, _role) in self.fds.items()}

    def close_fd(self, fd):
        path, _role = self.fds.pop(fd, (None, None))
        try:
            os.close(fd)
        except OSError:
            pass
        if path:
            print(f"closed {path}", file=sys.stderr, flush=True)

    def close_all(self):
        for fd in list(self.fds):
            self.close_fd(fd)

    def refresh(self):
        internal = find_keyboard()
        wanted = [(internal, "internal")]
        for path, role in find_bow_events():
            if path != internal:
                wanted.append((path, role))
        want_paths = {path for path, _role in wanted}
        for fd, (path, _role) in list(self.fds.items()):
            if path not in want_paths or not os.path.exists(path):
                self.close_fd(fd)
        open_paths = self.paths()
        for path, role in wanted:
            if path in open_paths:
                continue
            try:
                fd = open_input(path, role)
            except OSError as exc:
                print(exc, file=sys.stderr, flush=True)
                if role == "internal":
                    raise
                continue
            self.fds[fd] = (path, role)
            print(f"listening {role} {path}", file=sys.stderr, flush=True)
        return internal


def handle_space(led):
    led.toggle()


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_log(line):
    if not line.endswith("\n"):
        line += "\n"
    with _log_lock:
        fd = os.open(
            SCAN_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC, 0o644
        )
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)


def prepend_log(text):
    if not text.endswith("\n"):
        text += "\n"
    blob = text.encode()
    with _log_lock:
        prev = b""
        if os.path.exists(SCAN_LOG):
            rfd = os.open(SCAN_LOG, os.O_RDONLY | os.O_CLOEXEC)
            try:
                chunks = []
                while True:
                    piece = os.read(rfd, 65536)
                    if not piece:
                        break
                    chunks.append(piece)
                prev = b"".join(chunks)
            finally:
                os.close(rfd)
        wfd = os.open(
            SCAN_LOG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC, 0o644
        )
        try:
            os.write(wfd, blob + prev)
        finally:
            os.close(wfd)


def one_line(text):
    flat = " ".join(text.split())
    if len(flat) > 2000:
        return flat[:2000] + "..."
    return flat


def set_bow_present(present):
    global _bow_present
    with _state:
        _bow_present = bool(present)
        _state.notify_all()


def request_scan():
    global _scan_requests
    with _state:
        _scan_requests += 1
        _state.notify_all()


def bow_nodes():
    return [path for path, role in find_bow_events() if role == "bow"]


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
NEW_RE = re.compile(
    r"\[NEW\] Device ([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s*(.*)$"
)
CHG_RE = re.compile(
    r"\[CHG\] Device ([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+([^:]+):\s*(.*)$"
)
INFO_DEV_RE = re.compile(r"^Device ([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b")
INFO_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 ]*):\s*(.*)$")
PROMPT_RE = re.compile(r"\]#\s*$")
SECRET_RE = re.compile(
    r"(?:PIN code:\s*([0-9A-Za-z]{1,16})"
    r"|Passkey(?:\s+Notify)?:\s*([0-9]{1,6})"
    r"|Confirm passkey\s+([0-9]{1,6}))",
    re.I,
)
ENTER_RE = re.compile(r"Enter (?:PIN code|passkey)", re.I)
YESNO_RE = re.compile(r"\(yes/no\):\s*$", re.I)
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

DIGITS = {
    "0": [" ### ", "#   #", "#   #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "    #", " ### ", "#    ", " ### "],
    "3": [" ### ", "    #", " ### ", "    #", " ### "],
    "4": ["#   #", "#   #", " ### ", "    #", "    #"],
    "5": [" ### ", "#    ", " ### ", "    #", " ### "],
    "6": [" ### ", "#    ", "#### ", "#   #", " ### "],
    "7": ["#####", "   # ", "  #  ", " #   ", "#    "],
    "8": [" ### ", "#   #", " ### ", "#   #", " ### "],
    "9": [" ### ", "#   #", " ####", "    #", " ### "],
    "?": [" ### ", "    #", "  ## ", "     ", "  #  "],
    " ": ["     ", "     ", "     ", "     ", "     "],
}


def big_text(text):
    rows = ["", "", "", "", ""]
    for char in text:
        glyph = DIGITS.get(char, DIGITS["?"])
        for index in range(5):
            rows[index] += glyph[index] + " "
    width = max(len(row) for row in rows)
    border = "#" * (width + 4)
    body = "\n".join("# " + row.ljust(width) + " #" for row in rows)
    return f"{border}\n{body}\n{border}\n"


def announce_pin(value):
    if value is None:
        shown = "??????"
        title = "PIN REQUIRED"
    else:
        shown = value.strip()
        if shown.isdigit():
            shown = shown.zfill(6)
        title = "PIN / PASSKEY"
    banner = (
        f"{title} {shown}\n{big_text(shown)}"
        "Type this on the keyboard if it asks.\n"
    )
    print("\n" + banner, flush=True)
    for path in ("/dev/console", "/dev/tty1"):
        try:
            real = os.path.realpath(path)
        except OSError:
            continue
        if os.path.basename(real) in {"ttyUSB0", "ttyACM0", "ttyUSB1"}:
            continue
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            os.write(fd, ("\n" + banner).encode())
        except OSError:
            pass
        finally:
            os.close(fd)
    try:
        prepend_log(banner)
    except OSError as exc:
        print(exc, file=sys.stderr, flush=True)


def parse_number(value):
    token = value.split()[0]
    try:
        if token.lower().startswith("0x"):
            return int(token, 16)
        return int(token, 10)
    except ValueError:
        return None


def blank_device(mac):
    return {
        "mac": mac.upper(),
        "name": "",
        "alias": "",
        "rssi": None,
        "class": None,
        "appearance": None,
        "icon": "",
        "paired": None,
        "trusted": None,
        "connected": None,
        "uuids": [],
    }


def apply_field(dev, key, value):
    key_l = key.lower()
    if key_l in ("name", "alias") and value:
        dev[key_l] = value
    elif key_l == "rssi":
        number = parse_number(value)
        if number is not None:
            dev["rssi"] = number
    elif key_l == "class":
        number = parse_number(value)
        if number is not None:
            dev["class"] = number
    elif key_l == "appearance":
        number = parse_number(value)
        if number is not None:
            dev["appearance"] = number
    elif key_l == "icon" and value:
        dev["icon"] = value
    elif key_l == "paired":
        dev["paired"] = value.split()[0].lower()
    elif key_l == "bonded" and value.split()[0].lower() == "yes":
        dev["paired"] = "yes"
    elif key_l == "trusted":
        dev["trusted"] = value.split()[0].lower()
    elif key_l == "connected":
        dev["connected"] = value.split()[0].lower()
    elif key_l in ("uuid", "uuids"):
        for uuid in UUID_RE.findall(value):
            lowered = uuid.lower()
            if lowered not in dev["uuids"]:
                dev["uuids"].append(lowered)


def ingest(text):
    devices = {}
    clean = ANSI_RE.sub("", text.replace("\r", ""))
    for line in clean.splitlines():
        line = line.strip()
        new = NEW_RE.search(line)
        if new:
            mac = new.group(1).upper()
            dev = devices.setdefault(mac, blank_device(mac))
            named = new.group(2).strip()
            if named:
                dev["name"] = named
            continue
        changed = CHG_RE.search(line)
        if not changed:
            continue
        mac = changed.group(1).upper()
        dev = devices.setdefault(mac, blank_device(mac))
        apply_field(dev, changed.group(2).strip(), changed.group(3).strip())
    return devices


def parse_info(text, dev):
    clean = ANSI_RE.sub("", text.replace("\r", ""))
    seen = False
    for line in clean.splitlines():
        line = line.strip()
        if INFO_DEV_RE.match(line):
            seen = True
            continue
        field = INFO_FIELD_RE.match(line)
        if seen and field:
            apply_field(dev, field.group(1).strip(), field.group(2).strip())
    return dev


def display_name(dev):
    return (dev.get("name") or dev.get("alias") or "").strip()


def classify(dev):
    keyboard = False
    hid = False
    cod = dev.get("class")
    if isinstance(cod, int) and ((cod >> 8) & 0x1F) == 0x05:
        hid = True
        if ((cod >> 6) & 0x03) in (1, 3):
            keyboard = True
    appearance = dev.get("appearance")
    if isinstance(appearance, int):
        if ((appearance >> 6) & 0x3FF) == 0x0F:
            hid = True
        if appearance == 0x03C1:
            keyboard = True
    icon = (dev.get("icon") or "").lower()
    if icon.startswith("input-"):
        hid = True
    if icon == "input-keyboard":
        keyboard = True
    for uuid in dev.get("uuids", ()):
        if str(uuid).lower() in HID_UUIDS:
            hid = True
    if display_name(dev) == BOW_NAME or dev["mac"].upper() == BOW_MAC:
        keyboard = True
    dev["keyboard"] = keyboard
    dev["hid"] = hid
    return keyboard, hid


def should_pair(dev):
    """New B.O.W or a HID keyboard. Never a mouse, headset, or other non-keyboard."""
    keyboard, hid = classify(dev)
    if not keyboard:
        return False
    if display_name(dev) == BOW_NAME or dev["mac"].upper() == BOW_MAC:
        return True
    return keyboard and hid


def format_device(dev):
    classify(dev)
    name = display_name(dev).replace("\\", "\\\\").replace('"', '\\"')
    rssi = "unknown" if dev.get("rssi") is None else str(dev["rssi"])
    if dev.get("class") is None:
        cod = "unknown"
    else:
        cod = f"0x{dev['class']:06x}"
    if dev.get("appearance") is None:
        appearance = "unknown"
    else:
        appearance = f"0x{dev['appearance']:04x}"
    return (
        f"{stamp()} mac={dev['mac']} name=\"{name}\" rssi={rssi} "
        f"class={cod} appearance={appearance} "
        f"keyboard={'yes' if dev.get('keyboard') else 'no'} "
        f"hid={'yes' if dev.get('hid') else 'no'}"
    )


def run_captured(args, timeout):
    global _bt_proc
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    os.set_blocking(proc.stdout.fileno(), False)
    with _state:
        _bt_proc = proc
    chunks = []
    deadline = time.monotonic() + timeout
    reason = ""
    try:
        while proc.poll() is None:
            if _stop:
                reason = "stopped"
                proc.terminate()
                break
            if time.monotonic() >= deadline:
                reason = "timed out"
                proc.terminate()
                break
            ready, _, _ = select.select([proc.stdout], [], [], 0.3)
            if not ready:
                continue
            piece = proc.stdout.read() or ""
            if piece:
                chunks.append(piece)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        rest = ""
        try:
            rest = proc.stdout.read() or ""
        except OSError:
            rest = ""
        if rest:
            chunks.append(rest)
        output = "".join(chunks)
        if reason:
            output = (output + "\n" + reason).strip()
        rc = proc.returncode if proc.returncode is not None else 1
        return rc, output
    finally:
        with _state:
            if _bt_proc is proc:
                _bt_proc = None
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


def failed_text(text):
    low = text.lower()
    return "failed to " in low or "org.bluez.error" in low or "timed out" in low


def succeeded(text, kind):
    low = text.lower()
    if failed_text(text):
        return False
    if kind == "pair":
        return "pairing successful" in low or "paired: yes" in low
    if kind == "trust":
        return "trust succeeded" in low or "trusted: yes" in low
    if kind == "connect":
        return (
            "connection successful" in low
            or "already connected" in low
            or "connected: yes" in low
        )
    return False


class AgentSession:
    """Interactive bluetoothctl so a passkey can be shown as soon as it appears."""

    def __init__(self):
        self.master, slave = pty.openpty()
        os.set_inheritable(self.master, False)
        self.proc = subprocess.Popen(
            ["/usr/bin/bluetoothctl", "--agent", "DisplayOnly"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        os.set_blocking(self.master, False)
        self.buf = ""
        self.announced = set()
        self.accept = False
        self.replied_at = None
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.proc.poll() is None:
            try:
                self._write("quit\n")
            except OSError:
                pass
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        try:
            os.close(self.master)
        except OSError:
            pass

    def _write(self, text):
        data = text.encode()
        while data and not _stop:
            try:
                written = os.write(self.master, data)
            except BlockingIOError:
                select.select([], [self.master], [], 0.2)
                continue
            except OSError:
                return
            data = data[written:]

    def pump(self, wait):
        try:
            ready, _, _ = select.select([self.master], [], [], wait)
        except OSError:
            return
        if not ready:
            return
        try:
            raw = os.read(self.master, 8192)
        except OSError:
            return
        if not raw:
            return
        text = ANSI_RE.sub("", raw.decode("utf-8", "replace").replace("\r", ""))
        self.buf += text
        self._watch()
        if len(self.buf) > 200000:
            self.buf = self.buf[-100000:]

    def _watch(self):
        for match in SECRET_RE.finditer(self.buf):
            value = next(group for group in match.groups() if group)
            if value in self.announced:
                continue
            self.announced.add(value)
            announce_pin(value)
        tail = self.buf[-240:]
        if ENTER_RE.search(tail) and "enter" not in self.announced:
            if not any(item.isdigit() for item in self.announced):
                self.announced.add("enter")
                announce_pin(None)
        if self.accept and YESNO_RE.search(tail) and self.replied_at != tail:
            self.replied_at = tail
            self._write("yes\n")

    def read_until(self, seconds, done):
        start = len(self.buf)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not _stop:
            self.pump(0.2)
            new = self.buf[start:]
            if done(new):
                return new
            if self.proc.poll() is not None:
                self.pump(0)
                return self.buf[start:]
        self.pump(0)
        return self.buf[start:]

    def command(self, line, seconds, kind):
        self.replied_at = None
        self._write(line + "\n")

        def done(text):
            if YESNO_RE.search(text[-100:]):
                return False
            if kind == "shell":
                return bool(PROMPT_RE.search(text))
            return succeeded(text, kind) or failed_text(text)

        return self.read_until(seconds, done)


def pair_trust_connect(dev):
    global _bt_session
    mac = dev["mac"]
    name = display_name(dev)
    session = AgentSession()
    _bt_session = session
    try:
        session.command("agent DisplayOnly", 5, "shell")
        session.command("default-agent", 5, "shell")
        session.accept = True
        paired = session.command("pair " + mac, 45, "pair")
        ok = succeeded(paired, "pair")
        append_log(
            f"{stamp()} action=pair mac={mac} ok={'yes' if ok else 'no'} "
            f"output={one_line(paired)}"
        )
        print(f"pair {mac} ok={ok}", file=sys.stderr, flush=True)
        if not ok:
            return
        remember_keyboard(mac, name)
        trusted = session.command("trust " + mac, 15, "trust")
        append_log(f"{stamp()} action=trust mac={mac} output={one_line(trusted)}")
        connected = session.command("connect " + mac, 25, "connect")
        append_log(f"{stamp()} action=connect mac={mac} output={one_line(connected)}")
    except OSError as exc:
        line = f"{stamp()} action=pair-error mac={mac} error={exc}"
        append_log(line)
        print(line, file=sys.stderr, flush=True)
    finally:
        session.accept = False
        session.close()
        if _bt_session is session:
            _bt_session = None


def enrich(dev):
    rc, output = run_captured(["/usr/bin/bluetoothctl", "info", dev["mac"]], 8)
    if rc != 0:
        dev["info_error"] = output.strip()
        append_log(
            f"{stamp()} action=info-error mac={dev['mac']} rc={rc} "
            f"output={one_line(output)}"
        )
        return
    parse_info(output, dev)


def scan_and_pair():
    append_log(f"{stamp()} action=scan-start seconds={SCAN_SECONDS}")
    print(f"bluetooth scan {SCAN_SECONDS}s", file=sys.stderr, flush=True)
    try:
        rc, output = run_captured(
            ["/usr/bin/bluetoothctl", "--timeout", str(SCAN_SECONDS), "scan", "on"],
            SCAN_SECONDS + 5,
        )
    except OSError as exc:
        line = f"{stamp()} action=scan-error error={exc}"
        append_log(line)
        print(line, file=sys.stderr, flush=True)
        return
    devices = ingest(output)
    scan_ok = rc == 0 and not failed_text(output)
    if not scan_ok:
        line = f"{stamp()} action=scan-error rc={rc} output={one_line(output)}"
        append_log(line)
        print(line, file=sys.stderr, flush=True)
    for dev in devices.values():
        if scan_ok and not _stop:
            try:
                enrich(dev)
            except OSError as exc:
                append_log(f"{stamp()} action=info-error mac={dev['mac']} error={exc}")
        classify(dev)
        append_log(format_device(dev))
        if not scan_ok or _stop or not should_pair(dev):
            continue
        if dev.get("paired") != "no":
            state = dev.get("paired")
            reason = "already-paired" if state == "yes" else "paired-state-unknown"
            append_log(f"{stamp()} action=skip mac={dev['mac']} reason={reason}")
            continue
        pair_trust_connect(dev)
    append_log(
        f"{stamp()} action=scan-end rc={rc} ok={'yes' if scan_ok else 'no'} "
        f"devices={len(devices)}"
    )


def reconnect_bow():
    if bow_nodes():
        return
    print(f"reconnecting {BOW_MAC}", file=sys.stderr, flush=True)
    try:
        rc, output = run_captured(
            ["/usr/bin/bluetoothctl", "--timeout", "12", "connect", BOW_MAC],
            16,
        )
    except OSError as exc:
        line = f"{stamp()} action=reconnect mac={BOW_MAC} ok=no error={exc}"
    else:
        ok = rc == 0 and not failed_text(output)
        line = (
            f"{stamp()} action=reconnect mac={BOW_MAC} ok={'yes' if ok else 'no'} "
            f"rc={rc} output={one_line(output)}"
        )
    append_log(line)
    print(line, file=sys.stderr, flush=True)


def bt_worker():
    global _next_reconnect, _scan_requests
    while not _stop:
        job = None
        with _state:
            if _scan_requests > 0:
                _scan_requests -= 1
                job = "scan"
            elif not _bow_present and time.monotonic() >= _next_reconnect:
                job = "reconnect"
            else:
                _state.wait(timeout=1.0)
                continue
        if _stop:
            break
        try:
            if job == "scan":
                scan_and_pair()
            elif job == "reconnect":
                reconnect_bow()
                with _state:
                    _next_reconnect = time.monotonic() + 20
        except Exception as exc:
            line = f"{stamp()} action=bluetoothctl-error error={exc!r}"
            try:
                append_log(line)
            except OSError:
                pass
            print(line, file=sys.stderr, flush=True)


def _drain(fd):
    try:
        while os.read(fd, 256):
            pass
    except OSError as exc:
        if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
            raise


def run(watch, led, wake_r=None):
    # select() retries when a signal handler does not raise. The wake pipe
    # is registered with signal.set_wakeup_fd so SIGINT/SIGTERM make it readable.
    bufs = {}
    size = EVENT.size
    while not _stop:
        try:
            watch.refresh()
        except OSError as exc:
            print(exc, file=sys.stderr, flush=True)
            if not watch.fds:
                set_bow_present(False)
                time.sleep(1)
                continue
        set_bow_present(any(role == "bow" for _path, role in watch.fds.values()))
        fds = list(watch.fds)
        watch_list = list(fds)
        if wake_r is not None:
            watch_list.append(wake_r)
        try:
            ready, _, _ = select.select(watch_list, [], [], 1.0)
        except InterruptedError:
            continue
        except OSError as exc:
            if exc.errno == errno.EBADF:
                for fd in list(watch.fds):
                    if not os.path.exists(watch.fds[fd][0]):
                        bufs.pop(fd, None)
                        watch.close_fd(fd)
                continue
            raise
        if wake_r is not None and wake_r in ready:
            _drain(wake_r)
            return
        for fd in ready:
            if fd == wake_r or fd not in watch.fds:
                continue
            path, role = watch.fds[fd]
            try:
                chunk = os.read(fd, size * 64)
            except InterruptedError:
                continue
            except OSError as exc:
                if exc.errno in (errno.EINTR, errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                if exc.errno in (errno.ENODEV, errno.EBADF):
                    bufs.pop(fd, None)
                    watch.close_fd(fd)
                    continue
                raise
            if not chunk:
                bufs.pop(fd, None)
                watch.close_fd(fd)
                continue
            buf = bufs.get(fd, b"") + chunk
            while len(buf) >= size:
                _sec, _usec, ev_type, code, value = EVENT.unpack_from(buf)
                buf = buf[size:]
                if ev_type == EV_KEY and code == KEY_SPACE and value == 1:
                    handle_space(led)
                    print(f"from {path}", flush=True)
                    if role == "internal":
                        request_scan()
            bufs[fd] = buf


def main():
    global _stop, _next_reconnect
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)
    # The C signal handler writes one byte here, which unblocks select.
    old_wake = signal.set_wakeup_fd(wake_w)
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    led = None
    watch = KeyboardWatch()
    worker = None
    try:
        led = Led()
        internal = watch.refresh()
        set_bow_present(any(role == "bow" for _path, role in watch.fds.values()))
        _next_reconnect = time.monotonic() + 2
        bow = [path for path, role in watch.fds.values() if role == "bow"]
        print(
            f"led {led.base} keyboard {internal} bow {','.join(bow) if bow else 'waiting'} "
            f"scanlog {SCAN_LOG}",
            file=sys.stderr,
            flush=True,
        )
        worker = threading.Thread(target=bt_worker, name="bt-scan", daemon=False)
        worker.start()
        run(watch, led, wake_r)
    finally:
        _stop = True
        with _state:
            _state.notify_all()
            proc = _bt_proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if _bt_session is not None:
            _bt_session.close()
        if worker is not None:
            worker.join(timeout=8)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if led is not None:
                led.restore()
        finally:
            signal.set_wakeup_fd(old_wake)
            os.close(wake_r)
            os.close(wake_w)
            watch.close_all()


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
