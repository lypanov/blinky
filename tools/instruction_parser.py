op_names = ["MOV", "LSL", "ASR", "ROR", "AND", "ANN", "IOR", "XOR", "ADD", "SUB", "MUL", "DIV", "FAD", "FSB", "FML", "FDV"]
cond_names = ["MI", "EQ", "CS", "VS", "LS", "LT", "LE", "T", "PL", "NE", "CC", "VC", "HI", "GE", "GT", "F"]

def disassemble(instr):
    type_bits = (instr >> 30) & 0x3
    if type_bits == 0:  # F0
        u = (instr >> 29) & 1
        a = (instr >> 24) & 0xF
        b = (instr >> 20) & 0xF
        op = (instr >> 16) & 0xF
        c = instr & 0xF
        if (instr >> 4) & 0xFFF != 0:
            return "Invalid F0 instruction"
        if u == 0:
            return f"{op_names[op]} R{a}, R{b}, R{c}"
        else:
            if op == 8:
                return f"ADC R{a}, R{b}, R{c}"
            elif op == 9:
                return f"SBC R{a}, R{b}, R{c}"
            elif op == 10:
                return f"UMUL R{a}, R{b}, R{c}"
            else:
                return f"Unknown F0 u=1 op={op}"
    elif type_bits == 1:  # F1
        u = (instr >> 29) & 1
        v = (instr >> 28) & 1
        a = (instr >> 24) & 0xF
        b = (instr >> 20) & 0xF
        op = (instr >> 16) & 0xF
        n = instr & 0xFFFF
        if u == 0:
            if op == 0:
                return f"MOV R{a}, {n:#x}"
            else:
                return f"{op_names[op]} R{a}, R{b}, {n:#x}"
        else:
            if op == 0:
                return f"MHI R{a}, {n:#x}"
            elif op == 8:
                return f"ADC R{a}, R{b}, {n:#x}"
            elif op == 9:
                return f"SBC R{a}, R{b}, {n:#x}"
            elif op == 10:
                return f"UMUL R{a}, R{b}, {n:#x}"
            else:
                return f"Unknown F1 u=1 op={op}"
    elif type_bits == 2:  # F2
        u = (instr >> 29) & 1
        v = (instr >> 28) & 1
        a = (instr >> 24) & 0xF
        b = (instr >> 20) & 0xF
        off = instr & 0xFFFFF
        if u == 0:  # Load
            return f"LD{'B' if v else 'W'} R{a}, [R{b}, {off:#x}]"
        else:  # Store
            return f"ST{'B' if v else 'W'} R{a}, [R{b}, {off:#x}]"
    elif type_bits == 3:  # F3
        bit29 = (instr >> 29) & 1
        v = (instr >> 28) & 1
        cond = (instr >> 24) & 0xF
        if bit29 == 0:  # Branch to register
            if (instr >> 4) & 0xFFFFF != 0:
                return "Invalid F3 instruction"
            c = instr & 0xF
            if v == 0 and cond == 7 and c == 1:
                return "RTI"
            elif v == 0 and cond == 15 and (instr & 0xFF0) == 0x020:
                e = instr & 1
                return "STI" if e else "CLI"
            else:
                cond_name = cond_names[cond]
                return f"B{'L' if v else ''}{cond_name} R{c}"
        else:  # Branch to offset
            off = instr & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000  # Sign extend
            cond_name = cond_names[cond]
            return f"B{'L' if v else ''}{cond_name}, off={off}"

def disassemble_instructions(instructions, base_addr=0):
    """
    Disassembles a list of instructions.
    Each instruction is printed preceded by its virtual address computed from base_addr.
    """
    for i, instr in enumerate(instructions):
        addr = base_addr + i * 4
        asm = disassemble(instr)
        print(f"0x{addr:08x}: 0x{instr:08x}    {asm}")

if __name__ == "__main__":
    # For testing: if run standalone, read from input.txt and dump disassembly.
    with open('input.txt', 'r') as f:
        lines = f.readlines()

    instructions = []
    in_block = False
    for line in lines:
        line = line.strip()
        if line == "BEGIN":
            in_block = True
            continue
        elif line == "END":
            in_block = False
            continue
        if in_block:
            instr = int(line, 16)
            instructions.append(instr)

    disassemble_instructions(instructions)
