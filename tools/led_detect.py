#!/usr/bin/env python3
"""LED blob detection, colour, blink classification, and dual-board geometry.

No OpenCV. numpy + PIL. Used by the webcam MCP (auto_adjust, detect_leds,
measure_blink board ROIs). Does not touch the FPGA, serial, or openFPGALoader.

Desk layout (relative positions stay the same even if the pair drifts in
frame): Tang Primer 20K above with three LEDs (orange user LEDs + power),
Tang Nano 4K below with two red LEDs. Two of the five blink; three are
steady. Board identity is the LED pattern (count, colour, blink, geometry),
not USB cords.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BOARD_NANO4K = "nano4k"
BOARD_PRIMER20K = "primer20k"

# Complete-linkage merge cutoff. On Bee's 640x480 Logitech, LEDs on one
# board are ~40–90 px apart; the two boards are ~150–220 px apart.
CLUSTER_CUTOFF_PX = 120.0
MERGE_PX = 18.0
MIN_BLOB_AREA = 4
MAX_BLOB_AREA = 420
MAX_BLOB_SPAN = 56
MIN_BLINK_HZ = 0.85
MAX_BLINK_HZ = 8.0
BLINKER_PAD_PX = 12
BOARD_GAP_MARGIN_PX = 16
BLINKER_NMS_PX = 80.0
STEADY_NMS_PX = 24.0
NEAR_BLINKER_PX = 14.0
STD_PEAK_RADIUS = 6


def rgb_to_hsv(r: float, g: float, b: float) -> tuple[float, float, float]:
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    delta = mx - mn
    if delta < 1e-9:
        hue = 0.0
    elif mx == r:
        hue = (60.0 * ((g - b) / delta) + 360.0) % 360.0
    elif mx == g:
        hue = (60.0 * ((b - r) / delta) + 120.0) % 360.0
    else:
        hue = (60.0 * ((r - g) / delta) + 240.0) % 360.0
    sat = 0.0 if mx <= 1e-9 else delta / mx
    return hue, sat, mx


def classify_led_color(r: float, g: float, b: float) -> str:
    """red / orange / other from a peak RGB sample.

    This Logitech often reports G≈B. Orange still shows as hue ~15–40 or a
    higher G/R than a clipped red core.
    """
    hue, sat, val = rgb_to_hsv(r, g, b)
    if sat < 0.10 or val < 0.12:
        return "other"
    gr = g / max(r, 1.0)
    br = b / max(r, 1.0)
    if 12.0 <= hue <= 52.0:
        return "orange"
    if hue <= 18.0 or hue >= 340.0:
        if 0.20 <= gr <= 0.65 and br <= gr + 0.15:
            return "orange"
        return "red"
    return "other"


def load_jpeg_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def iter_rgb_frames(path: str, width: int, height: int):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", path,
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
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
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
        proc.wait()


def _connected_components(mask: np.ndarray, min_area: int, max_area: int) -> list[np.ndarray]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    blobs: list[np.ndarray] = []
    ys, xs = np.where(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        pix: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pix.append((y, x))
            for dy, dx in (
                (-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (-1, 1), (1, -1), (1, 1),
            ):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if min_area <= len(pix) <= max_area:
            arr = np.array(pix, dtype=np.int32)
            span_y = int(arr[:, 0].max() - arr[:, 0].min() + 1)
            span_x = int(arr[:, 1].max() - arr[:, 1].min() + 1)
            if span_x > MAX_BLOB_SPAN or span_y > MAX_BLOB_SPAN:
                continue
            if span_x * span_y > 0 and len(pix) / (span_x * span_y) < 0.25:
                continue
            blobs.append(arr)
    return blobs


def detect_blobs(rgb: np.ndarray) -> list[dict[str, Any]]:
    """Compact red/orange bright spots in one RGB frame (H, W, 3)."""
    arr = np.asarray(rgb, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 1.0)
    rg = r - g
    rb = r - b
    mask = (
        (r >= 80)
        & (rg >= 16)
        & (rb >= 8)
        & (r > g)
        & (r > b)
        & (luma >= 32)
        & (sat >= 0.20)
    )
    raw = _connected_components(mask, MIN_BLOB_AREA, MAX_BLOB_AREA)
    blobs: list[dict[str, Any]] = []
    for pix in raw:
        ys, xs = pix[:, 0], pix[:, 1]
        vals_r = r[ys, xs]
        vals_g = g[ys, xs]
        vals_b = b[ys, xs]
        chroma = vals_r - 0.5 * vals_g - 0.5 * vals_b
        peak_i = int(np.argmax(chroma))
        pr, pg, pb = float(vals_r[peak_i]), float(vals_g[peak_i]), float(vals_b[peak_i])
        hue, sat_p, _val = rgb_to_hsv(pr, pg, pb)
        area = int(len(pix))
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        blobs.append(
            {
                "x": float(xs.mean()),
                "y": float(ys.mean()),
                "x0": x0,
                "y0": y0,
                "w": x1 - x0 + 1,
                "h": y1 - y0 + 1,
                "area": area,
                "r": pr,
                "g": pg,
                "b": pb,
                "hue": round(hue, 1),
                "sat": round(float(sat_p), 3),
                "peak_r": float(vals_r.max()),
                "clip_frac": float((vals_r >= 250).mean()),
                "color": classify_led_color(pr, pg, pb),
                "luma": float(luma[ys, xs].mean()),
            }
        )
    # Drop gray-floor specks that pass the mask when brightness is lifted.
    blobs = [b for b in blobs if b["peak_r"] >= 90 or (b["sat"] >= 0.45 and b["area"] >= 8)]
    return _merge_nearby(blobs)


def _merge_nearby(blobs: list[dict[str, Any]], dist: float = MERGE_PX) -> list[dict[str, Any]]:
    blobs = sorted(blobs, key=lambda b: -b["area"])
    merged: list[dict[str, Any]] = []
    for blob in blobs:
        hit = None
        for other in merged:
            if (blob["x"] - other["x"]) ** 2 + (blob["y"] - other["y"]) ** 2 <= dist ** 2:
                hit = other
                break
        if hit is None:
            merged.append(dict(blob))
            continue
        n = hit["area"] + blob["area"]
        # Keep the brighter core's position so a split LED is not sampled
        # in the dark gap between fragments.
        if float(blob.get("peak_r") or 0) > float(hit.get("peak_r") or 0):
            hit["x"], hit["y"] = blob["x"], blob["y"]
        hit["x0"] = min(hit["x0"], blob["x0"])
        hit["y0"] = min(hit["y0"], blob["y0"])
        hit["w"] = max(hit["x0"] + hit["w"], blob["x0"] + blob["w"]) - hit["x0"]
        hit["h"] = max(hit["y0"] + hit["h"], blob["y0"] + blob["h"]) - hit["y0"]
        hit["area"] = n
        if blob["sat"] > hit["sat"] or blob["peak_r"] > hit["peak_r"]:
            for key in ("r", "g", "b", "hue", "sat", "peak_r", "color"):
                hit[key] = blob[key]
        hit["clip_frac"] = max(hit["clip_frac"], blob["clip_frac"])
        hit["luma"] = max(hit["luma"], blob["luma"])
    return merged


def score_led_exposure(rgb: np.ndarray) -> dict[str, Any]:
    """Score a still for distinct, unclipped, coloured LED blobs.

    Dark background is expected. Mean luma is not the target.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    blobs = detect_blobs(arr)
    mean_luma = float(luma.mean())
    clip_hi = float((luma >= 250).mean())
    n = len(blobs)
    ranked = sorted(blobs, key=lambda b: float(b["sat"]) * float(b["peak_r"]), reverse=True)
    core = ranked[:5]
    score = 18.0 * min(len(core), 5)
    hues: list[float] = []
    bloom = 0.0
    for blob in core:
        score += 28.0 * min(float(blob["sat"]), 0.85)
        pr = float(blob["peak_r"])
        # Sweet-spot core brightness: dim cores lose as room light falls,
        # clipped/bloomed cores lose when gain is too high.
        score -= 0.004 * (pr - 170.0) ** 2
        if blob["area"] > 140:
            extra = blob["area"] - 140
            bloom += extra
            score -= 0.12 * extra
        if blob["clip_frac"] > 0.40 and blob["area"] > 60:
            score -= 22.0
        if pr < 80:
            score -= 10.0
        # Clipped cores bloom into the cables. Prefer a slightly dimmer gain.
        if pr >= 250:
            score -= 8.0
        if float(blob["clip_frac"]) > 0.15:
            score -= 10.0
        if blob["sat"] >= 0.18:
            hues.append(float(blob["hue"]))
        if blob["color"] in ("red", "orange"):
            score += 6.0
    colors = {b["color"] for b in core}
    if "red" in colors and "orange" in colors:
        score += 45.0
    elif hues:
        wrapped = [h if h <= 180 else h - 360 for h in hues]
        if max(wrapped) - min(wrapped) >= 10:
            score += 20.0
    if mean_luma > 70:
        score -= 0.55 * (mean_luma - 70)
    core_peaks = [float(b["peak_r"]) for b in core]
    med_peak = float(np.median(core_peaks)) if core_peaks else 0.0
    if med_peak < 150:
        score -= 0.55 * (150.0 - med_peak)
    if mean_luma < 2.2:
        score -= 14.0 * (2.2 - mean_luma)
    if clip_hi > 0.004:
        score -= 500.0 * clip_hi
    # Five real LEDs. Drift to 2 or to silk/reflections should lose.
    if n == 5:
        score += 22.0
    elif n == 4:
        score += 8.0
    elif n == 6:
        score += 4.0
    elif n < 3:
        score -= 28.0
    elif n > 7:
        score -= 10.0 * (n - 7)
    return {
        "score": round(float(score), 2),
        "n_blobs": n,
        "mean_luma": round(mean_luma, 2),
        "clip_hi_frac": round(clip_hi, 5),
        "has_red": "red" in colors,
        "has_orange": "orange" in colors,
        "bloom_px": round(bloom, 1),
        "med_peak": round(med_peak, 1),
        "blobs": blobs,
    }


