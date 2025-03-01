#!/usr/bin/env python3

import re
import sys
import os
from collections import defaultdict
import argparse

# Constants from instruction_parser.py
op_names = ["MOV", "LSL", "ASR", "ROR", "AND", "ANN", "IOR", "XOR", "ADD", "SUB", "MUL", "DIV", "FAD", "FSB", "FML", "FDV"]
cond_names = ["MI", "EQ", "CS", "VS", "LS", "LT", "LE", "T", "PL", "NE", "CC", "VC", "HI", "GE", "GT", "F"]

# Disassemble function from instruction_parser.py
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
    return "Unknown instruction format"

class Instruction:
    def __init__(self, addr, hex_code, disasm=""):
        self.addr = addr
        self.hex_code = hex_code.replace("0x", "").upper()
        self.disasm = disasm
        self.instr_int = int(self.hex_code, 16)
        self.format = self._get_format()
        self.fields = self._parse_fields()
        
    def _get_format(self):
        type_bits = (self.instr_int >> 30) & 0x3
        if type_bits == 0:
            return "F0"  # Register operations
        elif type_bits == 1:
            return "F1"  # Immediate operations
        elif type_bits == 2:
            return "F2"  # Memory operations
        elif type_bits == 3:
            return "F3"  # Branch operations
        return "Unknown"
            
    def _parse_fields(self):
        instr = self.instr_int
        fields = {}
        
        # Common fields for all formats
        fields["type"] = (instr >> 30) & 0x3
        
        if self.format == "F0":  # Register operations
            fields["u"] = (instr >> 29) & 1
            fields["a"] = (instr >> 24) & 0xF
            fields["b"] = (instr >> 20) & 0xF
            fields["op"] = (instr >> 16) & 0xF
            fields["c"] = instr & 0xF
            
        elif self.format == "F1":  # Immediate operations
            fields["u"] = (instr >> 29) & 1
            fields["v"] = (instr >> 28) & 1
            fields["a"] = (instr >> 24) & 0xF
            fields["b"] = (instr >> 20) & 0xF
            fields["op"] = (instr >> 16) & 0xF
            fields["imm"] = instr & 0xFFFF
            
        elif self.format == "F2":  # Memory operations
            fields["u"] = (instr >> 29) & 1
            fields["v"] = (instr >> 28) & 1
            fields["a"] = (instr >> 24) & 0xF
            fields["b"] = (instr >> 20) & 0xF
            fields["off"] = instr & 0xFFFFF
            
        elif self.format == "F3":  # Branch operations
            fields["bit29"] = (instr >> 29) & 1
            fields["v"] = (instr >> 28) & 1
            fields["cond"] = (instr >> 24) & 0xF
            if fields["bit29"] == 0:  # Branch to register
                fields["c"] = instr & 0xF
            else:  # Branch to offset
                fields["off"] = instr & 0xFFFFFF
                if fields["off"] & 0x800000:
                    fields["off"] -= 0x1000000  # Sign extend
            
        return fields
    
    def get_disassembly(self):
        """Generate disassembly if not provided"""
        if self.disasm:
            return self.disasm
        
        return disassemble(self.instr_int)
        
    def __str__(self):
        result = f"0x{self.addr:08x}: 0x{self.hex_code} - {self.get_disassembly()} (Format: {self.format})"
        
        if self.format == "F0":
            result += f"\n  Dest: R{self.fields['a']}, Src1: R{self.fields['b']}, Op: {self.fields['op']}, Src2: R{self.fields['c']}"
        elif self.format == "F1":
            result += f"\n  Dest: R{self.fields['a']}, Src: R{self.fields['b']}, Op: {self.fields['op']}, Imm: {self.fields['imm']:#x}"
        elif self.format == "F2":
            op_type = "Store" if self.fields['u'] else "Load"
            size = "Byte" if self.fields['v'] else "Word"
            result += f"\n  {op_type} {size}: R{self.fields['a']}, [R{self.fields['b']}, {self.fields['off']:#x}]"
        elif self.format == "F3":
            if self.fields["bit29"] == 0:  # Branch to register
                result += f"\n  Branch to register: Cond: {self.fields['cond']} ({cond_names[self.fields['cond']]}), Reg: R{self.fields['c']}"
            else:  # Branch to offset
                target = (self.addr + 4 + (self.fields['off'] * 4)) & 0xFFFFFFFF
                result += f"\n  Branch: Cond: {self.fields['cond']} ({cond_names[self.fields['cond']]}), Offset: {self.fields['off']} (Target: 0x{target:08x})"
        
        return result


