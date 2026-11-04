"""V4L2 camera controls, persisted settings, and JPEG exposure metrics.

Used by the webcam MCP. Does not import mcp, so unit tests can run without
the server extra. Does not touch FPGA, serial ports, or openFPGALoader.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_DEVICE = os.environ.get("WEBCAM_MCP_DEVICE", "/dev/video0")
V4L2_TIMEOUT_S = 8.0

CONTROL_ALIASES = {
    "exposure": "exposure_time_absolute",
    "ae": "auto_exposure",
    "white_balance": "white_balance_temperature",
    "wb": "white_balance_automatic",
    "awb": "white_balance_automatic",
}

# Setting these requires the matching auto control to be off/manual.
GATED_BY = {
    "exposure_time_absolute": ("auto_exposure", 1),  # 1 = Manual Mode on this Logitech
    "white_balance_temperature": ("white_balance_automatic", 0),
}

CTRL_LINE_RE = re.compile(
    r"^\s{2,}(?P<name>[a-z0-9_]+)\s+0x[0-9a-fA-F]+\s+\((?P<type>\w+)\)\s*:\s*(?P<rest>.*)$"
)
MENU_LINE_RE = re.compile(r"^\s+(\d+):\s+(.*)$")
INT_RE = re.compile(r"^-?\d+$")

TARGET_MEAN = 115.0
MEAN_LOW = 85.0
MEAN_HIGH = 145.0
CLIP_HI_MAX = 0.02
CLIP_LO_MAX = 0.50  # dark-room FPGA desks have lots of near-black; do not chase this
CLIP_HI_LUMA = 250.0
CLIP_LO_LUMA = 5.0


def state_path() -> Path:
    override = os.environ.get("WEBCAM_MCP_STATE_DIR")
    if override:
        root = Path(override)
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        root = Path(xdg) / "webcam-mcp" if xdg else Path.home() / ".local/state/webcam-mcp"
    return root / "controls.json"


def canonical_control_name(name: str) -> str:
    key = name.strip()
    return CONTROL_ALIASES.get(key, key)


def parse_v4l2_ctrls(text: str) -> list[dict[str, Any]]:
    """Parse `v4l2-ctl --list-ctrls-menus` (or `--list-ctrls`) stdout."""
    controls: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        menu = MENU_LINE_RE.match(raw_line)
        if menu and current is not None:
            current.setdefault("menu", {})[int(menu.group(1))] = menu.group(2).strip()
            continue
        match = CTRL_LINE_RE.match(raw_line)
        if not match:
            continue
        current = {
            "name": match.group("name"),
            "type": match.group("type"),
        }
        rest = match.group("rest").strip()
        flags: list[str] = []
        if "flags=" in rest:
            head, flag_text = rest.split("flags=", 1)
            rest = head.strip()
            flags = [part.strip() for part in flag_text.split(",") if part.strip()]
        # value may be `3 (Aperture Priority Mode)`
        value_label: str | None = None
        value_match = re.search(r"\bvalue=(\S+)(?:\s+\(([^)]*)\))?", rest)
        if value_match:
            raw_val = value_match.group(1)
            current["value"] = _coerce_ctrl_value(raw_val)
            if value_match.group(2):
                value_label = value_match.group(2)
            rest = (rest[: value_match.start()] + rest[value_match.end() :]).strip()
        for token in rest.split():
            if "=" not in token:
                continue
            key, raw_val = token.split("=", 1)
            current[key] = _coerce_ctrl_value(raw_val)
        if flags:
            current["flags"] = flags
            current["inactive"] = "inactive" in flags
        else:
            current["inactive"] = False
        if value_label:
            current["value_label"] = value_label
        for needed in ("min", "max", "step", "default"):
            current.setdefault(needed, None)
        controls.append(current)
    return controls


def _coerce_ctrl_value(raw: str) -> int | str:
    if INT_RE.match(raw):
        return int(raw)
    return raw


def controls_by_name(controls: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in controls}


def clamp_value(ctrl: dict[str, Any], value: int) -> int:
    lo = ctrl.get("min")
    hi = ctrl.get("max")
    step = ctrl.get("step")
    if not isinstance(step, int) or step <= 0:
        step = 1
    v = int(value)
    if isinstance(lo, int) and isinstance(hi, int):
        v = max(lo, min(hi, v))
        v = lo + ((v - lo) // step) * step
        v = max(lo, min(hi, v))
    return v


def set_order(updates: dict[str, int]) -> list[tuple[str, int]]:
    """Autos that disable dependents first, then values, then autos that enable."""
    first: list[tuple[str, int]] = []
    middle: list[tuple[str, int]] = []
    last: list[tuple[str, int]] = []
    for name, value in updates.items():
        if name == "auto_exposure":
            (first if value == 1 else last).append((name, value))
        elif name == "white_balance_automatic":
            (first if value == 0 else last).append((name, value))
        else:
            middle.append((name, value))
    return first + middle + last


def expand_gated_updates(updates: dict[str, int]) -> dict[str, int]:
    """If a gated control is set without its auto counterpart, turn auto off/manual.

    A full driver-default snapshot includes both auto_exposure=3 and
    exposure_time_absolute=166; do not force manual in that case.
    """
    out = dict(updates)
    for name, (gate, required) in GATED_BY.items():
        if name in out and gate not in out:
            out[gate] = required
    return out


def settable_updates(updates: dict[str, int]) -> dict[str, int]:
    """Drop dependents that stay inactive while their auto control is on."""
    out = dict(updates)
    if out.get("auto_exposure", 1) != 1:
        out.pop("exposure_time_absolute", None)
    if out.get("white_balance_automatic", 1) != 0:
        out.pop("white_balance_temperature", None)
    return out


def run_v4l2(args: list[str], what: str) -> str:
    cmd = ["v4l2-ctl", *args]
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=V4L2_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("v4l2-ctl is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"v4l2-ctl {what} timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"v4l2-ctl {what} failed: {detail}") from exc
    return (proc.stdout or "") + (proc.stderr or "")


def list_device_controls(device: str) -> list[dict[str, Any]]:
    text = run_v4l2(["-d", device, "--list-ctrls-menus"], "list-ctrls")
    controls = parse_v4l2_ctrls(text)
    if not controls:
        raise RuntimeError(f"no V4L2 controls reported for {device}")
    return controls


def apply_control_updates(device: str, updates: dict[str, int]) -> dict[str, int]:
    """Set controls in an order that respects auto-exposure / AWB gates."""
    updates = settable_updates(expand_gated_updates(updates))
    if not updates:
        return {}
    applied: dict[str, int] = {}
    for name, value in set_order(updates):
        run_v4l2(["-d", device, "--set-ctrl", f"{name}={value}"], f"set {name}")
        applied[name] = value
    return applied


def driver_defaults(controls: list[dict[str, Any]]) -> dict[str, int]:
    defaults: dict[str, int] = {}
    for ctrl in controls:
        default = ctrl.get("default")
        if isinstance(default, int):
            defaults[ctrl["name"]] = default
    return defaults


def current_values(controls: list[dict[str, Any]]) -> dict[str, int]:
    values: dict[str, int] = {}
    for ctrl in controls:
        value = ctrl.get("value")
        if isinstance(value, int):
            values[ctrl["name"]] = value
    return values


def load_saved_controls() -> dict[str, dict[str, int]]:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for device, controls in data.items():
        if not isinstance(device, str) or not isinstance(controls, dict):
            continue
        cleaned: dict[str, int] = {}
        for name, value in controls.items():
            if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool):
                cleaned[canonical_control_name(name)] = value
        if cleaned:
            out[device] = cleaned
    return out


def save_device_controls(device: str, controls: dict[str, int] | None) -> Path:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_saved_controls()
    if controls is None:
        data.pop(device, None)
    else:
        data[device] = dict(controls)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def apply_saved_controls(device: str) -> dict[str, int]:
    saved = load_saved_controls().get(device)
    if not saved:
        return {}
    known = controls_by_name(list_device_controls(device))
    filtered: dict[str, int] = {}
    for name, value in saved.items():
        ctrl = known.get(name)
        if ctrl is None:
            continue
        filtered[name] = clamp_value(ctrl, value)
    if not filtered:
        return {}
    return apply_control_updates(device, expand_gated_updates(filtered))


def resolve_updates(
    requested: dict[str, int | None],
    known: dict[str, dict[str, Any]],
) -> dict[str, int]:
    updates: dict[str, int] = {}
    unknown: list[str] = []
    for raw_name, raw_value in requested.items():
        if raw_value is None:
            continue
        name = canonical_control_name(raw_name)
        ctrl = known.get(name)
        if ctrl is None:
            unknown.append(raw_name)
            continue
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            raise ValueError(f"{name} must be an int, not {raw_value!r}")
        updates[name] = clamp_value(ctrl, raw_value)
    if unknown:
        raise ValueError(
            "unknown control(s): "
            + ", ".join(unknown)
            + ". Call get_camera_controls for the list on this device."
        )
    if not updates:
        raise ValueError("no controls to set")
    return expand_gated_updates(updates)


def measure_rgb(data: bytes, width: int, height: int) -> dict[str, float | int]:
    expected = width * height * 3
    if len(data) != expected:
        raise RuntimeError(f"RGB buffer size {len(data)} != {expected} ({width}x{height})")
    n = width * height
    total = 0.0
    clip_hi = 0
    clip_lo = 0
    mv = memoryview(data)
    for i in range(0, expected, 3):
        y = 0.299 * mv[i] + 0.587 * mv[i + 1] + 0.114 * mv[i + 2]
        total += y
        if y >= CLIP_HI_LUMA:
            clip_hi += 1
        elif y <= CLIP_LO_LUMA:
            clip_lo += 1
    return {
        "mean_luma": round(total / n, 2),
        "clip_hi_frac": round(clip_hi / n, 5),
        "clip_lo_frac": round(clip_lo / n, 5),
        "width": width,
        "height": height,
        "pixels": n,
    }


def jpeg_size(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=V4L2_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffprobe timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"ffprobe failed: {detail}") from exc
    line = (proc.stdout or "").strip()
    parts = line.replace(",", " ").split()
    if len(parts) < 2:
        raise RuntimeError(f"ffprobe did not report size for {path}")
    return int(parts[0]), int(parts[1])


def measure_jpeg(path: Path, width: int | None = None, height: int | None = None) -> dict[str, float | int]:
    if width is None or height is None:
        width, height = jpeg_size(path)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, timeout=V4L2_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg measure timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip() or str(exc)
        raise RuntimeError(f"ffmpeg measure failed: {detail}") from exc
    return measure_rgb(proc.stdout, width, height)


def well_exposed(
    metrics: dict[str, float | int],
    *,
    target_mean: float = TARGET_MEAN,
    mean_low: float = MEAN_LOW,
    mean_high: float = MEAN_HIGH,
    clip_hi_max: float = CLIP_HI_MAX,
    clip_lo_max: float = CLIP_LO_MAX,
) -> bool:
    del target_mean  # used by callers for nudging, not the pass/fail band
    mean = float(metrics["mean_luma"])
    clip_hi = float(metrics["clip_hi_frac"])
    clip_lo = float(metrics["clip_lo_frac"])
    if clip_hi > clip_hi_max or mean > mean_high or mean < mean_low:
        return False
    # Only treat shadows as a failure when the whole frame is crushed.
    if clip_lo > clip_lo_max and mean < mean_low:
        return False
    return True


def _nudge_step(ctrl: dict[str, Any]) -> int:
    lo = ctrl.get("min")
    hi = ctrl.get("max")
    step = ctrl.get("step")
    value = ctrl.get("value")
    if not isinstance(step, int) or step <= 0:
        step = 1
    span = (hi - lo) if isinstance(lo, int) and isinstance(hi, int) else 64
    if span > 1000 and isinstance(value, int):
        # exposure_time_absolute is 1..10000; 8% of the span is far too coarse.
        raw = max(step, int(max(abs(value), 24) * 0.25))
    else:
        raw = max(step, int(span * 0.08))
        raw = max(8 if span >= 32 else step, raw)
    return max(step, (raw // step) * step)


def suggest_nudge(
    known: dict[str, dict[str, Any]],
    metrics: dict[str, float | int],
    *,
    target_mean: float = TARGET_MEAN,
    mean_low: float = MEAN_LOW,
    mean_high: float = MEAN_HIGH,
    clip_hi_max: float = CLIP_HI_MAX,
    clip_lo_max: float = CLIP_LO_MAX,
) -> dict[str, int] | None:
    """Return one control update to move exposure, or None if the frame is fine."""
    if well_exposed(
        metrics,
        target_mean=target_mean,
        mean_low=mean_low,
        mean_high=mean_high,
        clip_hi_max=clip_hi_max,
        clip_lo_max=clip_lo_max,
    ):
        return None
    mean = float(metrics["mean_luma"])
    clip_hi = float(metrics["clip_hi_frac"])
    too_bright = clip_hi > clip_hi_max or mean > mean_high
    sign = -1 if too_bright else 1
    if mean < 2:
        # Black/failed grab (this UVC cam does this with huge shutter values).
        return {}
    # Gain is the control that actually moves this Logitech; shutter is a last resort.
    for name in ("gain", "brightness", "exposure_time_absolute"):
        ctrl = known.get(name)
        if ctrl is None or not isinstance(ctrl.get("value"), int):
            continue
        step = _nudge_step(ctrl)
        # If far from target, take a bigger bite.
        err = abs(mean - target_mean)
        if err > 40:
            step *= 2
        new = clamp_value(ctrl, ctrl["value"] + sign * step)
        if new == ctrl["value"]:
            continue
        update = {name: new}
        if name == "exposure_time_absolute":
            update["auto_exposure"] = 1
        return update
    return {}


def freeze_auto_exposure(known: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Take AE out of aperture-priority so later nudges stick.

    The inactive exposure reading while AE is on is often stale on this
    Logitech, so prefer the driver default shutter and keep the current gain.
    """
    ae = known.get("auto_exposure")
    if ae is None or ae.get("value") == 1:
        return {}
    updates = {"auto_exposure": 1}
    exposure = known.get("exposure_time_absolute")
    if exposure is not None:
        if exposure.get("inactive") and isinstance(exposure.get("default"), int):
            updates["exposure_time_absolute"] = int(exposure["default"])
        elif isinstance(exposure.get("value"), int):
            updates["exposure_time_absolute"] = clamp_value(exposure, int(exposure["value"]))
        elif isinstance(exposure.get("default"), int):
            updates["exposure_time_absolute"] = int(exposure["default"])
    gain = known.get("gain")
    if gain is not None and isinstance(gain.get("value"), int):
        updates["gain"] = clamp_value(gain, int(gain["value"]))
    return updates
