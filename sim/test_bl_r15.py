#!/usr/bin/env python3
"""Assert BL plants R15 = PC+4 (ISA) and Blink3 Toggle returns into the loop."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from imem_layout import BLINK3_RETURN, BLINK3_TOGGLE  # noqa: E402

TRACE = os.path.join(HERE, "visualizer", "traces", "blink3.json")


def test_trace_bl_writes_r15_and_blinks():
    assert os.path.isfile(TRACE), f"missing {TRACE}; run make -C sim run-blink3"
    with open(TRACE) as f:
        trace = json.load(f)
    fail = trace.get("failure") or {}
    assert fail.get("actual_target") == BLINK3_TOGGLE, fail
    assert fail.get("r15_written"), fail
    assert fail.get("r15_after") == BLINK3_RETURN, fail
    assert fail.get("r15_expected") == BLINK3_RETURN, fail
    edges = (trace.get("summary") or {}).get("toggle_cycles") or trace.get("led_toggles") or []
    assert len(edges) >= 2, f"LED should blink after BL writes R15; edges={edges}"
    print(f"[ok] BL at 0x108C wrote R15=0x{BLINK3_RETURN:X}; {len(edges)} LED edges")


def main() -> int:
    test_trace_bl_writes_r15_and_blinks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
