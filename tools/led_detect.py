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
MERGE_PX = 12.0
MIN_BLOB_AREA = 4
MAX_BLOB_AREA = 280
MAX_BLOB_SPAN = 48


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
        proc.stdout.close()
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
        hit["x"] = (hit["x"] * hit["area"] + blob["x"] * blob["area"]) / n
        hit["y"] = (hit["y"] * hit["area"] + blob["y"] * blob["area"]) / n
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
        if blob["area"] > 220:
            extra = blob["area"] - 220
            bloom += extra
            score -= 0.05 * extra
        if blob["clip_frac"] > 0.40 and blob["area"] > 60:
            score -= 22.0
        if blob["peak_r"] < 80:
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
    if clip_hi > 0.004:
        score -= 500.0 * clip_hi
    if n < 2:
        score -= 30.0
    if n > 6:
        score -= 5.0 * (n - 6)
    return {
        "score": round(float(score), 2),
        "n_blobs": n,
        "mean_luma": round(mean_luma, 2),
        "clip_hi_frac": round(clip_hi, 5),
        "has_red": "red" in colors,
        "has_orange": "orange" in colors,
        "bloom_px": round(bloom, 1),
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
    # Ignore DC and very slow wander; LEDs here blink a few Hz.
    keep = (freqs >= 0.6) & (freqs <= min(12.0, fps / 2.2))
    if not np.any(keep):
        return None, 0.0
    band = spec[keep]
    peak_i = int(np.argmax(band))
    peak = float(band[peak_i])
    med = float(np.median(band)) if band.size else 0.0
    snr = peak / max(med, 1e-6)
    hz = float(freqs[keep][peak_i])
    return (hz if snr >= 2.5 else None), snr


def classify_temporal(series: np.ndarray, fps: float) -> tuple[str, float | None, float]:
    x = np.asarray(series, dtype=np.float64)
    if len(x) < 8:
        return "unknown", None, 0.0
    mean = float(x.mean())
    std = float(x.std())
    ptp = float(x.max() - x.min())
    cv = std / max(abs(mean), 1e-6)
    hz, snr = fft_peak_hz(x, fps)
    if cv >= 0.16 and ptp >= 18.0:
        return "blinking", hz, cv
    if hz is not None and snr >= 6.0 and cv >= 0.14 and ptp >= 15.0:
        return "blinking", hz, cv
    if mean >= 10.0:
        return "steady", None, cv
    return "unknown", None, cv


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
    if len(groups) == 1 and len(leds) >= 4:
        split = _split_by_largest_gap(leds)
        if len(split) == 2:
            groups = split
    if len(groups) > 2:
        groups = sorted(groups, key=lambda g: -len(g))[:2]

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
        boards = {name: _board_record(name, only["members"])}
        return {"boards": boards, "reason": "single cluster", "clusters": scored}

    # Relative layout is preserved: Primer 20K stays above Nano 4K. Count and
    # colour are evidence, not allowed to invert the names.
    a, b = scored[0], scored[1]
    upper, lower = (a, b) if a["cy"] < b["cy"] else (b, a)
    boards = {
        BOARD_PRIMER20K: _board_record(BOARD_PRIMER20K, upper["members"]),
        BOARD_NANO4K: _board_record(BOARD_NANO4K, lower["members"]),
    }
    reason = (
        f"upper=primer20k n={upper['n']} orange={upper['n_orange']} "
        f"lower=nano4k n={lower['n']} orange={lower['n_orange']} "
        f"cy={upper['cy']:.0f}/{lower['cy']:.0f}"
    )
    return {"boards": boards, "reason": reason, "clusters": scored}


def _board_record(name: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    xs = [m["x"] for m in members]
    ys = [m["y"] for m in members]
    pad = 12
    x0 = max(0, int(min(m["x0"] for m in members) - pad))
    y0 = max(0, int(min(m["y0"] for m in members) - pad))
    x1 = int(max(m["x0"] + m["w"] for m in members) + pad)
    y1 = int(max(m["y0"] + m["h"] for m in members) + pad)
    blinkers = [m for m in members if m.get("state") == "blinking"]
    if blinkers:
        target = max(blinkers, key=lambda m: float(m.get("cv") or 0))
    else:
        target = max(members, key=lambda m: m.get("sat", 0))
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))
    orientation = _orientation(members, cx, cy)
    board_roi = {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}
    # Meter the whole board so analyze_blink sees the blinker among neighbours.
    return {
        "name": name,
        "cx": round(cx, 1),
        "cy": round(cy, 1),
        "roi": board_roi,
        "measure_roi": board_roi,
        "target_led_id": target.get("id"),
        "n_leds": len(members),
        "n_blinking": sum(1 for m in members if m.get("state") == "blinking"),
        "n_steady": sum(1 for m in members if m.get("state") == "steady"),
        "colors": sorted({m.get("color", "other") for m in members}),
        "orientation": orientation,
        "leds": members,
    }


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


