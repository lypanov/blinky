#!/usr/bin/env python3
"""Check a UartLedGate Verilator wave.

The CPU LED register must keep a 15N+18 edge period straight through the
press. The pin must be 0 for every cycle the latch is set, and equal to
the register on every cycle it is clear (release resumes in phase).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys


def load(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append({
                "cycle": int(row["cycle"]),
                "led": int(row["led"]),
                "cpu_led": int(row["cpu_led"]),
                "pressed": int(row["pressed"]),
                "pc": int(row["pc"]),
            })
    return rows


def edges(rows: list[dict], key: str) -> list[int]:
    out = []
    for i in range(1, len(rows)):
        if rows[i][key] != rows[i - 1][key]:
            out.append(rows[i]["cycle"])
    return out


def rising(rows: list[dict], key: str) -> list[int]:
    return [rows[i]["cycle"] for i in range(1, len(rows))
            if rows[i][key] and not rows[i - 1][key]]


def falling(rows: list[dict], key: str) -> list[int]:
    return [rows[i]["cycle"] for i in range(1, len(rows))
            if not rows[i][key] and rows[i - 1][key]]


def thin_cycles(cycles: list[dict], press: int, release: int) -> list[dict]:
    """Keep boot, the cut, the release, and one step per CPU edge in between."""
    kept = []
    prev_cpu = None
    for c in cycles:
        cyc = int(c.get("cycle") or 0)
        cpu = c.get("cpu_led")
        edge = prev_cpu is not None and cpu != prev_cpu
        prev_cpu = cpu
        if (
            cyc <= 600
            or abs(cyc - press) <= 200
            or (release - 80) <= cyc <= (release + 400)
            or (press < cyc < release and edge)
        ):
            kept.append(c)
    return kept or cycles


def patch_visualizer(path: str, info: dict) -> None:
    with open(path) as f:
        trace = json.load(f)
    cycles = thin_cycles(
        trace.get("cycles") or [],
        int(info["press_cycle"]),
        int(info["release_cycle"]),
    )
    trace["cycles"] = cycles
    trace["clocks_sampled"] = trace.get("clocks_sampled")
    forced = next((i for i, c in enumerate(cycles)
                   if c.get("pressed") and c.get("cpu_led")), None)
    resume = None
    seen = False
    for i, c in enumerate(cycles):
        if c.get("pressed"):
            seen = True
        elif seen and c.get("led"):
            resume = i
            break
    info = dict(info)
    info["forced_off_step"] = forced
    info["resume_step"] = resume
    trace["uart"] = info
    trace["title"] = "Blink3 N=%d — UART press forces the LED pin off" % info["n"]
    trace["subtitle"] = (
        "0x01 latches press, 0x00 releases. The CPU LED register keeps "
        "the 15N+18 phase; the pin follows it again on release."
    )
    with open(path, "w") as f:
        json.dump(trace, f)
        f.write("\n")
    if forced is None or resume is None:
        raise SystemExit(f"visualizer trace has no press/release step ({path})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--visualizer", default="")
    args = ap.parse_args()

    sys.path.insert(0, "sim")
    from imem_layout import blink3_cycles_per_edge
    predict = blink3_cycles_per_edge(args.n)

    rows = load(args.wave)
    if len(rows) < 100:
        raise SystemExit("wave too short")

    cpu_e = edges(rows, "cpu_led")
    pin_e = edges(rows, "led")
    cpu_periods = [b - a for a, b in zip(cpu_e, cpu_e[1:])]
    press_at = rising(rows, "pressed")
    release_at = falling(rows, "pressed")
    problems = []

    if len(press_at) != 1:
        problems.append(f"expected one press latch, got {press_at}")
    if len(release_at) != 1:
        problems.append(f"expected one release, got {release_at}")
    if cpu_periods and any(p != predict for p in cpu_periods):
        bad = [p for p in cpu_periods if p != predict]
        problems.append(f"CPU LED period left {predict}: {bad[:8]}")
    if len(cpu_e) < 8:
        problems.append(f"only {len(cpu_e)} CPU LED edges")

    pressed_rows = [r for r in rows if r["pressed"]]
    if not pressed_rows:
        problems.append("press latch never set")
    elif any(r["led"] for r in pressed_rows):
        problems.append("pin was high while pressed")
    cpu_edges_while_pressed = [
        c for c in cpu_e
        if pressed_rows and pressed_rows[0]["cycle"] <= c <= pressed_rows[-1]["cycle"]
    ]
    if len(cpu_edges_while_pressed) < 4:
        problems.append(
            f"CPU LED barely moved during press ({len(cpu_edges_while_pressed)} edges)"
        )
    pcs = {r["pc"] for r in pressed_rows}
    if len(pcs) < 3:
        problems.append("PC stalled during press")

    released = [r for r in rows if not r["pressed"]]
    mismatch = [r["cycle"] for r in released if r["led"] != r["cpu_led"]]
    if mismatch:
        problems.append(f"pin != CPU LED while released, first cycles {mismatch[:6]}")

    resume_cycle = release_at[0] if release_at else None
    resume_row = next((r for r in rows if resume_cycle is not None and r["cycle"] == resume_cycle), None)
    in_phase = bool(resume_row and resume_row["led"] == resume_row["cpu_led"])
    if resume_row and not in_phase:
        problems.append(
            f"release cycle {resume_cycle} pin={resume_row['led']} cpu_led={resume_row['cpu_led']}"
        )

    # The next CPU edge after release must also be a pin edge (same cycle).
    if resume_cycle is not None:
        nxt = next((c for c in cpu_e if c > resume_cycle), None)
        if nxt is None or nxt not in pin_e:
            problems.append(f"CPU edge after release ({nxt}) was not a pin edge")

    text = "\n".join([
        f"N={args.n}",
        f"formula=15*N+18",
        f"predicted_cpu_cycles_per_edge={predict}",
        f"cpu_edges={' '.join(str(c) for c in cpu_e)}",
        f"cpu_periods={' '.join(str(p) for p in cpu_periods)}",
        f"pin_edges={' '.join(str(c) for c in pin_e)}",
        f"press_cycle={press_at[0] if press_at else ''}",
        f"release_cycle={release_at[0] if release_at else ''}",
        f"cpu_edges_while_pressed={len(cpu_edges_while_pressed)}",
        f"pressed_cycles={len(pressed_rows)}",
        f"release_cpu_led={resume_row['cpu_led'] if resume_row else ''}",
        f"release_pin={resume_row['led'] if resume_row else ''}",
        f"in_phase={'yes' if in_phase else 'no'}",
        f"match={'yes' if not problems else 'no'}",
    ])
    if problems:
        text += "\n" + "\n".join(f"problem: {p}" for p in problems)
    text += "\n"
    with open(args.out, "w") as f:
        f.write(text)
    print(text, end="")

    if args.visualizer and not problems:
        patch_visualizer(args.visualizer, {
            "n": args.n,
            "predict": predict,
            "press_cycle": press_at[0],
            "release_cycle": release_at[0],
            "cpu_period": predict,
            "cpu_edges_while_pressed": len(cpu_edges_while_pressed),
            "pressed_cycles": len(pressed_rows),
            "release_cpu_led": resume_row["cpu_led"] if resume_row else None,
            "in_phase": in_phase,
            "protocol": "8N1 115200 at 27 MHz; press 0x01 / '1' / space; release 0x00 / '0'",
        })
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
