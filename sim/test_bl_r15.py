#!/usr/bin/env python3
"""Assert the Blink3 image still has the relocated BL; the short sim does not run it.

LightToggle's delay is now 262144 iterations (hardware-visible). An 800-cycle
trace never reaches MMT.Toggle, so this file no longer looks for LED edges.
BL writing R15 is covered by the mill CPUSubset0 BL test.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from imem_layout import BLINK3_BL_PC, BLINK3_TOGGLE, blink3_imem  # noqa: E402

TRACE = os.path.join(HERE, "visualizer", "traces", "blink3.json")
FINAL = os.path.join(ROOT, "tests", "final_system.code")


def test_imem_keeps_relocated_bl():
    mem = blink3_imem(FINAL)
    assert mem[BLINK3_BL_PC // 4] == 0xF7FFFFDC, hex(mem[BLINK3_BL_PC // 4])
    print("[ok] IMEM 0x108C is still BL 0xF7FFFFDC → Toggle 0x1000")


def test_short_trace_does_not_reach_toggle():
    assert os.path.isfile(TRACE), f"missing {TRACE}; run make -C sim run-blink3"
    with open(TRACE) as f:
        trace = json.load(f)
    assert trace.get("failure") is None, trace.get("failure")
    steps = trace.get("cycles") or []
    pcs = {int(c.get("pc") or 0) for c in steps}
    assert BLINK3_BL_PC not in pcs, "800-cycle sim should not reach BL Toggle"
    assert BLINK3_TOGGLE not in pcs, "800-cycle sim should not enter Toggle"
    edges = (trace.get("summary") or {}).get("toggle_cycles") or trace.get("led_toggles") or []
    assert edges == [], f"no LED edges expected with maxIterations=262144; edges={edges}"
    print("[ok] 800-cycle Blink3 trace never reaches Toggle (delay is 262144)")


def main() -> int:
    test_imem_keeps_relocated_bl()
    test_short_trace_does_not_reach_toggle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
