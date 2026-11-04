#!/usr/bin/env python3
"""Assert the Blink3 sim trampoline calls AMMT BEGIN so light is 0.

Does not touch the CPU. R15/BL hardware is still unfixed. Does not claim
the LED blinks.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from imem_layout import (  # noqa: E402
    BLINK3_AMMT_BODY,
    BLINK3_ENTRY,
    BLINK3_INIT_CONT,
    BLINK3_LIGHT_ADDR,
    HALT_START,
    blink3_imem,
    blink3_startup_trampoline,
    branch_offset_word,
    mov_imm,
)

TRACE = os.path.join(HERE, "visualizer", "traces", "blink3.json")
FINAL = os.path.join(ROOT, "tests", "final_system.code")


def test_trampoline_encodings():
    words = {addr: word for addr, word, _ in blink3_startup_trampoline()}
    assert words[0x00] == mov_imm(15, BLINK3_INIT_CONT) == 0x4F000008, hex(words[0x00])
    assert words[0x04] == branch_offset_word(0x04, BLINK3_AMMT_BODY, link=False) == 0xE7000408, hex(words[0x04])
    assert words[0x08] == mov_imm(15, HALT_START) == 0x4F0000B0, hex(words[0x08])
    assert words[0x0C] == branch_offset_word(0x0C, BLINK3_ENTRY, link=False) == 0xE700040E, hex(words[0x0C])
    print("[ok] trampoline 0x00 MOV R15,0x08; 0x04 B 0x1028; 0x08 MOV R15,0xB0; 0x0C B 0x1048")


def test_imem_plants_trampoline():
    mem = blink3_imem(FINAL)
    assert mem[0] == 0x4F000008, hex(mem[0])
    assert mem[1] == 0xE7000408, hex(mem[1])
    assert mem[2] == 0x4F0000B0, hex(mem[2])
    assert mem[3] == 0xE700040E, hex(mem[3])
    # AMMT BEGIN still at 0x1028; LightToggle still at 0x1048; BL still relocated.
    assert mem[BLINK3_AMMT_BODY // 4] != 0x0000BEEF
    assert mem[BLINK3_ENTRY // 4] != 0x0000BEEF
    assert mem[0x108C // 4] == 0xF7FFFFDC, hex(mem[0x108C // 4])
    print("[ok] blink3.imem plants trampoline over the old B-to-LightToggle")


def test_trace_runs_begin_and_zeros_light():
    assert os.path.isfile(TRACE), f"missing {TRACE}; run make -C sim run-blink3"
    with open(TRACE) as f:
        trace = json.load(f)
    init = trace.get("init") or {}
    assert init.get("begin_pc") == BLINK3_AMMT_BODY, init
    assert init.get("store_pc") == BLINK3_AMMT_BODY + 0x10, init
    assert init.get("light_addr") == BLINK3_LIGHT_ADDR, init
    assert init.get("light_after") == 0, init
    steps = trace.get("cycles") or []
    pcs = [int(c.get("pc") or 0) for c in steps]
    assert BLINK3_AMMT_BODY in pcs, "BEGIN body at 0x1028 never executed"
    assert BLINK3_AMMT_BODY + 0x10 in pcs, "STW light:=0 at 0x1038 never executed"
    # Trampoline before main.
    assert 0x04 in pcs, "B to AMMT BEGIN never executed"
    i_begin = next(i for i, pc in enumerate(pcs) if pc == BLINK3_AMMT_BODY)
    i_main = next((i for i, pc in enumerate(pcs) if pc == BLINK3_ENTRY), None)
    assert i_main is not None and i_begin < i_main, "BEGIN must run before LightToggle"
    saw_zero = False
    for c in steps[init["store_step_index"]:]:
        dmem = c.get("dmem") or {}
        rec = dmem.get(str(BLINK3_LIGHT_ADDR)) or dmem.get(BLINK3_LIGHT_ADDR)
        if rec and rec.get("value") == 0:
            saw_zero = True
            break
    assert saw_zero, "dmem[0x50] light never became 0"
    print("[ok] trace: BEGIN 0x1028 then STW 0x1038; light at 0x50 is 0")


def main() -> int:
    test_trampoline_encodings()
    test_imem_plants_trampoline()
    test_trace_runs_begin_and_zeros_light()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
