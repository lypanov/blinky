#!/usr/bin/python3
"""Measure an FPGA LED blink rate from a recorded camera clip.

Finds the LED automatically (pixels that vary most over time, biased toward
red), extracts brightness, thresholds it, and reports frequency / period /
duty cycle / confidence. matplotlib must be the system package: run this
with /usr/bin/python3, not a mise/pyenv interpreter.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Hardware Blink2 (tests/Blink2hw.Mod) vs Verilator Blink2test.
CLOCK_HZ = 27_000_000
HW_MAX_ITERATIONS = 524_288
SIM_MAX_ITERATIONS = 5
SIM_CYCLES_PER_EDGE = 78.0  # Verilator mean period between LED edges


def expected_blink(clock_hz: float = CLOCK_HZ) -> dict[str, float]:
    """Scale the sim edge period from maxIterations=5 up to hardware 524288."""
    cycles_per_edge = SIM_CYCLES_PER_EDGE * (HW_MAX_ITERATIONS / SIM_MAX_ITERATIONS)
    toggle_hz = clock_hz / cycles_per_edge
    freq = toggle_hz / 2.0
    return {
        "clock_hz": clock_hz,
        "max_iterations": HW_MAX_ITERATIONS,
        "sim_cycles_per_edge": SIM_CYCLES_PER_EDGE,
        "sim_max_iterations": SIM_MAX_ITERATIONS,
        "cycles_per_edge": cycles_per_edge,
        "toggle_rate_hz": toggle_hz,
        "frequency_hz": freq,
        "period_s": 1.0 / freq,
    }


def run_ffprobe(path: str) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-select_streams",
        "v:0",
        path,
    ]
    out = subprocess.check_output(cmd, text=True)
    info = json.loads(out)
    stream = info["streams"][0]
    fmt = info.get("format", {})

    def parse_rate(s: str | None) -> float | None:
        if not s or s in ("0/0", "N/A"):
            return None
        if "/" in s:
            a, b = s.split("/", 1)
            den = float(b)
            return None if den == 0 else float(a) / den
        try:
            return float(s)
        except ValueError:
            return None

    width = int(stream["width"])
    height = int(stream["height"])
    fps = parse_rate(stream.get("avg_frame_rate")) or parse_rate(stream.get("r_frame_rate"))
    duration = None
    if stream.get("duration"):
        duration = float(stream["duration"])
    elif fmt.get("duration"):
        duration = float(fmt["duration"])
    n_frames = None
    if stream.get("nb_frames") and stream["nb_frames"] not in ("N/A", "0"):
        n_frames = int(stream["nb_frames"])
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "n_frames": n_frames,
    }


def iter_rgb_frames(path: str, width: int, height: int):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    nbytes = width * height * 3
    try:
        while True:
            buf = proc.stdout.read(nbytes)
            if len(buf) < nbytes:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3))
    finally:
        proc.stdout.close()
        proc.wait()


def parse_roi(spec: str) -> tuple[int, int, int, int]:
    parts = [int(p.strip()) for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI must be x,y,w,h")
    x, y, w, h = parts
    if w <= 0 or h <= 0:
        raise ValueError("ROI width/height must be positive")
    return x, y, w, h


def clamp_roi(x: int, y: int, w: int, h: int, width: int, height: int) -> tuple[int, int, int, int]:
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def auto_roi(std: np.ndarray, mean_r: np.ndarray, mean_g: np.ndarray) -> tuple[int, int, int, int, str]:
    """LED = temporally-variable AND red. Falls back to the reddest bright blob."""
    red = np.maximum(mean_r - mean_g, 0.0)
    score = std * (red + 1.0)
    y0, x0 = np.unravel_index(int(np.argmax(score)), score.shape)
    peak = float(score[y0, x0])
    method = "variance-red"
    if peak <= 1e-6 or float(std[y0, x0]) < 2.0:
        y0, x0 = np.unravel_index(int(np.argmax(red)), red.shape)
        peak = float(red[y0, x0])
        method = "red-blob"
        field = red
    else:
        field = score

    thresh = max(peak * 0.35, float(np.percentile(field, 99.5)))
    h, w = field.shape
    max_radius = max(12, min(h, w) // 8)
    ys, xs = np.where(field >= thresh)
    if len(ys) == 0:
        xs = np.array([x0])
        ys = np.array([y0])
    dist = np.hypot(ys.astype(np.float64) - y0, xs.astype(np.float64) - x0)
    keep = dist <= max_radius
    xs, ys = xs[keep], ys[keep]
    if len(xs) == 0:
        xs = np.array([x0])
        ys = np.array([y0])
    pad = 6
    x = int(xs.min()) - pad
    y = int(ys.min()) - pad
    ww = int(xs.max() - xs.min()) + 1 + 2 * pad
    hh = int(ys.max() - ys.min()) + 1 + 2 * pad
    ww = max(ww, 12)
    hh = max(hh, 12)
    return clamp_roi(x, y, ww, hh, w, h) + (method,)


def split_threshold(values: np.ndarray) -> tuple[float, float, float]:
    v = np.asarray(values, dtype=np.float64)
    t = 0.5 * (float(np.percentile(v, 10)) + float(np.percentile(v, 90)))
    low_mean = high_mean = t
    for _ in range(12):
        low = v[v <= t]
        high = v[v > t]
        if low.size == 0 or high.size == 0:
            break
        low_mean = float(low.mean())
        high_mean = float(high.mean())
        t = 0.5 * (low_mean + high_mean)
    return t, low_mean, high_mean


def hysteresis_states(values: np.ndarray, low_t: float, high_t: float) -> np.ndarray:
    states = np.empty(len(values), dtype=np.int8)
    state = 1 if values[0] >= 0.5 * (low_t + high_t) else 0
    for i, x in enumerate(values):
        if state == 0 and x >= high_t:
            state = 1
        elif state == 1 and x <= low_t:
            state = 0
        states[i] = state
    return states


def edges_from_states(states: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(states) < 2:
        return np.array([], dtype=int), np.array([], dtype=int)
    diff = np.diff(states.astype(np.int16))
    rising = np.where(diff == 1)[0] + 1
    falling = np.where(diff == -1)[0] + 1
    return rising, falling


def fft_peak_hz(values: np.ndarray, fps: float) -> tuple[float | None, float]:
    n = len(values)
    if n < 16 or fps <= 0:
        return None, 0.0
    x = np.asarray(values, dtype=np.float64)
    x = x - x.mean()
    window = np.hanning(n)
    spec = np.fft.rfft(x * window)
    mag = np.abs(spec)
    freqs = np.fft.rfftfreq(n, d=1.0 / fps)
    # Ignore DC and very slow wander (< 0.15 Hz).
    lo = 0.15
    hi = 0.45 * fps
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return None, 0.0
    mag_band = mag.copy()
    mag_band[~mask] = 0
    k = int(np.argmax(mag_band))
    peak = float(mag[k])
    floor = float(np.median(mag[mask])) + 1e-9
    snr = peak / floor
    return float(freqs[k]), snr


def measure_series(
    brightness: np.ndarray, fps: float
) -> dict[str, Any]:
    t, low_mean, high_mean = split_threshold(brightness)
    span = high_mean - low_mean
    # Hysteresis band: 20% of the low/high gap around the midpoint.
    band = max(0.08 * (span if span > 0 else np.ptp(brightness)), 1e-3)
    low_t = t - band
    high_t = t + band
    states = hysteresis_states(brightness, low_t, high_t)
    rising, falling = edges_from_states(states)
    edges = np.sort(np.concatenate([rising, falling]))
    marks = rising if len(rising) >= 2 else falling
    periods = np.diff(marks.astype(np.float64)) / fps if len(marks) >= 2 else np.array([])

    duration = (len(brightness) - 1) / fps if len(brightness) > 1 else 0.0
    warnings: list[str] = []

    freq = None
    period = None
    period_std = None
    period_median = None
    if len(marks) >= 2:
        # Long baseline: (last-first)/(n-1). Median of per-cycle intervals is
        # biased when the true period is not an integer number of frames.
        period = float(marks[-1] - marks[0]) / (len(marks) - 1) / fps
        period_std = float(np.std(periods)) if len(periods) else None
        period_median = float(np.median(periods)) if len(periods) else None
        if period > 0:
            freq = 1.0 / period
    elif len(edges) >= 2 and duration > 0:
        # Half-periods only: two edges ≈ one full blink.
        n_full = len(edges) / 2.0
        freq = n_full / duration
        period = 1.0 / freq if freq else None

    fft_hz, fft_snr = fft_peak_hz(brightness, fps)
    if freq is None and fft_hz:
        freq = fft_hz
        period = 1.0 / freq

    duty = float(states.mean()) if len(states) else None

    # Confidence: period regularity × on/off separation × enough edges.
    conf = 0.0
    if freq and period and span > 0:
        cv = (period_std / period) if (period_std is not None and period > 0) else 1.0
        regular = max(0.0, 1.0 - min(cv, 1.0))
        sep = min(1.0, span / (np.std(brightness) * 2.0 + 1e-9))
        n_need = max(4.0, duration * freq)
        enough = min(1.0, len(edges) / n_need) if n_need else 0.0
        conf = float(max(0.0, min(1.0, 0.5 * regular + 0.3 * sep + 0.2 * enough)))
        if fft_hz and abs(fft_hz - freq) / max(freq, 1e-9) > 0.25:
            conf *= 0.6
            warnings.append(
                f"edge frequency {freq:.3f} Hz disagrees with FFT peak {fft_hz:.3f} Hz"
            )
    if fft_snr > 5 and conf < 0.3:
        conf = min(0.7, conf + 0.3)

    nyquist = fps / 2.0
    aliasing = None
    if freq is not None:
        if nyquist > 0 and freq > 0.4 * fps:
            aliasing = (
                f"measured {freq:.3f} Hz is close to Nyquist ({nyquist:.3f} Hz at "
                f"{fps:.3f} fps); the true rate may be aliased"
            )
            warnings.append(aliasing)
        elif nyquist > 0 and abs(freq - nyquist) < 0.15 * nyquist:
            aliasing = (
                f"measured {freq:.3f} Hz is near fps/2 ({nyquist:.3f} Hz); "
                "blink may be undersampled"
            )
            warnings.append(aliasing)

    if span < 5:
        warnings.append("on/off brightness gap is small; ROI may have missed the LED")
        conf = min(conf, 0.3)
    if len(edges) < 4:
        warnings.append(f"only {len(edges)} edges in {duration:.1f}s; frequency is uncertain")
        conf = min(conf, 0.35)

    return {
        "frequency_hz": freq,
        "period_s": period,
        "period_median_s": period_median,
        "period_std_s": period_std,
        "toggle_rate_hz": (2.0 * freq) if freq else None,
        "duty_cycle": duty,
        "edge_count": int(len(edges)),
        "rising_edge_count": int(len(rising)),
        "falling_edge_count": int(len(falling)),
        "confidence": round(conf, 4),
        "threshold": t,
        "low_mean": low_mean,
        "high_mean": high_mean,
        "fft_frequency_hz": fft_hz,
        "fft_snr": fft_snr,
        "aliasing_warning": aliasing,
        "warnings": warnings,
        "duration_s": duration,
        "n_frames": int(len(brightness)),
        "fps": fps,
        "states": states,
        "rising": rising,
        "falling": falling,
    }


def draw_roi_png(frame: np.ndarray, roi: tuple[int, int, int, int], path: str, label: str) -> None:
    im = Image.fromarray(frame, mode="RGB")
    draw = ImageDraw.Draw(im)
    x, y, w, h = roi
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=(0, 255, 40), width=3)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((8, 8), label, fill=(0, 255, 40), font=font)
    im.save(path)


def plot_brightness(
    brightness: np.ndarray,
    fps: float,
    meas: dict[str, Any],
    path: str,
) -> None:
    t = np.arange(len(brightness), dtype=np.float64) / fps
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(t, brightness, color="#c43c3c", linewidth=1.1, label="ROI brightness")
    ax.axhline(meas["threshold"], color="#888888", linestyle="--", linewidth=1, label="threshold")
    states = meas["states"]
    ax.fill_between(t, brightness.min(), brightness.max(), where=states.astype(bool),
                    color="#c43c3c", alpha=0.12, linewidth=0)
    freq = meas["frequency_hz"]
    title = "LED brightness vs time"
    if freq:
        title += f"  —  {freq:.4f} Hz  (T={meas['period_s']:.4f}s, conf={meas['confidence']:.2f})"
    ax.set_title(title)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("mean (R − G) in ROI")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def analyze(
    video: str,
    outdir: str,
    warmup_s: float,
    roi_spec: str | None,
    fps_override: float | None,
) -> dict[str, Any]:
    os.makedirs(outdir, exist_ok=True)
    meta = run_ffprobe(video)
    width, height = meta["width"], meta["height"]
    fps = fps_override or meta["fps"]
    if not fps or fps <= 0:
        raise SystemExit("could not determine fps; pass --fps")

    # Pass 1: temporal stats on (R−G), skipping warmup.
    n_skip = int(round(warmup_s * fps))
    n = 0
    used = 0
    sum_r = np.zeros((height, width), dtype=np.float64)
    sum_g = np.zeros((height, width), dtype=np.float64)
    sumsq = np.zeros((height, width), dtype=np.float64)
    best_on = None
    best_on_score = -1.0
    last_frame = None
    for frame in iter_rgb_frames(video, width, height):
        last_frame = frame
        n += 1
        if n <= n_skip:
            continue
        rgb = frame.astype(np.float32)
        rg = np.maximum(rgb[:, :, 0] - rgb[:, :, 1], 0.0)
        sum_r += rgb[:, :, 0]
        sum_g += rgb[:, :, 1]
        sumsq += rg.astype(np.float64) ** 2
        used += 1
        score = float(rg.mean())
        if score > best_on_score:
            best_on_score = score
            best_on = frame.copy()
    if used < 8:
        raise SystemExit(
            f"not enough frames after warmup (total={n}, skip={n_skip}, used={used})"
        )

    mean_r = sum_r / used
    mean_g = sum_g / used
    mean_rg = np.maximum(mean_r - mean_g, 0.0)
    # Variance of (R−G). We accumulated sumsq of rg but not sum(rg).
    # Reuse mean_rg as E[rg]; std ≈ sqrt(E[x^2] - E[x]^2).
    var = np.maximum(sumsq / used - mean_rg ** 2, 0.0)
    std = np.sqrt(var)

    if roi_spec:
        x, y, w, h = clamp_roi(*parse_roi(roi_spec), width, height)
        method = "manual"
    else:
        x, y, w, h, method = auto_roi(std, mean_r, mean_g)

    # Pass 2: brightness time series from the ROI.
    brightness = []
    n = 0
    for frame in iter_rgb_frames(video, width, height):
        n += 1
        if n <= n_skip:
            continue
        patch = frame[y : y + h, x : x + w].astype(np.float32)
        brightness.append(float(np.mean(np.maximum(patch[:, :, 0] - patch[:, :, 1], 0.0))))
    brightness = np.asarray(brightness, dtype=np.float64)

    # Prefer fps implied by the kept samples if probe duration is trustworthy.
    probed_n = meta.get("n_frames")
    probed_d = meta.get("duration")
    if probed_n and probed_d and probed_d > 0:
        fps_from_file = (probed_n - 1) / probed_d if probed_n > 1 else fps
        # Only replace if close — container copy can have odd nb_frames.
        if 0.5 * fps < fps_from_file < 1.5 * fps:
            fps = fps_from_file

    meas = measure_series(brightness, fps)
    exp = expected_blink()
    err = None
    implied_cycles_per_edge = None
    implied_cycles_per_iteration = None
    if meas["frequency_hz"]:
        err = 100.0 * (meas["frequency_hz"] - exp["frequency_hz"]) / exp["frequency_hz"]
        toggle = meas["toggle_rate_hz"]
        if toggle:
            implied_cycles_per_edge = CLOCK_HZ / toggle
            implied_cycles_per_iteration = implied_cycles_per_edge / HW_MAX_ITERATIONS
    exp["note"] = (
        "Scales Verilator's 78-cycle edge period at maxIterations=5 linearly "
        "to 524288. Sim memory is 1-cycle; Gowin SPRAM wait-states make the "
        "hardware loop slower, so this is an upper bound on blink Hz."
    )

    roi_frame = best_on if best_on is not None else last_frame
    roi_png = os.path.join(outdir, "roi.png")
    plot_png = os.path.join(outdir, "brightness.png")
    csv_path = os.path.join(outdir, "brightness.csv")
    json_path = os.path.join(outdir, "result.json")

    if roi_frame is not None:
        draw_roi_png(roi_frame, (x, y, w, h), roi_png, f"ROI {x},{y} {w}x{h} ({method})")
    plot_brightness(brightness, fps, meas, plot_png)

    times = np.arange(len(brightness), dtype=np.float64) / fps
    with open(csv_path, "w") as f:
        f.write("t_s,brightness,state\n")
        for i, (ti, b) in enumerate(zip(times, brightness)):
            f.write(f"{ti:.6f},{b:.4f},{int(meas['states'][i])}\n")

    result = {
        "frequency_hz": meas["frequency_hz"],
        "period_s": meas["period_s"],
        "period_median_s": meas["period_median_s"],
        "period_std_s": meas["period_std_s"],
        "toggle_rate_hz": meas["toggle_rate_hz"],
        "implied_cycles_per_edge": implied_cycles_per_edge,
        "implied_cycles_per_iteration": implied_cycles_per_iteration,
        "duty_cycle": meas["duty_cycle"],
        "edge_count": meas["edge_count"],
        "rising_edge_count": meas["rising_edge_count"],
        "falling_edge_count": meas["falling_edge_count"],
        "confidence": meas["confidence"],
        "threshold": meas["threshold"],
        "fft_frequency_hz": meas["fft_frequency_hz"],
        "aliasing_warning": meas["aliasing_warning"],
        "warnings": meas["warnings"],
        "fps": fps,
        "probed_fps": meta["fps"],
        "warmup_s": warmup_s,
        "duration_s": meas["duration_s"],
        "n_frames_analyzed": meas["n_frames"],
        "n_frames_total": n,
        "video": os.path.abspath(video),
        "roi": {"x": x, "y": y, "w": w, "h": h, "method": method},
        "paths": {
            "json": os.path.abspath(json_path),
            "plot": os.path.abspath(plot_png),
            "roi_frame": os.path.abspath(roi_png),
            "csv": os.path.abspath(csv_path),
        },
        "expected": exp,
        "error_pct_vs_expected": err,
    }
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    return result


def write_synthetic_clip(path: str, freq_hz: float, fps: float, seconds: float) -> None:
    """Red 10×10 square blinking on black; used by --self-test."""
    width, height = 160, 120
    n = int(round(seconds * fps))
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "mjpeg",
        "-q:v",
        "5",
        path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    x0, y0, s = 70, 50, 10
    period = 1.0 / freq_hz
    for i in range(n):
        t = i / fps
        on = (t % period) < 0.5 * period
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        if on:
            frame[y0 : y0 + s, x0 : x0 + s] = (255, 16, 16)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed writing synthetic clip (exit {rc})")


def self_test() -> int:
    freq = 2.0
    fps = 30.0
    with tempfile.TemporaryDirectory(prefix="blink-selftest-") as td:
        clip = os.path.join(td, "synth.mkv")
        out = os.path.join(td, "out")
        write_synthetic_clip(clip, freq_hz=freq, fps=fps, seconds=6.0)
        result = analyze(clip, out, warmup_s=0.0, roi_spec=None, fps_override=None)
        got = result["frequency_hz"]
        if got is None:
            print("self-test FAIL: no frequency", file=sys.stderr)
            return 1
        err = abs(got - freq) / freq
        print(json.dumps({"got_hz": got, "expected_hz": freq, "rel_err": err,
                          "confidence": result["confidence"], "roi": result["roi"]}, indent=2))
        if err > 0.08:
            print(f"self-test FAIL: {got:.4f} Hz vs {freq} Hz", file=sys.stderr)
            return 1
        print("self-test OK", file=sys.stderr)
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", help="recorded clip (mjpeg/mp4/mkv)")
    ap.add_argument("--outdir", help="directory for JSON / PNG / CSV")
    ap.add_argument("--warmup", type=float, default=8.0, help="seconds to discard at start")
    ap.add_argument("--roi", help="manual ROI x,y,w,h (pixels)")
    ap.add_argument("--fps", type=float, help="override detected fps")
    ap.add_argument("--self-test", action="store_true", help="synthetic 2 Hz blink sanity check")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.video or not args.outdir:
        ap.error("--video and --outdir are required (or pass --self-test)")
    result = analyze(args.video, args.outdir, args.warmup, args.roi, args.fps)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    freq = result["frequency_hz"]
    if freq is None:
        print("warning: no blink frequency detected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
