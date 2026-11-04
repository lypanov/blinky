#!/usr/bin/env python3
"""Assert Blink3 LightToggle uses the hardware-visible delay (262144).

ORP emits MHI R0, 4 (0x60000004) because 0x40000 does not fit a 16-bit MOV.
The word count is unchanged, so the relocated BL stays at 0x108C.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from imem_layout import (  # noqa: E402
    BLINK3_MAXITER,
    BLINK3_MAXITER_ADDR,
    BLINK3_MAXITER_PC,
    BLINK3_MAXITER_STORE_PC,
    BLINK3_MHI_WORD,
    blink3_imem,
)

TRACE = os.path.join(HERE, "visualizer", "traces", "blink3.json")
FINAL = os.path.join(ROOT, "tests", "final_system.code")
MOD = os.path.join(ROOT, "tests", "Blink3test.Mod")


def test_source_and_image():
    src = open(MOD).read()
    assert "maxIterations := 262144;" in src, src
    text = open(FINAL).read().lower()
    assert "0x0000105c: 0x60000004" in text, text
    mem = blink3_imem(FINAL)
    assert mem[BLINK3_MAXITER_PC // 4] == BLINK3_MHI_WORD, hex(mem[BLINK3_MAXITER_PC // 4])
    print("[ok] source 262144; IMEM 0x105C = MHI R0, 4")


def test_trace_stores_delay():
    assert os.path.isfile(TRACE), f"missing {TRACE}; run make -C sim run-blink3"
    with open(TRACE) as f:
        trace = json.load(f)
    delay = trace.get("delay") or {}
    assert delay.get("max_iterations") == BLINK3_MAXITER, delay
    assert delay.get("mhi_word") == BLINK3_MHI_WORD, delay
    assert delay.get("mhi_pc") == BLINK3_MAXITER_PC, delay
    assert delay.get("store_pc") == BLINK3_MAXITER_STORE_PC, delay
    assert delay.get("addr") == BLINK3_MAXITER_ADDR, delay
    assert delay.get("value") == BLINK3_MAXITER, delay
    steps = trace.get("cycles") or []
    pcs = [int(c.get("pc") or 0) for c in steps]
    assert BLINK3_MAXITER_PC in pcs, "MHI at 0x105C never executed"
    assert BLINK3_MAXITER_STORE_PC in pcs, "STW maxIterations at 0x1060 never executed"
    saw = False
    for c in steps[delay["store_step_index"]:]:
        dmem = c.get("dmem") or {}
        rec = dmem.get(str(BLINK3_MAXITER_ADDR)) or dmem.get(BLINK3_MAXITER_ADDR)
        if rec and rec.get("value") == BLINK3_MAXITER:
            saw = True
            break
    assert saw, "dmem[0x74] never became 262144"
    print("[ok] trace: MHI 0x105C then STW 0x1060; dmem[0x74] = 262144")


def main() -> int:
    test_source_and_image()
    test_trace_stores_delay()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
