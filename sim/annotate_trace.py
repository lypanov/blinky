#!/usr/bin/env python3
"""Enrich a Verilator CPUSimTop trace with RISC5 disassembly and Oberon source.

Used for both Blink2 (default IMEM) and Blink3 (linked image). Labels what
the sim actually did.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))
from instruction_parser import disassemble  # noqa: E402
from imem_layout import (  # noqa: E402
    BLINK3_AMMT_BODY,
    BLINK3_BL_PC,
    BLINK3_ENTRY,
    BLINK3_LIGHT_ADDR,
    BLINK3_MAXITER,
    BLINK3_MAXITER_ADDR,
    BLINK3_MAXITER_PC,
    BLINK3_MAXITER_STORE_PC,
    BLINK3_MHI_WORD,
    BLINK3_RETURN,
    BLINK3_TOGGLE,
    BLINK3_WRONG_LAND,
    HALT_END,
    HALT_START,
    HALT_WORD,
    SETUP,
    blink3_startup_trampoline,
)

WATCH_ADDRS = {
    0x10: "LED snoop / old light",
    0x14: "MT[1] (AMMT vars ptr)",
    0x18: "MT[2] (LightToggle vars ptr)",
    0x50: "AMMT light (MT[1])",
    0x70: "LightToggle counter",
    0x74: "LightToggle maxIterations",
}


_COND = ["MI", "EQ", "CS", "VS", "LS", "LT", "LE", "always",
         "PL", "NE", "CC", "VC", "HI", "GE", "GT", "never"]


def pretty_disasm(word: int) -> str:
    """Prefer 'BL always' over the parser's 'BLT' (which collides with less-than)."""
    fmt = (word >> 28) & 0xF
    if fmt in (0xC, 0xD, 0xE, 0xF):
        v = fmt & 1
        cond = (word >> 24) & 0xF
        name = ("BL" if v else "B") + " " + _COND[cond]
        if fmt in (0xC, 0xD):
            return f"{name} R{word & 0xF}"
        off = word & 0xFFFFFF
        if off & 0x800000:
            off -= 0x1000000
        return f"{name}, off={off}"
    text = disassemble(word)
    return text if text is not None else f".word 0x{word:08x}"


def load_lines(rel: str) -> list[str]:
    path = os.path.join(ROOT, rel)
    with open(path) as f:
        return [line.rstrip("\n") for line in f]


def load_code_words(rel: str) -> list[int]:
    path = os.path.join(ROOT, rel)
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("="):
                continue
            if ":" in line and line.startswith("0x"):
                line = line.split(":", 1)[1].strip().split()[0]
            words.append(int(line.replace("0x", ""), 16))
    return words


def load_words_file(path: str) -> list[int]:
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                words.append(int(line, 16))
    return words


def entry(addr, word, file=None, line=None, src=None, note=None, mark=None):
    return {
        "addr": addr,
        "hex": f"{word:08x}",
        "disasm": pretty_disasm(word),
        "file": file,
        "line": line,
        "src": src,
        "note": note,
        "mark": mark,
    }


# Blink2test.Mod line numbers for user-program word index i (addr = i*4).
BLINK2_SOURCE = {
    0: (None, "compiler prologue: SUB SP, 4"),
    1: (None, "compiler prologue: save LNK"),
    2: (8, "light := 0"),
    3: (8, "SB := MT[1]  (LDW R13, [R12, 4])"),
    4: (8, "light := 0  ; STW -> 0x50, LED snoop"),
    5: (9, "counter := 0"),
    6: (9, "counter := 0"),
    7: (10, "maxIterations := 5"),
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
    23: (15, "light := 1 - light  ; STW light -> 0x50 toggles LED"),
    24: (16, "counter := 0"),
    25: (16, "counter := 0"),
    26: (12, "END  ; BT back to WHILE"),
    27: (None, "compiler epilogue: restore LNK"),
    28: (None, "compiler epilogue: restore SP"),
    29: (None, "compiler epilogue: BT LNK (halt at 0xB0)"),
}