def score_jpeg(path: Path) -> dict[str, Any]:
    metrics = score_led_exposure(load_jpeg_rgb(path))
    metrics["path"] = str(path)
    return metrics


def sample_disk(rgb: np.ndarray, x: float, y: float, radius: int = 4) -> np.ndarray:
    h, w, _ = rgb.shape
    x0 = max(0, int(round(x)) - radius)
    x1 = min(w, int(round(x)) + radius + 1)
    y0 = max(0, int(round(y)) - radius)
    y1 = min(h, int(round(y)) + radius + 1)
    patch = rgb[y0:y1, x0:x1].astype(np.float32)
    if patch.size == 0:
        return np.zeros(3, dtype=np.float32)
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    chroma = r - 0.5 * g - 0.5 * b
    return np.array(
        [float(r.mean()), float(g.mean()), float(b.mean()), float(chroma.mean())],
        dtype=np.float32,
    )


def fft_peak_hz(values: np.ndarray, fps: float) -> tuple[float | None, float]:
    n = len(values)
    if n < 16 or fps <= 0:
        return None, 0.0
    x = np.asarray(values, dtype=np.float64)
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(n, d=1.0 / fps)
    # Real blinkers here are ~1 Hz (20K) and ~3.43 Hz (4K). Reflections
    # wander near 0.6–0.8 Hz; keep them out of the blink band.
    keep = (freqs >= MIN_BLINK_HZ) & (freqs <= min(MAX_BLINK_HZ, fps / 2.2))
    if not np.any(keep):
        return None, 0.0
    band = spec[keep]
    peak_i = int(np.argmax(band))
    peak = float(band[peak_i])
    med = float(np.median(band)) if band.size else 0.0
    snr = peak / max(med, 1e-6)
    hz = float(freqs[keep][peak_i])
    return (hz if snr >= 3.0 else None), snr


def classify_temporal(series: np.ndarray, fps: float) -> tuple[str, float | None, float, float]:
    x = np.asarray(series, dtype=np.float64)
    if len(x) < 8:
        return "unknown", None, 0.0, 0.0
    mean = float(x.mean())
    std = float(x.std())
    ptp = float(x.max() - x.min())
    cv = std / max(abs(mean), 1e-6)
    hz, snr = fft_peak_hz(x, fps)
    if (
        hz is not None
        and MIN_BLINK_HZ <= hz <= MAX_BLINK_HZ
        and snr >= 4.0
        and cv >= 0.15
        and ptp >= 12.0
    ):
        return "blinking", hz, cv, snr
    if mean >= 10.0:
        return "steady", None, cv, snr
    return "unknown", None, cv, snr


