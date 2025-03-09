#!/usr/bin/env python3

from rsc_parser import parse_rsc, fixup_bl, fixup_ldr_str_add, fixup_type

# Global table emulating the MT register (module table)
mt_table = {}

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

    # Assign a module number (for simplicity, here assume each module has a unique key)
    # In a real loader, module.num is assigned during allocation.
    module["module_id"] = module["key"]  # or use another unique derivation

    # Register in our global module table.
    mt_table[module["module_id"]] = module

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
    """
    After all modules are loaded, assemble a system image.
    For simplicity the image is a list of (virtual address, content) tuples.
    The metadata includes the initial entry point (resolved from root_module).
    """
    system_image = []
    
    # Dump each module's code section at its allocated code_base.
    for mod in loaded_modules.values():
        base = mod["code_base"]
        for i, inst in enumerate(mod["code"]):
            addr = base + i * 4
            system_image.append((addr, inst))
    
    # Sort system memory by address.
    system_image.sort(key=lambda tup: tup[0])
    
    # Create metadata: for example, the initial entry point of the root module.
    metadata = {
        "initial_module": root_module["module_id"],
        "initial_entry_point": root_module["entry_point"] + root_module["code_base"],
        "module_table": {mod["module_id"]: {"name": name,
                                              "code_base": mod["code_base"],
                                              "data_base": mod["data_base"]} 
                         for name, mod in loaded_modules.items()}
    }
    
    return system_image, metadata

def main(root_module_name):
    # Load root module and all dependent modules recursively.
    root_module = load_module(root_module_name)
    
    # Assemble a system-wide memory image.
    system_image, metadata = assemble_system_memory(root_module)
    
    # Write the virtual memory image to final .code output.
    out_filename = "final_system.code"
    with open(out_filename, "w") as f:
        f.write("=== System Memory Image ===\n")
        for addr, inst in system_image:
            f.write(f"0x{addr:08x}: 0x{inst:08x}\n")
        f.write("\n=== Metadata ===\n")
        f.write(str(metadata))
    
    print(f"Final system image written to {out_filename}.")
    print(f"Initial entry point: 0x{metadata['initial_entry_point']:08x}")

if __name__ == "__main__":
    # Example: load the 'LightToggle' module (which depends on AMemoryMappedToggle).
    main("LightToggle")
