#!/usr/bin/env python3

from rsc_parser import parse_rsc, fixup_bl, fixup_ldr_str_add, fixup_type, ImportedModule
from mt_table import mt_table  # Shared mt_table

# Added a global counter for module numbering.
module_counter = 1

# Global dictionary holding all loaded modules by name.
loaded_modules = {}

# Virtual memory allocation counters (simulate physical addresses in our image)
next_free_code_addr = 0x1000  # start at address 0x1000 for code
next_free_data_addr = 0x8000  # start at address 0x8000 for data

def load_module(module_name, loaded_modules=loaded_modules):
    """
    Emulates Oberon's Load* procedure. Loads module module_name from its .rsc file,
    processes its imports recursively, assigns virtual memory, performs fixups, and
    registers it in the global module table (mt_table).
    """
    global next_free_code_addr, next_free_data_addr, mt_table

    if module_name in loaded_modules:
        # Module already loaded.
        return loaded_modules[module_name]
    
    # Construct file name – assuming modules are named by their module name.
    filename = module_name + ".rsc"
    print(f"Loading module {module_name} from {filename}...")
    
    # Parse the .rsc file.
    # Note: parse_rsc should be imported from tools/rsc_parser.py
    module = parse_rsc(filename, output_format="default", perform_fixup=False)
    
    # Process import (dependency) list recursively.
    for imp_str, imp_key in module["imports"]:
        dependency = load_module(imp_str, loaded_modules)
        if dependency["key"] != imp_key:
            raise Exception(f"Key mismatch: {imp_str} expected key {imp_key}, found {dependency['key']}")
        # In a complete loader, you might increment a reference count here.
    
    # Simulate memory allocation:
    module_code_size = len(module["code"]) * 4  # assume 4 bytes per instruction
    module_data_size = module.get("data_size", 0)
    module["code_base"] = next_free_code_addr
    next_free_code_addr += module_code_size
    module["data_base"] = next_free_data_addr
    next_free_data_addr += module_data_size

    # Replace the old module_id assignment with one using a global counter.
    global module_counter
    # Instead of: module["module_id"] = module["key"]
    module["module_id"] = module_counter
    module_counter += 1

    # Instead of storing the module dictionary directly, convert it to an ImportedModule.
    # Import the ImportedModule type from rsc_parser.
    if module["module_id"] == 1:
        # Global module: store under key 1.
        mt_table[module["module_id"]] = ImportedModule(
            num=module["module_id"],
            code=module["code_base"],
            data=module["data_base"],
            ent=module.get("entry_table", 0)
        )
    else:
        # Imported module: store using key = module_id - 1.
        mt_table[module["module_id"] - 1] = ImportedModule(
            num=module["module_id"],
            code=module["code_base"],
            data=module["data_base"],
            ent=module.get("entry_table", 0)
        )

    # Now perform the fixups on this module using the global MT table.
    # (fix_org is a tuple (fix_org_p, fix_org_d, fix_org_t) as parsed)
    fix_org_p, fix_org_d, fix_org_t = module["fix_org"]
    module["code"] = fixup_bl(module["code"], fix_org_p, module["module_id"], mt_table)
    module["code"] = fixup_ldr_str_add(module["code"], fix_org_d, module["module_id"], mt_table)
    module["type_descriptors"] = fixup_type(module["type_descriptors"], fix_org_t, module["data_base"], mt_table)

    # Store the module in the loaded_modules table
    loaded_modules[module_name] = module
    print(f"Module {module_name} loaded. Code base: 0x{module['code_base']:08x}, Data base: 0x{module['data_base']:08x}")
    return module

def assemble_system_memory(root_module):
    system_image_lines = []
    metadata = {}

    # For each loaded module, dump its code section with a header.
    for name, mod in loaded_modules.items():
        base = mod["code_base"]
        code_length = len(mod["code"]) * 4  # total bytes
        system_image_lines.append(f"=== Module: {name} ===")
        system_image_lines.append(f"Base: 0x{base:08x}")
        system_image_lines.append(f"Code Length: 0x{code_length:08x}")
        for i, inst in enumerate(mod["code"]):
            addr = base + i * 4
            # Always write using only the low 32 bits.
            system_image_lines.append(f"0x{addr:08x}: 0x{inst & 0xffffffff:08x}")
        system_image_lines.append("")  # blank line separator

    metadata["initial_entry_point"] = f"0x{root_module['entry_point'] + root_module['code_base']:08x}"
    metadata["module_table"] = {
        mod["module_id"]: {"name": mod_name, "code_base": mod["code_base"], "code_length": len(mod["code"]) * 4}
            for mod_name, mod in loaded_modules.items()}
    system_image_lines.append("=== System Metadata ===")
    system_image_lines.append(str(metadata))
    return system_image_lines, metadata

def main(root_module_name):
    # Load root module and all dependent modules recursively.
    root_module = load_module(root_module_name)
    
    # Assemble a system-wide memory image.
    system_image_lines, metadata = assemble_system_memory(root_module)
    
    # Write the virtual memory image to final .code output.
    out_filename = "final_system.code"
    with open(out_filename, "w") as f:
        for line in system_image_lines:
            f.write(line + "\n")
    
    print(f"Final system image written to {out_filename}.")
    print(f"Initial entry point: {metadata['initial_entry_point']}")

if __name__ == "__main__":
    # Example: load the 'LightToggle' module (which depends on AMemoryMappedToggle).
    main("LightToggle")