class TraceAnalyzer:
    def __init__(self, trace_file):
        self.trace_file = trace_file
        self.instructions = {}
        self.trace_blocks = []
        self.instruction_list = []  # Will hold instructions discovered in trace
        self.load_trace_file()
        
    def load_trace_file(self):
        """Load the trace file and parse trace data"""
        if not os.path.exists(self.trace_file):
            print(f"Error: Trace file {self.trace_file} not found")
            sys.exit(1)
            
        # Define patterns for parsing
        pc_pattern = r"PC:\s+(\d+), Instruction: ([0-9a-fA-F]+)"
        reg_pattern = r"R0:\s+(\d+), R1:\s+(\d+), R2:\s+(\d+), R3:\s+(\d+), Z:\s+([01])"
        format_pattern = r"Format:\s+(\d+), A:\s+(\d+), B:\s+(\d+), OP:\s+(\d+), IMM:\s+(\d+)"
        write_pattern = r"Writing\s+(\d+) to register\s+(\d+)"
        instr_mem_pattern = r"INSTR_MEM\[(\d+)\] = 0x([0-9a-fA-F]+)"
        
        # Read the trace file
        with open(self.trace_file, 'r') as f:
            lines = f.readlines()
        
        # First pass - extract the instruction memory contents
        for line in lines:
            instr_match = re.search(instr_mem_pattern, line.strip())
            if instr_match:
                idx = int(instr_match.group(1))
                hex_code = instr_match.group(2).upper()
                # Store in the instruction list (will expand if needed)
                while len(self.instruction_list) <= idx:
                    self.instruction_list.append(None)
                self.instruction_list[idx] = hex_code
                
                # Also create an instruction object at the appropriate address
                addr = idx * 4  # 4 bytes per instruction
                if addr not in self.instructions:
                    self.instructions[addr] = Instruction(addr, hex_code)
            
        # Second pass - process the trace blocks
        current_block = []
        pending_writes = []  # Store pending register writes for next instruction
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Preserve the original line before removing any prefixes
            original_line = line
            
            # Save any lines with FAILED for later inclusion - preserve prefix
            if "*** FAILED ***" in original_line:
                if current_block:
                    # Output failed messages immediately to the current block
                    current_block.append(original_line)
                continue
                
            # Remove the [120] prefix if present
            if line.startswith('['):
                line = line[line.find(']')+1:].strip()
            
            # Skip instruction memory lines
            if re.search(instr_mem_pattern, line):
                continue
                
            # If we see a register write, store it for the next instruction block
            write_match = re.search(write_pattern, line)
            if write_match:
                pending_writes.append(line)
                continue
                
            pc_match = re.search(pc_pattern, line)
            if pc_match:
                if current_block:
                    self.trace_blocks.append(current_block)
                # Start a new block with pending writes from previous instructions
                current_block = pending_writes + [line]
                pending_writes = []  # Clear pending writes
            elif current_block and (
                re.search(reg_pattern, line) or 
                re.search(format_pattern, line)
            ):
                current_block.append(line)
            else:
                # If line doesn't match any known pattern, add it directly to current_block
                # Only add if we have a current block to add to
                if current_block:
                    current_block.append(original_line)
                
        # Add the last block if not empty
        if current_block:
            self.trace_blocks.append(current_block)
            
        # Analyze each block to extract instructions
        for i, block in enumerate(self.trace_blocks):
            pc_line = None
            for line in block:
                pc_match = re.search(pc_pattern, line)
                if pc_match:
                    pc = int(pc_match.group(1))
                    instr_hex = pc_match.group(2)
                    
                    # Create an instruction entry if not exists
                    if pc not in self.instructions:
                        self.instructions[pc] = Instruction(pc, instr_hex)
                    break
                    
    def _format_value_with_sign(self, value_str):
        """Convert a value to unsigned, signed, and hex representations"""
        try:
            value = int(value_str)
            unsigned_value = value
            # If the most significant bit is set (value > 2^31-1), interpret as negative
            if value > 0x7FFFFFFF:
                signed_value = value - 0x100000000  # 2^32
            else:
                signed_value = value
                
            # Get the hexadecimal representation (always 8 digits with leading zeros)
            hex_value = f"0x{value:08X}"
            
            # Show unsigned, signed (if negative), and hex for all values
            if signed_value < 0:
                return f"{unsigned_value}U | {signed_value} | {hex_value}"
            # For positive values, show the value and hex
            return f"{value} | {hex_value}"
        except ValueError:
            return value_str
        
    def analyze_trace(self):
        """Analyze the trace data and add annotations"""
        # Use the same patterns as in load_trace_file
        pc_pattern = r"PC:\s+(\d+), Instruction: ([0-9a-fA-F]+)"
        reg_pattern = r"R0:\s+(\d+), R1:\s+(\d+), R2:\s+(\d+), R3:\s+(\d+), Z:\s+([01])"
        format_pattern = r"Format:\s+(\d+), A:\s+(\d+), B:\s+(\d+), OP:\s+(\d+), IMM:\s+(\d+)"
        write_pattern = r"Writing\s+(\d+) to register\s+(\d+)"
        
        results = []
        
        # Process each block
        for block in self.trace_blocks:
            results.append(self.annotate_block(block))
            
        return results
        
    def annotate_block(self, block):
        """Annotate a block of trace output with instruction information"""
        # Use the same patterns as in load_trace_file
        pc_pattern = r"PC:\s+(\d+), Instruction: ([0-9a-fA-F]+)"
        reg_pattern = r"R0:\s+(\d+), R1:\s+(\d+), R2:\s+(\d+), R3:\s+(\d+), Z:\s+([01])"
        format_pattern = r"Format:\s+(\d+), A:\s+(\d+), B:\s+(\d+), OP:\s+(\d+), IMM:\s+(\d+)"
        write_pattern = r"Writing\s+(\d+) to register\s+(\d+)"
        
        # Create lists to track parsed and unparsed lines with their original positions
        parsed_lines = []
        unparsed_lines = []
        positions = {}
        
        for i, line in enumerate(block):
            positions[line] = i
            # Check if line matches any of our known patterns
            if (re.search(pc_pattern, line) or 
                re.search(reg_pattern, line) or 
                re.search(format_pattern, line) or 
                re.search(write_pattern, line)):
                parsed_lines.append(line)
            else:
                # Unparsed line (error message, etc.)
                unparsed_lines.append(line)
        
        pc_line = None
        for line in block:
            pc_match = re.search(pc_pattern, line)
            if pc_match:
                pc_line = line
                break
                
        if not pc_line:
            # If there's no PC line, just return the block as is
            return "\n".join(block)
            
        pc_match = re.search(pc_pattern, pc_line)
        pc = int(pc_match.group(1))
        instr_hex = pc_match.group(2)
        
        # Get or create the instruction
        instr = self.instructions.get(pc)
        if not instr:
            instr = Instruction(pc, instr_hex)
            self.instructions[pc] = instr
            
        # Create annotated output
        annotated = [f"===== PC: 0x{pc:08x} - {instr.get_disassembly()} ====="]
        annotated.append(f"Raw instruction: 0x{instr_hex} (32-bit: 0x{int(instr_hex, 16):08x})")
        annotated.append(f"Format: {instr.format} (type bits: 0x{instr.fields['type']:x})")
        
        # Add decoded fields based on format
        if instr.format == "F0":
            annotated.extend([
                f"Decoded fields:",
                f"  A (dest): R{instr.fields['a']}",
                f"  B (src1): R{instr.fields['b']}",
                f"  OP: {instr.fields['op']} ({op_names[instr.fields['op']]})",
                f"  C (src2): R{instr.fields['c']}",
                f"  u: {instr.fields['u']}"
            ])
        elif instr.format == "F1":
            annotated.extend([
                f"Decoded fields:",
                f"  A (dest): R{instr.fields['a']}",
                f"  B (src): R{instr.fields['b']}",
                f"  OP: {instr.fields['op']} ({op_names[instr.fields['op']]})",
                f"  IMM: 0x{instr.fields['imm']:04x} ({instr.fields['imm']})",
                f"  u/v: {instr.fields['u']}/{instr.fields['v']}"
            ])
        elif instr.format == "F2":
            op_type = "Store" if instr.fields['u'] else "Load"
            size = "Byte" if instr.fields['v'] else "Word"
            annotated.extend([
                f"Decoded fields:",
                f"  A (reg): R{instr.fields['a']}",
                f"  B (base): R{instr.fields['b']}",
                f"  Offset: 0x{instr.fields['off']:05x} ({instr.fields['off']})",
                f"  u/v: {instr.fields['u']}/{instr.fields['v']} ({op_type}/{size})"
            ])
        elif instr.format == "F3":
            annotated.extend([
                f"Decoded fields:",
                f"  Condition: {instr.fields['cond']} ({cond_names[instr.fields['cond']]})",
                f"  v (link): {instr.fields['v']}"
            ])
            if instr.fields["bit29"] == 0:  # Branch to register
                annotated.append(f"  C (reg): R{instr.fields['c']}")
            else:  # Branch to offset
                target = (pc + 4 + (instr.fields['off'] * 4)) & 0xFFFFFFFF
                annotated.append(f"  Offset: {instr.fields['off']} (Target: 0x{target:08x})")
        
        # Check for register writes - these are the actual effects of THIS instruction
        has_reg_write = False
        for line in block:
            write_match = re.search(write_pattern, line)
            if write_match:
                if not has_reg_write:
                    annotated.append("Execution Effects:")
                    has_reg_write = True
                value = write_match.group(1)
                formatted_value = self._format_value_with_sign(value)
                reg = write_match.group(2)
                annotated.append(f"  Writing R{reg} = {formatted_value}")
            
        # Add register state after execution
        for line in block:
            reg_match = re.search(reg_pattern, line)
            if reg_match:
                r0 = self._format_value_with_sign(reg_match.group(1))
                r1 = self._format_value_with_sign(reg_match.group(2))
                r2 = self._format_value_with_sign(reg_match.group(3))
                r3 = self._format_value_with_sign(reg_match.group(4))
                z = reg_match.group(5)
                annotated.append("Register State: (does not include execution effects)")
                annotated.append(f"  R0={r0}, R1={r1}, R2={r2}, R3={r3}, Z={z}")
                break
        
        # After the standard annotation, we add all unparsed lines
        # This keeps them in the same block but at the end of the annotations
        if unparsed_lines:
            for line in unparsed_lines:
                annotated.append(line)
                
        return "\n".join(annotated)
        
    def write_annotated_trace(self, output_file):
        """Write the annotated trace to a file"""
        annotated_blocks = self.analyze_trace()
        
        # Create instruction map from the instructions we extracted from the trace
        instruction_map = {}
        for idx, instr in enumerate(self.instruction_list):
            if instr:
                addr = idx * 4
                if addr not in self.instructions:
                    self.instructions[addr] = Instruction(addr, instr)
                instruction_map[addr] = self.instructions[addr]
        
        # If we didn't find any instructions in the trace, handle gracefully
        if not instruction_map:
            print("Warning: No instructions found in trace file. Analysis may be incomplete.")
            instruction_map = {}
        
        with open(output_file, 'w') as f:
            f.write("===========================================\n")
            f.write("CPU Trace Analysis - Annotated Instruction Trace\n")
            f.write("===========================================\n\n")
            
            f.write("Instructions in program:\n")
            f.write("----------------------\n")
            for addr in sorted(instruction_map.keys()):
                f.write(f"{instruction_map[addr]}\n\n")
                
            f.write("\n===========================================\n")
            f.write("Annotated Trace Output:\n")
            f.write("===========================================\n\n")
            
            for block in annotated_blocks:
                f.write(f"{block}\n\n")


def main():
    parser = argparse.ArgumentParser(description='Analyze CPU trace files')
    parser.add_argument('trace_file', help='Path to the CPU trace file')
    parser.add_argument('output_file', nargs='?', help='Path to the output annotated trace file (optional)')
    args = parser.parse_args()
    
    # If output file not specified, generate one based on input file
    if not args.output_file:
        # Extract base name without extension
        base_name = os.path.splitext(os.path.basename(args.trace_file))[0]
        # Replace cpu_trace with annotated_trace
        if base_name.startswith('cpu_trace'):
            output_base = base_name.replace('cpu_trace', 'annotated_trace')
        else:
            output_base = f"annotated_{base_name}"
        
        # Create output path
        output_dir = os.path.dirname(args.trace_file)
        args.output_file = os.path.join(output_dir, f"{output_base}.txt")
    
    analyzer = TraceAnalyzer(args.trace_file)
    analyzer.analyze_trace()
    analyzer.write_annotated_trace(args.output_file)
    
    print(f"Annotated trace written to {args.output_file}")


if __name__ == "__main__":
    main() 