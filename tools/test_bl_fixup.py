#!/usr/bin/env python3
"""Assert the Python loader's BL fixup matches Modules.Mod.

Expected for Blink3 / LightToggle:
  BL at 0x108C becomes 0xF7FFFFDC and lands on Toggle at 0x1000.

Does not touch the CPU. R15/BL hardware is still unfixed.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, HERE)

from rsc_parser import ImportedModule, fixup_bl  # noqa: E402
from module_loader import linked_image, mt_table  # noqa: E402

# Modules.Mod: PC' = PC + 4 + off*4, off is signed 24-bit.
BL_PC = 0x108C
TOGGLE = 0x1000
EXPECTED_WORD = 0xF7FFFFDC  # off = -36 → 0x108C+4+(-36)*4 = 0x1000
PLACEHOLDER = 0xF7102011  # compiler packing: mno=1, pno=2, disp=17


def branch_target(pc, word):
    off = word & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return pc + 4 + off * 4


def test_synthetic_modules_mod_formula():
    """Same numbers as AMemoryMappedToggle.entries[2]=0, LightToggle BL at +0x44."""
    imp = ImportedModule(num=1, code=0x1000, entries=[40, 0, 0])
    code = [0] * 25
    code[17] = PLACEHOLDER
    out = fixup_bl(code, 17, code_base=0x1048, imports=[imp])
    word = out[17] & 0xFFFFFFFF
    assert word == EXPECTED_WORD, f"synthetic BL word 0x{word:08x}, want 0x{EXPECTED_WORD:08x}"
    assert branch_target(BL_PC, word) == TOGGLE, f"synthetic target 0x{branch_target(BL_PC, word):x}"
    print("[ok] synthetic fixup_bl → 0xF7FFFFDC → Toggle 0x1000")


def test_lighttoggle_rsc():
    words, root, meta = linked_image("LightToggle", TESTS)
    assert 1 in mt_table and 2 in mt_table, f"MT keys {sorted(mt_table)} (overwrite?)"
    assert mt_table[1].code == 0x1000, hex(mt_table[1].code)
    assert mt_table[2].code == 0x1048, hex(mt_table[2].code)
    assert mt_table[1].entries == [40, 0, 0], mt_table[1].entries
    assert mt_table[1].entry_at(2) == 0

    assert BL_PC in words, f"no word at 0x{BL_PC:x}"
    word = words[BL_PC]
    assert word == EXPECTED_WORD, (
        f"BL at 0x108C is 0x{word:08x}, expected 0x{EXPECTED_WORD:08x} "
        f"(Modules.Mod dest=entries[2]+code_base=0x1000)"
    )
    target = branch_target(BL_PC, word)
    assert target == TOGGLE, f"BL lands at 0x{target:08x}, expected Toggle 0x{TOGGLE:08x}"
    assert root["entry_point"] + root["code_base"] == 0x1048
    print(f"[ok] linked LightToggle: 0x108C = 0x{word:08x} → 0x{target:08x}")
    print(f"[ok] MT keys {sorted(mt_table)} entries AMMT={mt_table[1].entries}")
    print(f"[ok] entry point {meta['initial_entry_point']}")

    image = os.path.join(TESTS, "final_system.code")
    if os.path.isfile(image):
        text = open(image).read().lower()
        assert "0x0000108c: 0xf7ffffdc" in text, (
            f"{image} does not contain the relocated BL; re-run tools/module_loader.py"
        )
        print("[ok] tests/final_system.code has 0x108C = 0xf7ffffdc")


def main() -> int:
    test_synthetic_modules_mod_formula()
    test_lighttoggle_rsc()
    print("BL fixup matches Modules.Mod.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise SystemExit(1)
