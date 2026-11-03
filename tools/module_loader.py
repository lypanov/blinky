#!/usr/bin/env python3
"""Ahead-of-time port of Modules.Load* (docs/OberonSources/Modules.Mod).

Assigns code/data bases, fills mt_table[mod.num] without overwriting, and
runs the P/D/T fixup chains. Does not change the CPU.
"""

from __future__ import annotations

import os
import sys

from rsc_parser import parse_rsc, fixup_bl, fixup_ldr_str_add, fixup_type, ImportedModule
from mt_table import mt_table

module_counter = 1
loaded_modules = {}
next_free_code_addr = 0x1000
next_free_data_addr = 0x8000


def reset_loader_state():
    global module_counter, next_free_code_addr, next_free_data_addr
    loaded_modules.clear()
    mt_table.clear()
    module_counter = 1
    next_free_code_addr = 0x1000
    next_free_data_addr = 0x8000


def _rsc_path(module_name, rsc_dir):
    name = module_name + ".rsc"
    if rsc_dir:
        return os.path.join(rsc_dir, name)
    return name


def load_module(module_name, loaded_modules=loaded_modules, rsc_dir=None):
    """
    Emulates Oberon's Load* procedure. Loads module module_name from its .rsc file,
    processes its imports recursively, assigns virtual memory, performs fixups, and
    registers it in the global module table (mt_table[mod.num]).
    """
    global next_free_code_addr, next_free_data_addr, mt_table, module_counter

    if module_name in loaded_modules:
        return loaded_modules[module_name]

    filename = _rsc_path(module_name, rsc_dir)
    print(f"Loading module {module_name} from {filename}...")

    module = parse_rsc(filename, output_format="quiet", perform_fixup=False)

    # Load imports first (Modules.Mod recurses on the import list).
    imp_mods = []
    for imp_str, imp_key in module["imports"]:
        dependency = load_module(imp_str, loaded_modules, rsc_dir=rsc_dir)
        if dependency["key"] != imp_key:
            raise Exception(
                f"Key mismatch: {imp_str} expected key {imp_key}, found {dependency['key']}"
            )
        imp_mods.append(mt_table[dependency["module_id"]])

    module_code_size = len(module["code"]) * 4
    module_data_size = module.get("data_size", 0)
    module["code_base"] = next_free_code_addr
    next_free_code_addr += module_code_size
    module["data_base"] = next_free_data_addr
    next_free_data_addr += module_data_size

    module["module_id"] = module_counter
    module_counter += 1
    module["imp"] = imp_mods

    # Modules.Mod: SYSTEM.PUT(mod.num * 4 + MTOrg, p) — one slot per mod.num.
    desc = ImportedModule(
        num=module["module_id"],
        code=module["code_base"],
        data=module["data_base"],
        entries=module.get("entries") or [],
    )
    mt_table[module["module_id"]] = desc

    fix_org_p, fix_org_d, fix_org_t = module["fix_org"]
    module["code"] = fixup_bl(
        module["code"],
        fix_org_p,
        code_base=module["code_base"],
        imports=imp_mods,
    )
    module["code"] = fixup_ldr_str_add(
        module["code"],
        fix_org_d,
        module["module_id"],
        mt_table,
        imports=imp_mods,
    )
    module["type_descriptors"] = fixup_type(
        module["type_descriptors"], fix_org_t, module["data_base"], mt_table
    )

    loaded_modules[module_name] = module
    print(
        f"Module {module_name} loaded. Code base: 0x{module['code_base']:08x}, "
        f"Data base: 0x{module['data_base']:08x}, num={module['module_id']}, "
        f"entries={module.get('entries')}"
    )
    return module


def assemble_system_memory(root_module):
    system_image_lines = []
    metadata = {}

    for name, mod in loaded_modules.items():
        base = mod["code_base"]
        code_length = len(mod["code"]) * 4
        system_image_lines.append(f"=== Module: {name} ===")
        system_image_lines.append(f"Base: 0x{base:08x}")
        system_image_lines.append(f"Code Length: 0x{code_length:08x}")
        for i, inst in enumerate(mod["code"]):
            addr = base + i * 4
            system_image_lines.append(f"0x{addr:08x}: 0x{inst & 0xffffffff:08x}")
        system_image_lines.append("")

    metadata["initial_entry_point"] = f"0x{root_module['entry_point'] + root_module['code_base']:08x}"
    metadata["module_table"] = {
        mod["module_id"]: {
            "name": mod_name,
            "code_base": mod["code_base"],
            "code_length": len(mod["code"]) * 4,
            "entries": mod.get("entries") or [],
        }
        for mod_name, mod in loaded_modules.items()
    }
    system_image_lines.append("=== System Metadata ===")
    system_image_lines.append(str(metadata))
    return system_image_lines, metadata


def linked_image(root_module_name, rsc_dir):
    """Load root + imports and return {byte_addr: word}, root module, metadata."""
    reset_loader_state()
    root = load_module(root_module_name, rsc_dir=rsc_dir)
    words = {}
    for _name, mod in loaded_modules.items():
        for i, inst in enumerate(mod["code"]):
            words[mod["code_base"] + i * 4] = inst & 0xFFFFFFFF
    _, metadata = assemble_system_memory(root)
    return words, root, metadata


def main(root_module_name, rsc_dir=None, out_filename="final_system.code"):
    reset_loader_state()
    root_module = load_module(root_module_name, rsc_dir=rsc_dir)
    system_image_lines, metadata = assemble_system_memory(root_module)
    with open(out_filename, "w") as f:
        for line in system_image_lines:
            f.write(line + "\n")
    print(f"Final system image written to {out_filename}.")
    print(f"Initial entry point: {metadata['initial_entry_point']}")
    bl = None
    for line in system_image_lines:
        if line.startswith("0x0000108c:"):
            bl = line
    if bl:
        print(f"BL at 0x108C: {bl}")
    return metadata


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    tests = os.path.abspath(os.path.join(here, "..", "tests"))
    cwd_rsc = os.path.join(os.getcwd(), "LightToggle.rsc")
    rsc_dir = os.getcwd() if os.path.isfile(cwd_rsc) else tests
    out = os.path.join(rsc_dir, "final_system.code") if rsc_dir == tests else "final_system.code"
    main("LightToggle", rsc_dir=rsc_dir, out_filename=out)
