#!/usr/bin/env python3
"""Check Blink3 LED edge spacing against 15N+18 cycles."""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imem_layout import blink3_cycles_per_edge, blink3_predicted_hz  # noqa: E402


def load_edges(path: str) -> list[int]:
    edges = []
    with open(path) as f:
        for row in csv.DictReader(f):
            edges.append(int(row["cycle"]))
    return edges


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--toggles", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pred = blink3_cycles_per_edge(args.n)
    edges = load_edges(args.toggles)
    periods = [edges[i] - edges[i - 1] for i in range(1, len(edges))]
    hz = blink3_predicted_hz(args.n)
    match = bool(periods) and all(p == pred for p in periods)
    lines = [
        f"N={args.n}",
        "formula=15*N+18",
        f"predicted_cycles_per_edge={pred}",
        f"edges={' '.join(str(c) for c in edges)}",
        f"periods={' '.join(str(p) for p in periods)}",
        f"clock_hz={hz['clock_hz']}",
        f"predicted_edge_hz={hz['toggle_rate_hz']:.6f}",
        f"predicted_blink_hz={hz['frequency_hz']:.6f}",
        f"match={'yes' if match else 'no'}",
        "",
    ]
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(text)
    print(text, end="")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
