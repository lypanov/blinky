"""Blink-rate detector arbitration and named ROI parsing.

No numpy/matplotlib. Used by tools/analyze_blink.py and unit tests.
"""

from __future__ import annotations

# Hardware Blink3 LightToggle delay. 27 MHz / (262144 * 30) = 3.433 Hz.
# 30 cycles/iteration matches the Nano 4K measurement notes (3.433–3.437 Hz).
CLOCK_HZ = 27_000_000
BLINK3_MAX_ITERATIONS = 262_144
BLINK3_CYCLES_PER_ITERATION = 30.0
PREDICTED_BLINK3_HZ = CLOCK_HZ / (BLINK3_MAX_ITERATIONS * BLINK3_CYCLES_PER_ITERATION)

# Future dual-board: LEDs are a clear top/bottom split in the Logitech frame.
# These names only restrict the auto-ROI search window; they do not run two meters.
REGION_ALIASES = {
    "auto": "auto",
    "all": "auto",
    "default": "auto",
    "full": "full",
    "top": "top",
    "bottom": "bottom",
    # Bee's current desk: Primer 20K above, Tang Nano 4K below.
    "nano4k": "bottom",
    "tang-nano-4k": "bottom",
    "tangnano4k": "bottom",
    "4k": "bottom",
    "primer20k": "top",
    "primer-20k": "top",
    "20k": "top",
}


def predicted_blink3() -> dict[str, float | int | str]:
    return {
        "program": "Blink3",
        "max_iterations": BLINK3_MAX_ITERATIONS,
        "clock_hz": CLOCK_HZ,
        "cycles_per_iteration": BLINK3_CYCLES_PER_ITERATION,
        "frequency_hz": PREDICTED_BLINK3_HZ,
        "note": (
            "Blink3 LightToggle N=262144 at 27 MHz, 30 cycles/iteration "
            f"→ {PREDICTED_BLINK3_HZ:.3f} Hz (Nano 4K hardware notes)."
        ),
    }


def parse_roi_arg(spec: str | None) -> tuple[str, tuple[int, int, int, int] | None]:
    """Return (kind, manual_xywh).

    kind is auto|full|top|bottom|manual. manual_xywh is set only for x,y,w,h.
    """
    if spec is None:
        return "auto", None
    text = spec.strip()
    if not text:
        return "auto", None
    key = text.lower().replace(" ", "")
    if key in REGION_ALIASES:
        return REGION_ALIASES[key], None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError(
            "roi must be auto, full, top, bottom, nano4k, primer20k, or x,y,w,h"
        )
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError("roi x,y,w,h must be integers") from exc
    if w <= 0 or h <= 0:
        raise ValueError("roi width/height must be positive")
    return "manual", (x, y, w, h)


def search_window(
    kind: str, width: int, height: int
) -> tuple[int, int, int, int]:
    """Pixel rect to auto-find the LED in. top/bottom split the frame in half."""
    if kind == "top":
        return 0, 0, width, max(1, height // 2)
    if kind == "bottom":
        y = height // 2
        return 0, y, width, max(1, height - y)
    return 0, 0, width, height


def choose_trusted(
    *,
    edge_hz: float | None,
    fft_hz: float | None,
    fft_snr: float,
    edge_count: int,
    duration_s: float,
) -> tuple[str, str]:
    """Pick edge/threshold vs FFT. FFT wins when edges undercount (the ~6.9 Hz case)."""
    if edge_hz is None and not fft_hz:
        return "none", "neither detector found a blink"
    if edge_hz is None:
        return "fft", "edge detector found no period; using FFT peak"
    if not fft_hz:
        return "edge", "FFT had no peak; using edge/threshold period"

    rel = abs(edge_hz - fft_hz) / max(edge_hz, fft_hz)
    expected_edges = duration_s * fft_hz * 2.0  # rising + falling
    undercount = duration_s > 0 and edge_count < 0.7 * expected_edges
    if fft_snr >= 4.0 and (undercount or rel > 0.12):
        why = "edge detector undercounted" if undercount else "edge and FFT disagree"
        return "fft", f"{why}; trusting FFT peak (snr={fft_snr:.1f})"
    if fft_snr < 4.0:
        return "edge", "FFT SNR is weak; using edge/threshold period"
    return "edge", "edge/threshold period agrees with FFT"
