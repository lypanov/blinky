#!/usr/bin/env python3
"""Pin LED vs CPU LED register vs UART press latch."""

from __future__ import annotations

import argparse
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path: str):
    cycles, pin, cpu, pressed = [], [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            cycles.append(int(row["cycle"]))
            pin.append(int(row["led"]))
            cpu.append(int(row["cpu_led"]))
            pressed.append(int(row["pressed"]))
    return cycles, pin, cpu, pressed


def steps(xs, ys):
    px, py = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        px.append(xs[i])
        py.append(ys[i - 1])
        px.append(xs[i])
        py.append(ys[i])
    px.append(xs[-1] + 1)
    py.append(ys[-1])
    return px, py


def shade(ax, cycles, pressed):
    on = None
    for c, p in zip(cycles, pressed):
        if p and on is None:
            on = c
        elif not p and on is not None:
            ax.axvspan(on, c, color="#6b1a2a", alpha=0.35, lw=0)
            on = None
    if on is not None:
        ax.axvspan(on, cycles[-1], color="#6b1a2a", alpha=0.35, lw=0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--title", default="UART LED gate")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    cycles, pin, cpu, pressed = load(args.csv)
    fig, axes = plt.subplots(3, 1, figsize=(14, 6.2), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 0.7]})
    fig.patch.set_facecolor("#0b1220")
    series = (
        (axes[0], pin, "LED pin", "#3dff9a"),
        (axes[1], cpu, "CPU LED register", "#7eb6ff"),
        (axes[2], pressed, "gate pressed", "#ffb020"),
    )
    for ax, ys, name, color in series:
        ax.set_facecolor("#10192b")
        ax.tick_params(colors="#c8d3e8")
        for spine in ax.spines.values():
            spine.set_color("#2a3b5c")
        shade(ax, cycles, pressed)
        px, py = steps(cycles, ys)
        ax.plot(px, py, color=color, lw=1.6)
        ax.set_ylim(-0.15, 1.25)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["0", "1"])
        ax.set_ylabel(name, color="#c8d3e8")
        ax.grid(True, axis="x", color="#24344f", lw=0.6)
    axes[2].set_xlabel("cycle after reset", color="#c8d3e8")
    fig.suptitle(args.title, color="#e8eefc", fontsize=13)
    if args.note:
        fig.text(0.01, 0.01, args.note, color="#9eb0cc", fontsize=8, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(args.png, dpi=120)
    print(f"[plot] {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
