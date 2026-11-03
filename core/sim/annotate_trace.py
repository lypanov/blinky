#!/usr/bin/env python3
"""Enrich the Verilator Blink2 trace with RISC5 disassembly and Oberon source."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from instruction_parser import disassemble  # noqa: E402

# CPUSubset0 setup / halt image (byte addresses). See CPUSubset0.scala.
SETUP = [
    (0x80, 0x4E000080, "(trap/setup) MOV SP, #0x80  ; stack pointer"),
    (0x84, 0x4F0000A0, "(trap/setup) MOV LNK, #0xA0 ; return-to-halt"),
    (0x88, 0x40000000, "(trap/setup) MOV R0, #0     ; user entry"),
    (0x8C, 0xC7000000, "(trap/setup) BT R0          ; jump to Blink2"),
]
HALT_START = 0xA0
HALT_END = 0xB0
HALT_WORD = 0xE7FFFFFF

# Map user-program PCs (Blink2test.asm) onto Blink2test.Mod lines.
# Indices are instruction numbers in tests/Blink2test.code (addr = i*4).
USER_SOURCE = {
    0: (None, "compiler prologue: SUB SP, 4"),
    1: (None, "compiler prologue: save LNK"),
    2: (8, "light := 0"),
    3: (8, "SB := 0x10  (R13-from-R0 load hack)"),
    4: (8, "light := 0"),
    5: (9, "counter := 0"),
    6: (9, "counter := 0"),
    7: (10, "maxIterations := 5   ; sim-only delay (hw uses 524288)"),
    8: (10, "maxIterations := 5"),
    9: (12, "WHILE TRUE DO"),
    10: (13, "INC(counter)"),
    11: (13, "INC(counter)"),
    12: (13, "INC(counter)"),
    13: (13, "INC(counter)"),
    14: (13, "INC(counter)"),
    15: (14, "IF counter >= maxIterations THEN"),
    16: (14, "IF counter >= maxIterations THEN"),
    17: (14, "IF counter >= maxIterations THEN"),
    18: (14, "IF counter >= maxIterations THEN  ; BLT skips toggle"),
    19: (15, "light := 1 - light"),
    20: (15, "light := 1 - light"),
    21: (15, "light := 1 - light"),
    22: (15, "light := 1 - light"),
    23: (15, "light := 1 - light  ; STW light -> 0x10 toggles LED"),
    24: (16, "counter := 0"),
    25: (16, "counter := 0"),
    26: (12, "END  ; BT back to WHILE"),
    27: (None, "compiler epilogue: restore LNK"),
    28: (None, "compiler epilogue: restore SP"),
    29: (None, "compiler epilogue: BT LNK (halt at 0xA0)"),
}


def load_mod_lines() -> list[str]:
    path = os.path.join(ROOT, "tests", "Blink2test.Mod")
    with open(path) as f:
        return [line.rstrip("\n") for line in f]


def load_user_code() -> list[int]:
    path = os.path.join(ROOT, "tests", "Blink2test.code")
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            words.append(int(line.replace("0x", ""), 16))
    return words


def pretty_disasm(word: int) -> str:
    text = disassemble(word)
    return text if text is not None else f".word 0x{word:08x}"


def build_program() -> list[dict]:
    mod = load_mod_lines()
    user = load_user_code()
    entries = []

    def add(addr: int, word: int, file: str | None, line: int | None, note: str | None):
        src = None
        if line is not None and 1 <= line <= len(mod):
            src = mod[line - 1].strip()
        entries.append({
            "addr": addr,
            "hex": f"{word:08x}",
            "disasm": pretty_disasm(word),
            "file": file,
            "line": line,
            "src": src,
            "note": note,
        })

    for i, word in enumerate(user):
        addr = i * 4
        line, note = USER_SOURCE.get(i, (None, None))
        add(addr, word, "tests/Blink2test.Mod" if line else None, line, note)

    for addr, word, note in SETUP:
        add(addr, word, None, None, note)

    for addr in range(HALT_START, HALT_END, 4):
        add(addr, HALT_WORD, None, None, "halt (branch-self)")

    return entries, mod


def lookup(program: list[dict], pc: int) -> dict | None:
    for e in program:
        if e["addr"] == pc:
            return e
    return None


def annotate(trace: dict, program: list[dict]) -> dict:
    for cyc in trace.get("cycles", []):
        pc = int(cyc.get("pc", 0))
        info = lookup(program, pc)
        if info:
            cyc["disasm"] = info["disasm"]
            cyc["hex"] = info["hex"]
            cyc["src"] = info["src"]
            cyc["srcLine"] = info["line"]
            cyc["note"] = info["note"]
        else:
            cyc["disasm"] = f"(pc 0x{pc:x} outside image)"
            cyc["hex"] = None
            cyc["src"] = None
            cyc["srcLine"] = None
            cyc["note"] = None
    return trace


def summarize(trace: dict) -> dict:
    edges = trace.get("led_toggles") or []
    periods = [edges[i] - edges[i - 1] for i in range(1, len(edges))]
    mean = (sum(periods) / len(periods)) if periods else None
    return {
        "toggle_cycles": edges,
        "periods": periods,
        "mean_period": mean,
        "n_cycles": len(trace.get("cycles", [])),
        "treadle_reference_cycles": 81,
        "treadle_reference_note": (
            "CPUSubset0Test blink2_code_test asserts average period == 81 "
            "on Treadle with maxIterations=5. Informal notes say ~89; both "
            "describe the same short-delay Blink2test image."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--wave", required=True)
    ap.add_argument("--program", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--visualizer")
    args = ap.parse_args()

    program, mod = build_program()
    with open(args.trace) as f:
        trace = json.load(f)

    trace = annotate(trace, program)
    summary = summarize(trace)
    trace["summary"] = summary
    trace["mod_source"] = mod
    trace["mod_file"] = "tests/Blink2test.Mod"

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(trace, f, indent=2)
        f.write("\n")

    with open(args.program, "w") as f:
        json.dump({"entries": program, "mod_source": mod, "mod_file": "tests/Blink2test.Mod"}, f, indent=2)
        f.write("\n")

    if args.visualizer:
        vis_dir = os.path.dirname(args.visualizer)
        os.makedirs(vis_dir, exist_ok=True)
        with open(args.visualizer, "w") as f:
            json.dump(trace, f)
            f.write("\n")
        vis_prog = os.path.join(vis_dir, "program.json")
        with open(vis_prog, "w") as f:
            json.dump({"entries": program, "mod_source": mod, "mod_file": "tests/Blink2test.Mod"}, f)
            f.write("\n")

    print("[annotate] instructions:", len(program))
    print("[annotate] cycles:", summary["n_cycles"])
    print("[annotate] LED edges at cycles:", summary["toggle_cycles"])
    print("[annotate] periods:", summary["periods"])
    if summary["mean_period"] is not None:
        print("[annotate] mean period: %.2f cycles (Treadle reference %d)" % (
            summary["mean_period"], summary["treadle_reference_cycles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
