#!/usr/bin/env python3
"""Draw a GTKWave-style digital timing diagram of the Blink2 LED from sim CSV."""

from __future__ import annotations

import argparse
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def load_wave(path: str):
    cycles, led, pc = [], [], []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            cycles.append(int(row["cycle"]))
            led.append(int(row["led"]))
            pc.append(int(row["pc"]))
    return cycles, led, pc


def load_toggles(path: str):
    edges = []
    if not os.path.exists(path):
        return edges
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            edges.append((int(row["cycle"]), int(row["led_next"])))
    return edges


def digital_steps(xs, ys):
    """Expand a sampled 0/1 signal into a stairstep polyline."""
    if not xs:
        return [], []
    px, py = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        px.append(xs[i])
        py.append(ys[i - 1])
        px.append(xs[i])
        py.append(ys[i])
    px.append(xs[-1] + 1)
    py.append(ys[-1])
    return px, py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--toggles", required=True)
    ap.add_argument("--png", required=True)
    args = ap.parse_args()

    cycles, led, pc = load_wave(args.csv)
    edges = load_toggles(args.toggles)
    if not cycles:
        raise SystemExit("empty wave CSV")

    periods = [edges[i][0] - edges[i - 1][0] for i in range(1, len(edges))]
    mean = (sum(periods) / len(periods)) if periods else None

    fig, axes = plt.subplots(2, 1, figsize=(14, 5.2), sharex=True,
                             gridspec_kw={"height_ratios": [1.2, 1.6]})
    fig.patch.set_facecolor("#0b1220")
    for ax in axes:
        ax.set_facecolor("#10192b")
        ax.tick_params(colors="#c8d3e8")
        for spine in ax.spines.values():
            spine.set_color("#2a3b5c")
        ax.yaxis.label.set_color("#d7e3f7")
        ax.xaxis.label.set_color("#d7e3f7")
        ax.title.set_color("#e8eefc")
        ax.grid(True, color="#1e2d48", linestyle="--", linewidth=0.6)

    x, y = digital_steps(cycles, led)
    axes[0].plot(x, y, color="#39ff88", linewidth=1.8, solid_capstyle="butt")
    axes[0].fill_between(x, y, 0, color="#39ff88", alpha=0.12, step=None)
    axes[0].set_ylim(-0.15, 1.25)
    axes[0].set_yticks([0, 1])
    axes[0].set_yticklabels(["OFF (0)", "ON (1)"])
    axes[0].set_ylabel("io_led")
    title = "Blink2 LED (Verilator, sim delay maxIterations=5)"
    if mean is not None:
        title += f"  —  mean period {mean:.1f} cycles"
    axes[0].set_title(title)

    for cyc, _val in edges:
        axes[0].axvline(cyc, color="#ffcc66", alpha=0.45, linewidth=0.8)
        axes[0].text(cyc, 1.12, f"{cyc}", color="#ffcc66", fontsize=8,
                     ha="center", va="bottom")

    axes[1].plot(cycles, pc, color="#6cb6ff", linewidth=1.1)
    axes[1].set_ylabel("PC")
    axes[1].set_xlabel("cycle (after reset)")
    axes[1].yaxis.set_major_formatter(lambda v, _p: f"0x{int(v):X}")

    # Highlight the user Blink2 loop vs setup (PC starts at 0x80).
    setup_band = Rectangle((cycles[0], 0x80), cycles[-1] - cycles[0] + 1, 0x30,
                           facecolor="#ff8866", alpha=0.08, edgecolor=None)
    axes[1].add_patch(setup_band)
    axes[1].text(cycles[0] + 2, 0xA4, "setup/halt 0x80–0xB0", color="#ffaa88", fontsize=8)

    note = "Treadle blink2_code_test: 81-cycle average. Hardware Blink2hw delay is 524288 (not used here)."
    if periods:
        note = f"Periods between LED edges: {periods}    " + note
    fig.text(0.01, 0.01, note, color="#9aabc4", fontsize=8)

    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs(os.path.dirname(args.png) or ".", exist_ok=True)
    fig.savefig(args.png, dpi=140)
    print(f"[plot] wrote {args.png}")
    if mean is not None:
        print(f"[plot] mean LED period = {mean:.2f} cycles  edges={ [e[0] for e in edges] }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