def _edge_frequency_hz(series: np.ndarray, fps: float) -> float | None:
    """Rising-edge period of one LED trace. None when the swing is not a blink."""
    values = np.asarray(series, dtype=np.float64)
    if len(values) < 8 or fps <= 0:
        return None
    low = float(np.percentile(values, 10))
    high = float(np.percentile(values, 90))
    span = high - low
    if span < 8.0:
        return None
    band = max(0.12 * span, 1e-3)
    level = 0.5 * (low + high)
    state = 1 if values[0] >= level else 0
    rising: list[int] = []
    for i, sample in enumerate(values):
        if state == 0 and sample >= level + band:
            state = 1
            rising.append(i)
        elif state == 1 and sample <= level - band:
            state = 0
    if len(rising) < 2:
        return None
    period = (rising[-1] - rising[0]) / (len(rising) - 1) / fps
    if period <= 0:
        return None
    return 1.0 / period


def measure_chroma_trace(series: np.ndarray, fps: float) -> dict[str, Any]:
    """Headline rate for one LED, from its own chroma samples.

    The FFT is limited to the blink band (about 0.85–8 Hz). A padded-box
    mean can lock onto slow drift near 0.18 Hz and must not replace this.
    """
    values = np.asarray(series, dtype=np.float64)
    mean = float(values.mean()) if len(values) else 0.0
    std = float(values.std()) if len(values) else 0.0
    ptp = float(np.ptp(values)) if len(values) else 0.0
    cv = std / max(abs(mean), 1e-6)
    fft_hz, snr = fft_peak_hz(values, fps)
    edge_hz = _edge_frequency_hz(values, fps)
    if edge_hz is not None and not (MIN_BLINK_HZ <= edge_hz <= MAX_BLINK_HZ):
        edge_hz = None
    if fft_hz is not None and not (MIN_BLINK_HZ <= fft_hz <= MAX_BLINK_HZ):
        fft_hz = None
    blink_shape = cv >= 0.15 and ptp >= 12.0
    fft_ok = fft_hz is not None and snr >= 4.0 and blink_shape
    edge_ok = edge_hz is not None and blink_shape and (
        fft_hz is None or abs(edge_hz - fft_hz) / max(edge_hz, fft_hz) <= 0.12 or fft_ok
    )
    freq: float | None = None
    method = "untrusted"
    reason = "no blink on this LED"
    if edge_ok and fft_ok:
        rel = abs(edge_hz - fft_hz) / max(edge_hz, fft_hz)
        if rel <= 0.12:
            freq, method = edge_hz, "edge"
            reason = "blinking LED edge period agrees with its FFT"
        else:
            # Keep the classified blink-band rate. Do not drop it because a
            # different estimator (or a padded box) saw something else.
            freq, method = fft_hz, "fft"
            reason = (
                f"blinking LED FFT {fft_hz:.3f} Hz "
                f"(edge {edge_hz:.3f} Hz disagrees; box-mean peak is not used)"
            )
    elif fft_ok:
        freq, method = fft_hz, "fft"
        reason = "blinking LED FFT (edge detector found no in-band period)"
    elif edge_ok:
        freq, method = edge_hz, "edge"
        reason = "blinking LED edge period"
    if freq is None:
        state = "steady" if mean >= 10.0 else "unknown"
        conf = 0.12
    else:
        state = "blinking"
        agree = 1.0
        if edge_hz and fft_hz:
            rel = abs(edge_hz - fft_hz) / max(edge_hz, fft_hz)
            agree = 1.0 if rel <= 0.12 else 0.45
        elif method == "fft":
            agree = 0.7
        snr_term = min(1.0, float(snr) / 8.0)
        conf = float(max(0.0, min(1.0, 0.25 + 0.4 * agree + 0.35 * snr_term)))
    return {
        "state": state,
        "frequency_hz": None if freq is None else round(float(freq), 3),
        "edge_frequency_hz": None if edge_hz is None else round(float(edge_hz), 3),
        "fft_frequency_hz": None if fft_hz is None else round(float(fft_hz), 3),
        "fft_snr": round(float(snr), 2),
        "trusted_method": method,
        "trusted_reason": reason,
        "confidence": round(conf, 3),
        "cv": cv,
        "snr": snr,
        "source": "blinking-led",
    }


def peak_rgb(rgb: np.ndarray, x: float, y: float, radius: int = 3) -> tuple[float, float, float]:
    """RGB of the highest-chroma pixel in a small disk.

    The disk mean mixes in cable silk and bloom and can turn a red core orange.
    """
    h, w, _ = rgb.shape
    x0 = max(0, int(round(x)) - radius)
    x1 = min(w, int(round(x)) + radius + 1)
    y0 = max(0, int(round(y)) - radius)
    y1 = min(h, int(round(y)) + radius + 1)
    patch = rgb[y0:y1, x0:x1].astype(np.float32)
    if patch.size == 0:
        return 0.0, 0.0, 0.0
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    chroma = r - 0.5 * g - 0.5 * b
    flat = int(np.argmax(chroma))
    return float(r.flat[flat]), float(g.flat[flat]), float(b.flat[flat])


def _agglomerative(points: list[tuple[float, float]], cutoff: float) -> list[list[int]]:
    clusters = [{i} for i in range(len(points))]

    def complete_dist(a: set[int], b: set[int]) -> float:
        best = 0.0
        for i in a:
            for j in b:
                d = ((points[i][0] - points[j][0]) ** 2 + (points[i][1] - points[j][1]) ** 2) ** 0.5
                if d > best:
                    best = d
        return best

    while len(clusters) > 1:
        best: tuple[float, int, int] | None = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = complete_dist(clusters[i], clusters[j])
                if d <= cutoff and (best is None or d < best[0]):
                    best = (d, i, j)
        if best is None:
            break
        _d, i, j = best
        clusters[i] = clusters[i] | clusters[j]
        del clusters[j]
    return [sorted(c) for c in clusters]


