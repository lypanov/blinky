#!/usr/bin/env python3
"""Assert the Blink3 sim trampoline calls AMMT BEGIN so light is 0.

The trampoline is two BLs (Modules.Load `body` stand-in). BEGIN still runs
before LightToggle.
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
    BLINK3_LIGHT_ADDR,
    blink3_imem,
    blink3_startup_trampoline,
    branch_offset_word,
)

TRACE = os.path.join(HERE, "visualizer", "traces", "blink3.json")
FINAL = os.path.join(ROOT, "tests", "final_system.code")


def test_trampoline_encodings():
    words = {addr: word for addr, word, _ in blink3_startup_trampoline()}
    assert words[0x00] == branch_offset_word(0x00, BLINK3_AMMT_BODY, link=True) == 0xF7000409, hex(words[0x00])
    assert words[0x04] == branch_offset_word(0x04, BLINK3_ENTRY, link=True) == 0xF7000410, hex(words[0x04])
    print("[ok] trampoline 0x00 BL 0x1028; 0x04 BL 0x1048 (BL plants R15)")


def test_imem_plants_trampoline():
    mem = blink3_imem(FINAL)
    assert mem[0] == 0xF7000409, hex(mem[0])
    assert mem[1] == 0xF7000410, hex(mem[1])
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
    assert 0x00 in pcs, "BL to AMMT BEGIN never executed"
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