# Word index inside AMemoryMappedToggle (base 0x1000).
AMMT_SOURCE = {
    0: (8, "PROCEDURE Toggle*  prologue"),
    1: (8, "save LNK"),
    2: (10, "light := 1 - light"),
    3: (10, "SB := MT[1]"),
    4: (10, "load light"),
    5: (10, "1 - light"),
    6: (10, "store light  ; this is the LED write if we ever get here"),
    7: (11, "restore LNK"),
    8: (11, "restore SP"),
    9: (11, "BT R15  ; return to caller"),
    10: (14, "BEGIN light := 0  prologue"),
    11: (14, "save LNK"),
    12: (14, "light := 0"),
    13: (14, "SB := MT[1]"),
    14: (14, "store light := 0"),
    15: (15, "restore LNK"),
    16: (15, "restore SP"),
    17: (15, "BT R15"),
}

# Word index inside LightToggle (base 0x1048).
LT_SOURCE = {
    0: (None, "compiler prologue: SUB SP, 4"),
    1: (None, "compiler prologue: save LNK"),
    2: (9, "counter := 0"),
    3: (9, "SB := MT[2]"),
    4: (9, "store counter"),
    5: (10, "maxIterations := 262144  ; MHI R0, 4"),
    6: (10, "store maxIterations"),
    7: (12, "WHILE TRUE DO"),
    8: (13, "INC(counter)  ; reload SB"),
    9: (13, "INC(counter)"),
    10: (13, "INC(counter)"),
    11: (13, "INC(counter)"),
    12: (13, "INC(counter)"),
    13: (13, "load counter"),
    14: (14, "load maxIterations"),
    15: (14, "IF counter >= maxIterations"),
    16: (14, "BLT skip Toggle"),
    17: (15, "MMT.Toggle  ; BL → 0x1000, R15 := 0x1090"),
    18: (16, "counter := 0  ; return from Toggle"),
    19: (16, "reload SB"),
    20: (16, "store counter"),
    21: (12, "BT back to WHILE"),
    22: (None, "epilogue: restore LNK"),
    23: (None, "epilogue: restore SP"),
    24: (None, "BT LNK"),
}


def src_of(mod_lines: list[str], line: int | None) -> str | None:
    if line is None or not (1 <= line <= len(mod_lines)):
        return None
    return mod_lines[line - 1].strip()


def add_setup_and_halt(entries: list[dict]) -> None:
    for addr, word, note in SETUP:
        entries.append(entry(addr, word, note=note, mark="setup"))
    for addr in range(HALT_START, HALT_END, 4):
        entries.append(entry(addr, HALT_WORD, note="halt (branch-self)", mark="halt"))


def build_blink2() -> tuple[list[dict], dict]:
    mod = load_lines("tests/Blink2test.Mod")
    user = load_code_words("tests/Blink2test.code")
    entries = []
    for i, word in enumerate(user):
        line, note = BLINK2_SOURCE.get(i, (None, None))
        entries.append(entry(
            i * 4, word,
            file="tests/Blink2test.Mod" if line else None,
            line=line,
            src=src_of(mod, line),
            note=note,
        ))
    add_setup_and_halt(entries)
    return entries, {
        "mod_file": "tests/Blink2test.Mod",
        "mod_source": mod,
        "modules": [{"file": "tests/Blink2test.Mod", "source": mod, "title": "LightToggle (Blink2)"}],
        "title": "Blink2 — inlined toggle (this one works)",
        "subtitle": "Verilator playback of Blink2test · unfixed CPU, no BL",
    }