def _split_by_largest_gap(leds: list[dict[str, Any]]) -> list[list[int]]:
    order = sorted(range(len(leds)), key=lambda i: leds[i]["y"])
    if len(order) < 2:
        return [order]
    gaps = []
    for a, b in zip(order, order[1:]):
        gaps.append((leds[b]["y"] - leds[a]["y"], a, b))
    gap, _a, _b = max(gaps, key=lambda t: t[0])
    if gap < 40:
        return [order]
    cut = None
    for i, idx in enumerate(order[:-1]):
        nxt = order[i + 1]
        if leds[nxt]["y"] - leds[idx]["y"] == gap:
            cut = i + 1
            break
    if cut is None:
        return [order]
    return [order[:cut], order[cut:]]


def assign_boards(
    leds: list[dict[str, Any]],
    cutoff: float | None = None,
) -> dict[str, Any]:
    """Group LEDs into nano4k / primer20k from geometry + colour + blink.

    Does not use USB cords. Relative layout (20K above 4K) is a tie-break.
    """
    if not leds:
        return {"boards": {}, "reason": "no LEDs"}
    points = [(float(led["x"]), float(led["y"])) for led in leds]
    groups = _agglomerative(points, cutoff or CLUSTER_CUTOFF_PX)
    # Prefer the large vertical gap between the two boards. Complete-linkage
    # otherwise isolates the 20K blinker when a nearby silk blob inflates
    # the upper cluster diameter.
    if len(leds) >= 4:
        split = _split_by_largest_gap(leds)
        if len(split) == 2:
            ys0 = [leds[i]["y"] for i in split[0]]
            ys1 = [leds[i]["y"] for i in split[1]]
            if abs(float(np.mean(ys0)) - float(np.mean(ys1))) >= 40:
                groups = split
    if len(groups) > 2:
        groups = sorted(
            groups,
            key=lambda g: (
                sum(1 for i in g if leds[i].get("state") == "blinking"),
                len(g),
            ),
            reverse=True,
        )[:2]

    scored: list[dict[str, Any]] = []
    for idxs in groups:
        members = [leds[i] for i in idxs]
        n = len(members)
        n_orange = sum(1 for m in members if m.get("color") == "orange")
        n_red = sum(1 for m in members if m.get("color") == "red")
        n_blink = sum(1 for m in members if m.get("state") == "blinking")
        cy = float(np.mean([m["y"] for m in members]))
        cx = float(np.mean([m["x"] for m in members]))
        score_20k = 0.0
        score_4k = 0.0
        if n == 3:
            score_20k += 6.0
        elif n == 2:
            score_4k += 6.0
        elif n >= 4:
            score_20k += 2.0
        if n_orange:
            score_20k += 4.0 * n_orange
        if n_red and n_orange == 0:
            score_4k += 2.0
        if n_blink == 1:
            # both boards have one blinker in Alex's description
            pass
        scored.append(
            {
                "idxs": idxs,
                "members": members,
                "n": n,
                "cx": cx,
                "cy": cy,
                "n_orange": n_orange,
                "n_red": n_red,
                "n_blink": n_blink,
                "score_20k": score_20k,
                "score_4k": score_4k,
            }
        )

    if len(scored) == 1:
        only = scored[0]
        name = BOARD_PRIMER20K if only["score_20k"] >= only["score_4k"] else BOARD_NANO4K
        want = 3 if name == BOARD_PRIMER20K else 2
        boards = {name: _board_record(name, _prune_board_members(only["members"], want))}
        return {"boards": boards, "reason": "single cluster", "clusters": scored}

    # Relative layout is preserved: Primer 20K stays above Nano 4K. Count and
    # colour are evidence, not allowed to invert the names.
    a, b = scored[0], scored[1]
    upper, lower = (a, b) if a["cy"] < b["cy"] else (b, a)
    boards = {
        BOARD_PRIMER20K: _board_record(
            BOARD_PRIMER20K, _prune_board_members(upper["members"], 3)
        ),
        BOARD_NANO4K: _board_record(
            BOARD_NANO4K, _prune_board_members(lower["members"], 2)
        ),
    }
    _isolate_measure_rois(boards)
    reason = (
        f"upper=primer20k n={boards[BOARD_PRIMER20K]['n_leds']} "
        f"orange={sum(1 for m in boards[BOARD_PRIMER20K]['leds'] if m.get('color')=='orange')} "
        f"lower=nano4k n={boards[BOARD_NANO4K]['n_leds']} "
        f"orange={sum(1 for m in boards[BOARD_NANO4K]['leds'] if m.get('color')=='orange')} "
        f"cy={boards[BOARD_PRIMER20K]['cy']:.0f}/{boards[BOARD_NANO4K]['cy']:.0f}"
    )
    return {"boards": boards, "reason": reason, "clusters": scored}


def _prune_board_members(members: list[dict[str, Any]], want: int) -> list[dict[str, Any]]:
    """Keep one blinker plus the brightest steady cores; drop silk/reflections."""
    blink = [m for m in members if m.get("state") == "blinking"]
    blink.sort(
        key=lambda m: (
            float(m.get("std") or 0),
            float(m.get("cv") or 0),
            float(m.get("mean_chroma") or 0),
        ),
        reverse=True,
    )
    chosen = {id(blink[0])} if blink else set()
    rest = [m for m in members if id(m) not in chosen]
    rest.sort(key=lambda m: float(m.get("mean_chroma") or 0), reverse=True)
    out: list[dict[str, Any]] = []
    if blink:
        out.append(blink[0])
    for m in rest:
        if len(out) >= want:
            break
        out.append(m)
    primary = out[0] if out and out[0].get("state") == "blinking" else None
    if primary is not None:
        for m in out:
            if m is not primary and m.get("state") == "blinking":
                m["state"] = "steady"
                m["frequency_hz"] = None
                m["edge_frequency_hz"] = None
                m["fft_frequency_hz"] = None
                m["trusted_method"] = "untrusted"
                m["trusted_reason"] = "another LED on this board is the blinker"
                m["confidence"] = 0.12
                m.pop("trace", None)
    return out


def _target_blinker(members: list[dict[str, Any]]) -> dict[str, Any] | None:
    blinkers = [m for m in members if m.get("state") == "blinking"]
    if not blinkers:
        return None
    return max(
        blinkers,
        key=lambda m: (
            float(m.get("std") or 0),
            float(m.get("cv") or 0),
            float(m.get("mean_chroma") or 0),
        ),
    )


