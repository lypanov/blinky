#!/usr/bin/env python3

import sys
from instruction_parser import disassemble

def dump_system_image(image_file):
    """
    Reads a system image file containing lines of the form:
      0x[address]: 0x[instruction]
    and dumps a fully disassembled listing.
    """
    instructions = []
    addresses = []
    with open(image_file, "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            # Skip header or metadata lines
            if not line or line.startswith("===") or line.startswith("Metadata"):
                continue
            # Expect lines like: "0x00401000: 0x81d00004"
            try:
                addr_str, rest = line.split(":", 1)
                inst_str = rest.strip().split()[0]
                addr = int(addr_str, 16)
                instr = int(inst_str, 16)
                addresses.append(addr)
                instructions.append(instr)
            except Exception:
                # Skip lines that do not match the expected format.
                continue

    # Dump the disassembled instructions.
    for i, instr in enumerate(instructions):
        addr = addresses[i]
        asm = disassemble(instr)
        print(f"0x{addr:08x}: 0x{instr:08x}    {asm}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python image_dump.py <system_image_file>")
        sys.exit(1)
    image_file = sys.argv[1]
    dump_system_image(image_file)

if __name__ == "__main__":
    main()