def build_blink3(imem_path: str) -> tuple[list[dict], dict]:
    ammt_mod = load_lines("tests/AMemoryMappedToggle.Mod")
    lt_mod = load_lines("tests/Blink3test.Mod")
    words = load_words_file(imem_path)
    entries = []

    for addr, word, note in blink3_startup_trampoline():
        entries.append(entry(addr, word, note=note, mark="trampoline"))
    add_setup_and_halt(entries)

    ammt_base = 0x1000
    for i in range(18):
        addr = ammt_base + i * 4
        word = words[addr // 4]
        line, note = AMMT_SOURCE.get(i, (None, None))
        mark = None
        if addr == BLINK3_TOGGLE:
            mark = "expected-target"
        elif addr == BLINK3_AMMT_BODY:
            mark = "module-init"
        elif addr == BLINK3_AMMT_BODY + 0x10:
            mark = "init-store"
        entries.append(entry(
            addr, word,
            file="tests/AMemoryMappedToggle.Mod" if line else None,
            line=line,
            src=src_of(ammt_mod, line),
            note=note,
            mark=mark,
        ))

    lt_base = BLINK3_ENTRY
    for i in range(25):
        addr = lt_base + i * 4
        word = words[addr // 4]
        line, note = LT_SOURCE.get(i, (None, None))
        mark = None
        if addr == BLINK3_BL_PC:
            mark = "call-bl"
        elif addr == BLINK3_RETURN:
            mark = "return-addr"
        elif addr == BLINK3_MAXITER_PC:
            mark = "delay-mhi"
        elif addr == BLINK3_MAXITER_STORE_PC:
            mark = "delay-store"
        entries.append(entry(
            addr, word,
            file="tests/Blink3test.Mod" if line else None,
            line=line,
            src=src_of(lt_mod, line),
            note=note,
            mark=mark,
        ))

    combined = (
        ["----- tests/AMemoryMappedToggle.Mod -----"]
        + ammt_mod
        + [""]
        + ["----- tests/Blink3test.Mod  (LightToggle) -----"]
        + lt_mod
    )
    # 1-based line of each module's first source line in the combined listing.
    ammt_off = 2
    lt_off = 4 + len(ammt_mod)
    return entries, {
        "mod_file": "tests/Blink3test.Mod + AMemoryMappedToggle.Mod",
        "mod_source": combined,
        "modules": [
            {"file": "tests/AMemoryMappedToggle.Mod", "source": ammt_mod, "title": "AMemoryMappedToggle"},
            {"file": "tests/Blink3test.Mod", "source": lt_mod, "title": "LightToggle (Blink3)"},
        ],
        "title": "Blink3 — AMMT BEGIN, then Toggle via BL (R15 = PC+4)",
        "subtitle": "Trampoline BLs stand in for Modules.Load body calls",
        "ammt_mod_offset": ammt_off,
        "lt_mod_offset": lt_off,
    }


def lookup(program: list[dict], pc: int) -> dict | None:
    for e in program:
        if e["addr"] == pc:
            return e
    return None


def collapse_to_instructions(cycles: list[dict]) -> list[dict]:
    """Keep the last cycle of each PC run so LDW has retired before we step."""
    out = []
    for i, c in enumerate(cycles):
        nxt = cycles[i + 1] if i + 1 < len(cycles) else None
        if nxt is None or nxt.get("pc") != c.get("pc"):
            out.append(c)
    return out


def attach_dmem(cycles: list[dict]) -> None:
    mem: dict[int, int] = {}
    for c in cycles:
        if c.get("memWrite"):
            mem[int(c.get("memAddr") or 0)] = int(c.get("memWriteData") or 0)
        snap = {}
        for addr, name in WATCH_ADDRS.items():
            if addr in mem:
                snap[str(addr)] = {"addr": addr, "name": name, "value": mem[addr]}
        c["dmem"] = snap


def find_blink3_init(steps: list[dict]) -> dict | None:
    begin_i = None
    store_i = None
    light_after = None
    for i, c in enumerate(steps):
        pc = int(c.get("pc") or 0)
        if pc == BLINK3_AMMT_BODY and begin_i is None:
            begin_i = i
        if pc == BLINK3_AMMT_BODY + 0x10 and store_i is None:
            store_i = i
        dmem = c.get("dmem") or {}
        rec = dmem.get(str(BLINK3_LIGHT_ADDR)) or dmem.get(BLINK3_LIGHT_ADDR)
        if rec and rec.get("value") == 0 and store_i is not None and i >= store_i:
            light_after = 0
    if begin_i is None:
        return None
    return {
        "begin_pc": BLINK3_AMMT_BODY,
        "store_pc": BLINK3_AMMT_BODY + 0x10,
        "light_addr": BLINK3_LIGHT_ADDR,
        "light_after": light_after,
        "begin_step_index": begin_i,
        "store_step_index": store_i if store_i is not None else begin_i,
    }


def find_blink3_delay(steps: list[dict]) -> dict | None:
    mhi_i = None
    store_i = None
    value = None
    for i, c in enumerate(steps):
        pc = int(c.get("pc") or 0)
        if pc == BLINK3_MAXITER_PC and mhi_i is None:
            mhi_i = i
        if pc == BLINK3_MAXITER_STORE_PC and store_i is None:
            store_i = i
        dmem = c.get("dmem") or {}
        rec = dmem.get(str(BLINK3_MAXITER_ADDR)) or dmem.get(BLINK3_MAXITER_ADDR)
        if rec is not None and rec.get("value") is not None:
            value = rec["value"]
    if mhi_i is None:
        return None
    raw = steps[mhi_i].get("hex")
    try:
        word = int(str(raw), 16) if raw else BLINK3_MHI_WORD
    except ValueError:
        word = BLINK3_MHI_WORD
    stored = value if value is not None else BLINK3_MAXITER
    return {
        "max_iterations": stored,
        "mhi_word": word,
        "mhi_pc": BLINK3_MAXITER_PC,
        "store_pc": BLINK3_MAXITER_STORE_PC,
        "addr": BLINK3_MAXITER_ADDR,
        "value": value,
        "mhi_step_index": mhi_i,
        "store_step_index": store_i if store_i is not None else mhi_i,
    }


def find_blink3_failure(steps: list[dict]) -> dict | None:
    bl_i = None
    for i, c in enumerate(steps):
        if int(c.get("pc") or 0) == BLINK3_BL_PC:
            bl_i = i
            break
    if bl_i is None:
        return None
    bl = steps[bl_i]
    land = steps[bl_i + 1] if bl_i + 1 < len(steps) else {}
    actual = int(land.get("pc") or 0)
    r15 = int(bl.get("r15") or 0)
    r15_after = int(land.get("r15") or r15)
    hex_word = bl.get("hex") or ""
    insn = hex_word if str(hex_word).startswith("0x") else f"0x{hex_word}"
    r15_written = r15_after == BLINK3_RETURN
    if actual == BLINK3_TOGGLE and r15_written:
        kind = "bl_ok"
        label = (
            "BL at 0x108C lands on Toggle at 0x1000 and writes R15 = 0x1090."
        )
    elif actual == BLINK3_TOGGLE:
        kind = "bl_no_r15"
        label = (
            "BL at 0x108C lands on Toggle at 0x1000 (loader matches Modules.Mod). "
            "R15 is not written."
        )
    else:
        kind = "bl_wrong_target"
        label = (
            f"BL at 0x108C jumps to 0x{actual:X}, not Toggle at 0x1000. "
            "R15 is not written."
        )
    return {
        "kind": kind,
        "label": label,
        "bl_pc": BLINK3_BL_PC,
        "expected_target": BLINK3_TOGGLE,
        "actual_target": actual,
        "return_addr": BLINK3_RETURN,
        "r15_at_bl": r15,
        "r15_after": r15_after,
        "r15_expected": BLINK3_RETURN,
        "r15_written": r15_written,
        "step_index": bl_i,
        "landing_step_index": bl_i + 1 if bl_i + 1 < len(steps) else bl_i,
        "insn": insn,
    }


def annotate(trace: dict, program: list[dict], meta: dict) -> dict:
    for cyc in trace.get("cycles", []):
        pc = int(cyc.get("pc", 0))
        info = lookup(program, pc)
        if info:
            cyc["disasm"] = info["disasm"]
            cyc["hex"] = info["hex"]
            cyc["src"] = info["src"]
            src_line = info["line"]
            if src_line and info.get("file"):
                if "AMemoryMappedToggle" in info["file"]:
                    src_line = meta.get("ammt_mod_offset", 2) + info["line"] - 1
                elif "Blink3test" in info["file"]:
                    src_line = meta.get("lt_mod_offset", 2) + info["line"] - 1
            cyc["srcLine"] = src_line
            cyc["srcFile"] = info["file"]
            cyc["note"] = info["note"]
            cyc["mark"] = info["mark"]
        else:
            cyc["disasm"] = f"(pc 0x{pc:x} outside listing)"
            cyc["hex"] = None
            cyc["src"] = None
            cyc["srcLine"] = None
            cyc["srcFile"] = None
            cyc["note"] = None
            cyc["mark"] = None
        if pc == BLINK3_BL_PC:
            cyc["mark"] = "call-bl"
        elif pc == BLINK3_TOGGLE:
            cyc["mark"] = cyc.get("mark") or "expected-target"
        elif pc == BLINK3_AMMT_BODY:
            cyc["mark"] = "module-init"
        elif pc == BLINK3_AMMT_BODY + 0x10:
            cyc["mark"] = "init-store"
        elif pc == BLINK3_MAXITER_PC:
            cyc["mark"] = "delay-mhi"
        elif pc == BLINK3_MAXITER_STORE_PC:
            cyc["mark"] = "delay-store"
    return trace


def summarize(trace: dict) -> dict:
    edges = trace.get("led_toggles") or []
    periods = [edges[i] - edges[i - 1] for i in range(1, len(edges))]
    mean = (sum(periods) / len(periods)) if periods else None
    return {
        "toggle_cycles": edges,
        "periods": periods,
        "mean_period": mean,
        "n_clocks": len(trace.get("clocks") or trace.get("cycles", [])),
        "n_steps": len(trace.get("cycles", [])),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--wave", required=True)
    ap.add_argument("--program", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--visualizer")
    ap.add_argument("--image", default="blink2", choices=("blink2", "blink3"))
    ap.add_argument("--imem", default="")
    ap.add_argument("--collapse", action="store_true", default=True)
    args = ap.parse_args()

    if args.image == "blink3":
        imem = args.imem or os.path.join(ROOT, "sim", "visualizer", "imem", "blink3.words")
        program, meta = build_blink3(imem)
    else:
        program, meta = build_blink2()

    with open(args.trace) as f:
        trace = json.load(f)

    clocks = list(trace.get("cycles", []))
    trace = annotate(trace, program, meta)
    if args.collapse:
        trace["clocks_sampled"] = len(clocks)
        trace["cycles"] = collapse_to_instructions(trace.get("cycles", []))
    attach_dmem(trace["cycles"])

    summary = summarize(trace)
    trace["summary"] = summary
    trace["mod_source"] = meta["mod_source"]
    trace["mod_file"] = meta["mod_file"]
    trace["title"] = meta["title"]
    trace["subtitle"] = meta["subtitle"]
    trace["modules"] = meta["modules"]
    trace["image"] = args.image
    if args.image == "blink3":
        trace["failure"] = find_blink3_failure(trace["cycles"])
        trace["init"] = find_blink3_init(trace["cycles"])
        trace["delay"] = find_blink3_delay(trace["cycles"])
        trace["ammt_mod_offset"] = meta.get("ammt_mod_offset")
        trace["lt_mod_offset"] = meta.get("lt_mod_offset")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(trace, f, indent=2)
        f.write("\n")

    prog_doc = {"entries": program, **{k: meta[k] for k in ("mod_source", "mod_file", "title", "subtitle", "modules") if k in meta}}
    with open(args.program, "w") as f:
        json.dump(prog_doc, f, indent=2)
        f.write("\n")

    if args.visualizer:
        vis_dir = os.path.dirname(args.visualizer)
        os.makedirs(vis_dir, exist_ok=True)
        with open(args.visualizer, "w") as f:
            json.dump(trace, f)
            f.write("\n")

    print("[annotate] image:", args.image)
    print("[annotate] listing:", len(program), "instructions")
    print("[annotate] clocks:", summary["n_clocks"], "instruction steps:", summary["n_steps"])
    print("[annotate] LED edges at cycles:", summary["toggle_cycles"])
    if args.image == "blink3":
        print("[annotate] init:", json.dumps(trace.get("init"), indent=2))
        print("[annotate] delay:", json.dumps(trace.get("delay"), indent=2))
        print("[annotate] failure:", json.dumps(trace.get("failure"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