def _keep_likely_leds(
    leds: list[dict[str, Any]],
    limit: int = 6,
    frame_wh: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Drop reflections / silk; keep blinking spots and bright red/orange cores."""
    w = h = None
    if frame_wh:
        w, h = frame_wh
    kept: list[dict[str, Any]] = []
    for led in leds:
        if w and h:
            if led["y"] > 0.88 * h or led["y"] < 0.05 * h:
                continue
            if led["x"] < 0.08 * w or led["x"] > 0.92 * w:
                continue
        if led.get("state") == "blinking":
            kept.append(led)
            continue
        if led.get("color") not in ("red", "orange"):
            continue
        if float(led.get("mean_chroma") or 0) < 18.0 and float(led.get("sat") or 0) < 0.35:
            continue
        kept.append(led)
    kept.sort(
        key=lambda led: (
            1 if led.get("state") == "blinking" else 0,
            float(led.get("mean_chroma") or 0),
            float(led.get("sat") or 0),
        ),
        reverse=True,
    )
    return kept[:limit]


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
    blobs = detect_blobs(max_rgb)
    # Also pick up blink-only spots that the max-projection mask may split.
    extra_mask = std_rg >= max(8.0, float(np.percentile(std_rg, 99.2)))
    extra = _connected_components(extra_mask, 3, 400)
    for pix in extra:
        ys, xs = pix[:, 0], pix[:, 1]
        x, y = float(xs.mean()), float(ys.mean())
        if any((x - b["x"]) ** 2 + (y - b["y"]) ** 2 < MERGE_PX ** 2 for b in blobs):
            continue
        yy = min(max_rgb.shape[0] - 1, max(0, int(round(y))))
        xx = min(max_rgb.shape[1] - 1, max(0, int(round(x))))
        peak = max_rgb[yy, xx]
        blobs.append(
            {
                "x": x,
                "y": y,
                "x0": int(xs.min()),
                "y0": int(ys.min()),
                "w": int(xs.max() - xs.min() + 1),
                "h": int(ys.max() - ys.min() + 1),
                "area": int(len(pix)),
                "r": float(peak[0]),
                "g": float(peak[1]),
                "b": float(peak[2]),
                "hue": round(rgb_to_hsv(*peak.tolist())[0], 1),
                "sat": round(rgb_to_hsv(*peak.tolist())[1], 3),
                "peak_r": float(peak[0]),
                "clip_frac": 0.0,
                "color": classify_led_color(*peak.tolist()),
                "luma": float(np.mean(peak)),
            }
        )
    blobs = _merge_nearby(blobs)

    leds: list[dict[str, Any]] = []
    for i, blob in enumerate(blobs):
        series = np.array(
            [sample_disk(frame, blob["x"], blob["y"])[3] for frame in frames],
            dtype=np.float32,
        )
        state, hz, cv = classify_temporal(series, fps)
        # Re-sample colour from the brightest frame at this location.
        peak_frame = frames[int(np.argmax(series))]
        sample = sample_disk(peak_frame, blob["x"], blob["y"], radius=3)
        color = classify_led_color(float(sample[0]), float(sample[1]), float(sample[2]))
        hue, sat, _v = rgb_to_hsv(float(sample[0]), float(sample[1]), float(sample[2]))
        leds.append(
            {
                "id": i,
                "x": round(float(blob["x"]), 1),
                "y": round(float(blob["y"]), 1),
                "x0": int(blob["x0"]),
                "y0": int(blob["y0"]),
                "w": int(blob["w"]),
                "h": int(blob["h"]),
                "area": int(blob["area"]),
                "r": round(float(sample[0]), 1),
                "g": round(float(sample[1]), 1),
                "b": round(float(sample[2]), 1),
                "hue": round(hue, 1),
                "sat": round(sat, 3),
                "color": color,
                "state": state,
                "frequency_hz": None if hz is None else round(float(hz), 3),
                "cv": round(float(cv), 3),
                "mean_chroma": round(float(series.mean()), 2),
            }
        )

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


def analyze_video_once(path: Path, max_frames: int = 180) -> tuple[dict[str, Any], np.ndarray]:
    width, height, fps, duration = probe_video(path)
    frames = []
    for i, frame in enumerate(iter_rgb_frames(str(path), width, height)):
        frames.append(frame)
        if i + 1 >= max_frames:
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
    roi = board.get("measure_roi") or board.get("roi")
    return int(roi["x"]), int(roi["y"]), int(roi["w"]), int(roi["h"])


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
        leds.append({k: v for k, v in led.items() if k not in {"x0", "y0"}})
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
        result, still = analyze_video_once(Path(args.video), max_frames=args.max_frames)
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