def _board_record(name: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    xs = [m["x"] for m in members]
    ys = [m["y"] for m in members]
    pad = 12
    x0 = max(0, int(min(m["x0"] for m in members) - pad))
    y0 = max(0, int(min(m["y0"] for m in members) - pad))
    x1 = int(max(m["x0"] + m["w"] for m in members) + pad)
    y1 = int(max(m["y0"] + m["h"] for m in members) + pad)
    target = _target_blinker(members)
    cx = float(np.mean(xs)) if xs else 0.0
    cy = float(np.mean(ys)) if ys else 0.0
    orientation = _orientation(members, cx, cy)
    board_roi = {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}
    measure_roi = _padded_roi(target, BLINKER_PAD_PX) if target is not None else None
    if target is None:
        status = "board present but not blinking"
        freq = edge = fft = None
        method = "untrusted"
        reason = status
        conf = 0.0
    else:
        status = "blinking"
        freq = target.get("frequency_hz")
        edge = target.get("edge_frequency_hz")
        fft = target.get("fft_frequency_hz")
        method = target.get("trusted_method") or "fft"
        reason = target.get("trusted_reason") or "blinking LED"
        conf = target.get("confidence") or 0.0
    return {
        "name": name,
        "cx": round(cx, 1),
        "cy": round(cy, 1),
        "roi": board_roi,
        "measure_roi": measure_roi,
        "target_led_id": None if target is None else target.get("id"),
        "n_leds": len(members),
        "n_blinking": sum(1 for m in members if m.get("state") == "blinking"),
        "n_steady": sum(1 for m in members if m.get("state") == "steady"),
        "colors": sorted({m.get("color", "other") for m in members}),
        "orientation": orientation,
        "leds": members,
        # Headline rate is the classified blinking LED, never a padded-box FFT.
        "frequency_hz": freq,
        "edge_frequency_hz": edge,
        "fft_frequency_hz": fft,
        "trusted_method": method,
        "trusted_reason": reason,
        "status": status,
        "confidence": conf,
        "source": "blinking-led",
    }


def _isolate_measure_rois(boards: dict[str, Any]) -> None:
    """Clip each blinker ROI so it cannot reach the other board."""
    upper = boards.get(BOARD_PRIMER20K)
    lower = boards.get(BOARD_NANO4K)
    if not upper or not lower:
        return
    gap = int(round((float(upper["cy"]) + float(lower["cy"])) / 2.0))
    uroi = upper.get("measure_roi")
    if uroi:
        y1 = min(uroi["y"] + uroi["h"], gap - BOARD_GAP_MARGIN_PX)
        uroi["h"] = max(12, y1 - uroi["y"])
    lroi = lower.get("measure_roi")
    if lroi:
        y0 = max(lroi["y"], gap + BOARD_GAP_MARGIN_PX)
        bottom = lroi["y"] + lroi["h"]
        lroi["y"] = y0
        lroi["h"] = max(12, bottom - y0)


def _padded_roi(led: dict[str, Any], pad: int = 10) -> dict[str, int]:
    x = max(0, int(led["x0"]) - pad)
    y = max(0, int(led["y0"]) - pad)
    w = int(led["w"]) + 2 * pad
    h = int(led["h"]) + 2 * pad
    return {"x": x, "y": y, "w": max(12, w), "h": max(12, h)}


def _orientation(members: list[dict[str, Any]], cx: float, cy: float) -> dict[str, Any]:
    blinkers = [m for m in members if m.get("state") == "blinking"]
    steady = [m for m in members if m.get("state") == "steady"]
    def side(led: dict[str, Any]) -> str:
        dx, dy = led["x"] - cx, led["y"] - cy
        if abs(dx) >= abs(dy):
            return "right" if dx >= 0 else "left"
        return "below" if dy >= 0 else "above"
    return {
        "blinking_vs_centroid": [side(m) for m in blinkers],
        "steady_vs_centroid": [side(m) for m in steady],
        "span_x": round(max(xs := [m["x"] for m in members]) - min(xs), 1) if members else 0.0,
        "span_y": round(max(ys := [m["y"] for m in members]) - min(ys), 1) if members else 0.0,
    }


def _nms_leds(leds: list[dict[str, Any]], min_dist: float) -> list[dict[str, Any]]:
    """Keep the highest-ranked LED and drop neighbours within min_dist."""
    kept: list[dict[str, Any]] = []
    for led in leds:
        if any((led["x"] - k["x"]) ** 2 + (led["y"] - k["y"]) ** 2 < min_dist ** 2 for k in kept):
            continue
        kept.append(led)
    return kept


def _keep_likely_leds(
    leds: list[dict[str, Any]],
    limit: int = 5,
    frame_wh: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Keep the five real LEDs: two blinkers and three bright steady cores."""
    w = h = None
    if frame_wh:
        w, h = frame_wh
    filtered: list[dict[str, Any]] = []
    for led in leds:
        if w and h:
            if led["y"] > 0.88 * h or led["y"] < 0.05 * h:
                continue
            if led["x"] < 0.08 * w or led["x"] > 0.92 * w:
                continue
        filtered.append(led)

    def chroma(led: dict[str, Any]) -> float:
        return float(led.get("mean_chroma") or 0)

    def blink_key(led: dict[str, Any]) -> tuple[float, float, float]:
        return (
            float(led.get("std") or 0),
            chroma(led),
            float(led.get("cv") or 0),
        )

    blinkers = [led for led in filtered if led.get("state") == "blinking"]
    blinkers.sort(key=blink_key, reverse=True)
    if blinkers:
        floor = 0.35 * chroma(blinkers[0])
        blinkers = [led for led in blinkers if chroma(led) >= floor]
    # Two real blinkers sit on different boards (~150 px). Glow around a
    # blinker also FFTs at that rate — drop it with NMS.
    blinkers = _nms_leds(blinkers, BLINKER_NMS_PX)[:2]
    used = {(led["x"], led["y"]) for led in blinkers}

    def near_blinker(led: dict[str, Any]) -> bool:
        return any(
            (led["x"] - b["x"]) ** 2 + (led["y"] - b["y"]) ** 2 < NEAR_BLINKER_PX ** 2
            for b in blinkers
        )

    leftover_blink = [
        led
        for led in filtered
        if led.get("state") == "blinking" and (led["x"], led["y"]) not in used
    ]
    steady = [
        led
        for led in filtered
        if (led["x"], led["y"]) not in used
        and not near_blinker(led)
        and led.get("color") in ("red", "orange")
        and chroma(led) >= 20.0
        and (led.get("state") != "blinking" or led in leftover_blink)
    ]
    steady.sort(key=chroma, reverse=True)
    if steady:
        floor = max(22.0, 0.22 * chroma(steady[0]))
        steady = [led for led in steady if chroma(led) >= floor]
    steady = _nms_leds(steady, STEADY_NMS_PX)
    kept = blinkers + steady
    return kept[: max(limit, 6)]


def _local_maxima(
    field: np.ndarray, radius: int = 6, max_peaks: int = 8
) -> list[tuple[int, int, float]]:
    """Strong isolated peaks of a 2-D field, strongest first."""
    h, w = field.shape
    thr = max(12.0, float(np.percentile(field, 99.0)))
    ys, xs = np.where(field >= thr)
    if len(xs) == 0:
        return []
    order = np.argsort(-field[ys, xs])
    taken = np.zeros(len(xs), dtype=bool)
    peaks: list[tuple[int, int, float]] = []
    sep2 = float((2 * radius) ** 2)
    for idx in order:
        if taken[idx]:
            continue
        x, y = int(xs[idx]), int(ys[idx])
        val = float(field[y, x])
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        if val < float(field[y0:y1, x0:x1].max()) - 1e-6:
            continue
        peaks.append((x, y, val))
        taken |= (xs.astype(np.float32) - x) ** 2 + (ys.astype(np.float32) - y) ** 2 <= sep2
        if len(peaks) >= max_peaks:
            break
    return peaks


def _blob_from_peak(rgb: np.ndarray, x: int, y: int, radius: int = 6) -> dict[str, Any]:
    h, w, _ = rgb.shape
    x0 = max(0, int(x) - radius)
    x1 = min(w, int(x) + radius + 1)
    y0 = max(0, int(y) - radius)
    y1 = min(h, int(y) + radius + 1)
    peak = rgb[min(h - 1, max(0, int(y))), min(w - 1, max(0, int(x)))]
    pr, pg, pb = float(peak[0]), float(peak[1]), float(peak[2])
    hue, sat, _val = rgb_to_hsv(pr, pg, pb)
    return {
        "x": float(x),
        "y": float(y),
        "x0": x0,
        "y0": y0,
        "w": max(1, x1 - x0),
        "h": max(1, y1 - y0),
        "area": max(1, (x1 - x0) * (y1 - y0) // 4),
        "r": pr,
        "g": pg,
        "b": pb,
        "hue": round(hue, 1),
        "sat": round(float(sat), 3),
        "peak_r": pr,
        "clip_frac": 0.0,
        "color": classify_led_color(pr, pg, pb),
        "luma": float(0.299 * pr + 0.587 * pg + 0.114 * pb),
    }


def analyze_frames(
    frames: list[np.ndarray],
    fps: float,
) -> dict[str, Any]:
    if not frames:
        raise ValueError("no frames")
    stacked = np.stack(frames, axis=0)
    max_rgb = stacked.max(axis=0)
    mean_rgb = stacked.mean(axis=0)
    # Std of red-minus-green finds blinkers even when mean is modest.
    rg = stacked[:, :, :, 0].astype(np.float32) - stacked[:, :, :, 1].astype(np.float32)
    std_rg = rg.std(axis=0)
    blobs = _merge_nearby(detect_blobs(max_rgb))
    # Blinkers are local maxima of temporal (R−G) variance. Max-projection
    # blobs miss them when they bloom past MAX_BLOB_AREA, or shrink to a
    # 4 px remnant whose centroid is off the core. Do not merge after
    # snapping — that would pull the variance peak off the core.
    for x, y, stdv in _local_maxima(std_rg, radius=STD_PEAK_RADIUS, max_peaks=8):
        peak_blob = _blob_from_peak(max_rgb, x, y, radius=STD_PEAK_RADIUS)
        peak_blob["std"] = stdv
        near = None
        best_d2 = MERGE_PX ** 2
        for blob in blobs:
            d2 = (blob["x"] - x) ** 2 + (blob["y"] - y) ** 2
            if d2 <= best_d2:
                near = blob
                best_d2 = d2
        if near is None:
            blobs.append(peak_blob)
            continue
        near["x"], near["y"] = float(x), float(y)
        near["std"] = stdv
        near["x0"] = min(int(near["x0"]), int(peak_blob["x0"]))
        near["y0"] = min(int(near["y0"]), int(peak_blob["y0"]))
        near["w"] = max(
            int(near["x0"]) + int(near["w"]),
            int(peak_blob["x0"]) + int(peak_blob["w"]),
        ) - int(near["x0"])
        near["h"] = max(
            int(near["y0"]) + int(near["h"]),
            int(peak_blob["y0"]) + int(peak_blob["h"]),
        ) - int(near["y0"])
        if float(peak_blob["peak_r"]) >= float(near.get("peak_r") or 0):
            for key in ("r", "g", "b", "hue", "sat", "peak_r", "color"):
                near[key] = peak_blob[key]

    leds: list[dict[str, Any]] = []
    for i, blob in enumerate(blobs):
        series = np.array(
            [sample_disk(frame, blob["x"], blob["y"])[3] for frame in frames],
            dtype=np.float32,
        )
        measured = measure_chroma_trace(series, fps)
        state = measured["state"]
        # Colour from the core pixel on the brightest frame, not the disk mean.
        peak_frame = frames[int(np.argmax(series))]
        pr, pg, pb = peak_rgb(peak_frame, blob["x"], blob["y"], radius=3)
        color = classify_led_color(pr, pg, pb)
        hue, sat, _v = rgb_to_hsv(pr, pg, pb)
        led = {
            "id": i,
            "x": round(float(blob["x"]), 1),
            "y": round(float(blob["y"]), 1),
            "x0": int(blob["x0"]),
            "y0": int(blob["y0"]),
            "w": int(blob["w"]),
            "h": int(blob["h"]),
            "area": int(blob["area"]),
            "r": round(pr, 1),
            "g": round(pg, 1),
            "b": round(pb, 1),
            "hue": round(hue, 1),
            "sat": round(sat, 3),
            "color": color,
            "state": state,
            "frequency_hz": measured["frequency_hz"],
            "edge_frequency_hz": measured["edge_frequency_hz"],
            "fft_frequency_hz": measured["fft_frequency_hz"],
            "trusted_method": measured["trusted_method"],
            "trusted_reason": measured["trusted_reason"],
            "confidence": measured["confidence"],
            "cv": round(float(measured["cv"]), 3),
            "snr": round(float(measured["snr"]), 2),
            "std": round(float(blob.get("std") or 0.0), 1),
            "mean_chroma": round(float(series.mean()), 2),
            "source": "blinking-led",
        }
        if state == "blinking":
            led["trace"] = [round(float(v), 2) for v in series]
        leds.append(led)

    h, w = frames[0].shape[:2]
    leds = _keep_likely_leds(leds, frame_wh=(w, h))
    for i, led in enumerate(leds):
        led["id"] = i

    cutoff = max(28.0, CLUSTER_CUTOFF_PX * (min(h, w) / 480.0))
    assigned = assign_boards(leds, cutoff=cutoff)
    for name, board in assigned.get("boards", {}).items():
        for led in board["leds"]:
            led["board"] = name
        for led in leds:
            if any(led["id"] == m["id"] for m in board["leds"]):
                led["board"] = name
    leds = [led for led in leds if led.get("board")]
    still = np.clip(0.55 * mean_rgb + 0.45 * max_rgb, 0, 255).astype(np.uint8)
    return {
        "leds": leds,
        "boards": assigned.get("boards", {}),
        "assign_reason": assigned.get("reason"),
        "fps": fps,
        "n_frames": len(frames),
        "still_rgb": still,
    }


def probe_video(path: Path) -> tuple[int, int, float, float | None]:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", "-select_streams", "v:0", str(path),
    ]
    info = json.loads(subprocess.check_output(cmd, text=True))
    stream = info["streams"][0]
    fmt = info.get("format") or {}
    width, height = int(stream["width"]), int(stream["height"])

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

    fps = parse_rate(stream.get("avg_frame_rate")) or parse_rate(stream.get("r_frame_rate")) or 30.0
    duration = None
    if stream.get("duration"):
        duration = float(stream["duration"])
    elif fmt.get("duration"):
        duration = float(fmt["duration"])
    return width, height, fps, duration


def analyze_video_once(
    path: Path, max_frames: int = 180, skip_s: float = 0.0
) -> tuple[dict[str, Any], np.ndarray]:
    width, height, fps, duration = probe_video(path)
    skip_n = max(0, int(round(skip_s * fps)))
    frames = []
    seen = 0
    for frame in iter_rgb_frames(str(path), width, height):
        if seen < skip_n:
            seen += 1
            continue
        frames.append(frame)
        seen += 1
        if len(frames) >= max_frames:
            break
    if duration and duration > 0 and len(frames) > 2:
        fps_file = (len(frames) - 1) / duration
        expected = duration * fps
        # Only trust duration-derived fps when we decoded (almost) the whole clip.
        # Truncating at --max-frames would otherwise report 150/6s ≈ 25 fps.
        if fps_file >= 4.0 and len(frames) >= 0.85 * max(expected, 1.0):
            fps = fps_file
    result = analyze_frames(frames, fps)
    still = result.pop("still_rgb")
    result["video"] = str(path)
    result["width"] = width
    result["height"] = height
    return result, still


def _font(size: int = 12):
    for name in (
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        p = Path(name)
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def write_trace_plot(series: list[float] | np.ndarray, fps: float, info: dict[str, Any], path: Path) -> None:
    """Brightness-style plot of one LED chroma trace. PIL only."""
    values = np.asarray(series, dtype=np.float64)
    width, height = 960, 300
    img = Image.new("RGB", (width, height), (18, 18, 20))
    draw = ImageDraw.Draw(img)
    font = _font(15)
    if len(values) < 2:
        draw.text((12, 12), "no samples", fill=(220, 220, 220), font=font)
        img.save(path)
        return
    lo = float(values.min())
    hi = float(values.max())
    if hi - lo < 1e-3:
        hi = lo + 1.0
    pad_x, pad_y = 36, 28
    pts = []
    span = len(values) - 1
    for i, sample in enumerate(values):
        x = pad_x + (width - 2 * pad_x) * i / span
        y = height - pad_y - (height - 2 * pad_y) * (float(sample) - lo) / (hi - lo)
        pts.append((x, y))
    draw.line(pts, fill=(220, 64, 64), width=2)
    hz = info.get("frequency_hz")
    hz_s = f"{hz:.3f} Hz" if isinstance(hz, (int, float)) else "no blink"
    label = (
        f"{info.get('board') or ''} {info.get('state') or ''} {hz_s} "
        f"{info.get('trusted_method') or ''}  source=blinking-led"
    )
    draw.rectangle([0, 0, width, 22], fill=(0, 0, 0))
    draw.text((8, 4), label.strip(), fill=(235, 235, 235), font=font)
    img.save(path)


def annotate(rgb: np.ndarray, result: dict[str, Any]) -> Image.Image:
    img = Image.fromarray(np.asarray(rgb, dtype=np.uint8), mode="RGB")
    draw = ImageDraw.Draw(img)
    font = _font(12)
    font_sm = _font(11)
    board_colors = {BOARD_NANO4K: (80, 180, 255), BOARD_PRIMER20K: (255, 200, 60)}
    for name, board in (result.get("boards") or {}).items():
        roi = board["roi"]
        col = board_colors.get(name, (255, 255, 255))
        box = [roi["x"], roi["y"], roi["x"] + roi["w"], roi["y"] + roi["h"]]
        draw.rectangle(box, outline=col, width=2)
        draw.text((roi["x"] + 4, max(0, roi["y"] - 14)), name, fill=col, font=font)
    for led in result.get("leds") or []:
        x, y = float(led["x"]), float(led["y"])
        r = max(6, int(max(led["w"], led["h"]) * 0.4))
        outline = (255, 80, 80) if led.get("state") == "blinking" else (80, 255, 120)
        if led.get("color") == "orange":
            fill_dot = (255, 140, 0)
        elif led.get("color") == "red":
            fill_dot = (255, 40, 40)
        else:
            fill_dot = (200, 200, 200)
        draw.ellipse([x - r, y - r, x + r, y + r], outline=outline, width=2)
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=fill_dot)
        hz = led.get("frequency_hz")
        hz_s = f" {hz:.2f}Hz" if isinstance(hz, (int, float)) else ""
        label = f"#{led['id']} {led.get('color','?')} {led.get('state','?')}{hz_s}"
        draw.text((x + r + 3, y - 8), label, fill=(255, 255, 255), font=font_sm)
        # Colour swatch of the sampled RGB.
        sw = [int(img.width - 36), 8 + 22 * int(led["id"]), int(img.width - 8), 26 + 22 * int(led["id"])]
        draw.rectangle(sw, fill=(int(led["r"]), int(led["g"]), int(led["b"])), outline=(255, 255, 255))
    legend = (
        "circles: green=steady  red-outline=blinking   "
        "dot colour = sampled LED RGB   boxes = boards"
    )
    draw.rectangle([0, img.height - 18, img.width, img.height], fill=(0, 0, 0))
    draw.text((4, img.height - 16), legend, fill=(220, 220, 220), font=font_sm)
    return img


def board_measure_roi(result: dict[str, Any], name: str) -> tuple[int, int, int, int] | None:
    key = name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "nano4k": BOARD_NANO4K,
        "tangnano4k": BOARD_NANO4K,
        "4k": BOARD_NANO4K,
        "primer20k": BOARD_PRIMER20K,
        "20k": BOARD_PRIMER20K,
        "primer": BOARD_PRIMER20K,
    }
    board_name = aliases.get(key)
    if not board_name:
        return None
    board = (result.get("boards") or {}).get(board_name)
    if not board:
        return None
    roi = board.get("measure_roi")
    if not roi:
        return None
    return int(roi["x"]), int(roi["y"]), int(roi["w"]), int(roi["h"])


def board_measurement(result: dict[str, Any], name: str) -> dict[str, Any]:
    """Headline for one board from the shared LED detection.

    Missing board and a board whose LEDs are all steady are results, not errors.
    """
    key = name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "nano4k": BOARD_NANO4K,
        "tangnano4k": BOARD_NANO4K,
        "4k": BOARD_NANO4K,
        "primer20k": BOARD_PRIMER20K,
        "20k": BOARD_PRIMER20K,
        "primer": BOARD_PRIMER20K,
    }
    board_name = aliases.get(key, name)
    board = (result.get("boards") or {}).get(board_name)
    if not board:
        present = sorted((result.get("boards") or {}).keys())
        return {
            "board": board_name,
            "frequency_hz": None,
            "edge_frequency_hz": None,
            "fft_frequency_hz": None,
            "trusted_method": "untrusted",
            "trusted_reason": f"{board_name} not in frame",
            "status": f"{board_name} not in frame",
            "confidence": 0.0,
            "source": "blinking-led",
            "n_leds": 0,
            "n_blinking": 0,
            "boards_present": present,
        }
    status = board.get("status") or (
        "blinking" if board.get("n_blinking") else "board present but not blinking"
    )
    return {
        "board": board_name,
        "frequency_hz": board.get("frequency_hz"),
        "edge_frequency_hz": board.get("edge_frequency_hz"),
        "fft_frequency_hz": board.get("fft_frequency_hz"),
        "trusted_method": board.get("trusted_method"),
        "trusted_reason": board.get("trusted_reason"),
        "status": status,
        "confidence": board.get("confidence"),
        "source": "blinking-led",
        "n_leds": board.get("n_leds"),
        "n_blinking": board.get("n_blinking"),
        "n_steady": board.get("n_steady"),
        "colors": board.get("colors"),
        "target_led_id": board.get("target_led_id"),
        "measure_roi": board.get("measure_roi"),
        "roi": board.get("roi"),
    }


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    boards = {}
    for name, board in (result.get("boards") or {}).items():
        boards[name] = {
            k: v
            for k, v in board.items()
            if k != "leds"
        }
        boards[name]["led_ids"] = [led["id"] for led in board.get("leds", [])]
    leds = []
    for led in result.get("leds") or []:
        leds.append({k: v for k, v in led.items() if k not in {"x0", "y0", "trace"}})
        leds[-1]["x0"] = led["x0"]
        leds[-1]["y0"] = led["y0"]
    return {
        "leds": leds,
        "boards": boards,
        "assign_reason": result.get("assign_reason"),
        "fps": result.get("fps"),
        "n_frames": result.get("n_frames"),
        "video": result.get("video"),
        "width": result.get("width"),
        "height": result.get("height"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LED blob / board geometry helper")
    ap.add_argument("--jpeg", help="score a still JPEG")
    ap.add_argument("--video", help="classify LEDs over a clip")
    ap.add_argument("--annotate", help="write annotated JPEG")
    ap.add_argument("--json", help="write JSON result")
    ap.add_argument("--max-frames", type=int, default=180)
    ap.add_argument("--skip-s", type=float, default=0.0, help="discard this many seconds at the start")
    ap.add_argument("--plot-dir", help="write one chroma plot per blinking LED")
    args = ap.parse_args(argv)
    if args.jpeg:
        metrics = score_jpeg(Path(args.jpeg))
        # blobs are large; keep a summary plus compact blob list
        out = {
            k: v for k, v in metrics.items() if k != "blobs"
        }
        out["blobs"] = [
            {
                "x": round(b["x"], 1),
                "y": round(b["y"], 1),
                "area": b["area"],
                "rgb": [round(b["r"]), round(b["g"]), round(b["b"])],
                "hue": b["hue"],
                "sat": b["sat"],
                "color": b["color"],
                "clip_frac": round(b["clip_frac"], 3),
            }
            for b in metrics["blobs"]
        ]
        text = json.dumps(out, indent=2)
        if args.json:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    if args.video:
        result, still = analyze_video_once(
            Path(args.video), max_frames=args.max_frames, skip_s=args.skip_s
        )
        if args.plot_dir:
            plot_dir = Path(args.plot_dir)
            plot_dir.mkdir(parents=True, exist_ok=True)
            for led in result.get("leds") or []:
                trace = led.get("trace")
                if led.get("state") != "blinking" or not trace:
                    continue
                board = led.get("board") or f"led{led['id']}"
                write_trace_plot(trace, float(result.get("fps") or 30.0), led, plot_dir / f"{board}.png")
        pub = public_result(result)
        if args.annotate:
            annotate(still, result).save(args.annotate, quality=92)
            pub["annotated"] = str(Path(args.annotate).resolve())
        text = json.dumps(pub, indent=2)
        if args.json:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    ap.error("pass --jpeg or --video")
    return 2


if __name__ == "__main__":
    sys.exit(main())
