#!/usr/bin/env python3

import sys
from instruction_parser import disassemble

def dump_system_image(image_file):
    """
    Reads a system image file with module header markers and dumps
    the disassembled code for each module.
    """
    with open(image_file, "r") as f:
        lines = f.readlines()

    current_module = None
    module_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("=== Module:"):
            # If a previous module was being processed, dump its code.
            if current_module is not None and module_lines:
                print(f"\nModule: {current_module['name']}")
                print(f"Base: 0x{current_module['base']:08x}  Code Length: 0x{current_module['length']:08x}")
                for addr, inst in module_lines:
                    # Mask the instruction to 32 bits.
                    inst &= 0xffffffff
                    print(f"0x{addr:08x}: 0x{inst:08x}    {disassemble(inst)}")
            # Start a new module.
            current_module = {"name": line[len("=== Module:"):].strip()}
            module_lines = []
        elif line.startswith("Base:"):
            if current_module is not None:
                base_str = line.split(":")[1].strip()
                current_module["base"] = int(base_str, 16)
        elif line.startswith("Code Length:"):
            if current_module is not None:
                len_str = line.split(":")[1].strip()
                current_module["length"] = int(len_str, 16)
        elif line and line.startswith("0x"):
            # Parse an instruction line.
            try:
                addr_str, rest = line.split(":", 1)
                addr = int(addr_str, 16)
                inst_str = rest.strip().split()[0]
                inst = int(inst_str, 16)
                module_lines.append((addr, inst))
            except Exception:
                continue
        # We ignore metadata blocks here.
    
    # Dump last module if any.
    if current_module is not None and module_lines:
        print(f"\nModule: {current_module['name']}")
        print(f"Base: 0x{current_module['base']:08x}  Code Length: 0x{current_module['length']:08x}")
        for addr, inst in module_lines:
            inst &= 0xffffffff
            print(f"0x{addr:08x}: 0x{inst:08x}    {disassemble(inst)}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python image_dump.py <system_image_file>")
        sys.exit(1)
    image_file = sys.argv[1]
    dump_system_image(image_file)

if __name__ == "__main__":
    main()
