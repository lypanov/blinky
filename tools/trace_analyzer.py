#!/usr/bin/env python3

import re
import sys
import os
from collections import defaultdict
import argparse

class Instruction:
    def __init__(self, addr, hex_code, disasm=""):
        self.addr = addr
        self.hex_code = hex_code.replace("0x", "").upper()
        self.disasm = disasm
        self.format = self._get_format()
        self.fields = self._parse_fields()
        
    def _get_format(self):
        instr = int(self.hex_code, 16)
        format_bits = (instr >> 28) & 0xF
        
        if format_bits in [0x4, 0x5]:
            return "F1"  # Immediate operations
        elif format_bits in [0x0, 0x1]:
            return "F0"  # Register operations
        elif format_bits in [0xE, 0xF]:
            return "F3"  # Branch operations
        else:
            return "Unknown"
            
    def _parse_fields(self):
        instr = int(self.hex_code, 16)
        fields = {}
        
        # Common fields for all formats
        fields["format"] = (instr >> 28) & 0xF
        
        if self.format == "F1":  # Immediate operations
            fields["a"] = (instr >> 24) & 0xF  # Destination register
            fields["b"] = (instr >> 20) & 0xF  # Source register
            fields["op"] = (instr >> 16) & 0xF  # Operation code
            fields["imm"] = instr & 0xFFFF  # Immediate value
            
        elif self.format == "F0":  # Register operations
            fields["a"] = (instr >> 24) & 0xF  # Destination register
            fields["b"] = (instr >> 20) & 0xF  # Source register 1
            fields["op"] = (instr >> 16) & 0xF  # Operation code
            fields["c"] = instr & 0xF  # Source register 2
            
        elif self.format == "F3":  # Branch operations
            fields["cond"] = (instr >> 24) & 0xF  # Branch condition
            fields["off"] = instr & 0xFFFFFF  # Offset
            # Sign extend the offset for display
            if fields["off"] & 0x800000:
                fields["off"] = fields["off"] | 0xFF000000
                
        return fields
    
    def get_disassembly(self):
        """Generate disassembly if not provided"""
        if self.disasm:
            return self.disasm
            
        if self.format == "F1":  # Immediate operations
            op = self.fields["op"]
            a = self.fields["a"]
            b = self.fields["b"]
            imm = self.fields["imm"]
            
            if op == 0:
                return f"MOV R{a}, {imm}"
            elif op == 7:
                return f"XOR R{a}, R{b}, {imm}"
            elif op == 8:
                return f"ADD R{a}, R{b}, {imm}"
            elif op == 9:
                return f"SUB R{a}, R{b}, {imm}"
            else:
                return f"Unknown F1 op: {op}"
                
        elif self.format == "F0":  # Register operations
            op = self.fields["op"]
            a = self.fields["a"]
            b = self.fields["b"]
            c = self.fields["c"]
            
            if op == 9:
                return f"SUB R{a}, R{b}, R{c}"
            else:
                return f"Unknown F0 op: {op}"
                
        elif self.format == "F3":  # Branch operations
            cond = self.fields["cond"]
            off = self.fields["off"]
            
            if cond == 1:
                return f"BEQ offset={off}"
            elif cond == 9:
                return f"BNE offset={off}"
            elif cond == 7:
                return f"B offset={off}"
            else:
                return f"Unknown branch condition: {cond}"
                
        return "Unknown instruction format"
        
    def __str__(self):
        result = f"0x{self.addr:08x}: 0x{self.hex_code} - {self.get_disassembly()} (Format: {self.format})"
        if self.format == "F1":
            result += f"\n  Dest: R{self.fields['a']}, Src: R{self.fields['b']}, Op: {self.fields['op']}, Imm: {self.fields['imm']}"
        elif self.format == "F0":
            result += f"\n  Dest: R{self.fields['a']}, Src1: R{self.fields['b']}, Op: {self.fields['op']}, Src2: R{self.fields['c']}"
        elif self.format == "F3":
            result += f"\n  Cond: {self.fields['cond']}, Offset: {self.fields['off']} (Target: 0x{(self.addr + 4 + (self.fields['off'] * 4)) & 0xFFFFFFFF:08x})"
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
            
        print(f"Analyzing trace file: {self.trace_file}")
        
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
        """Convert a value to both unsigned and signed representations"""
        try:
            value = int(value_str)
            unsigned_value = value
            # If the most significant bit is set (value > 2^31-1), interpret as negative
            if value > 0x7FFFFFFF:
                signed_value = value - 0x100000000  # 2^32
            else:
                signed_value = value
                
            # Only show both formats if they're different (value is negative)
            if signed_value < 0:
                return f"{unsigned_value}U | {signed_value}"
            return str(value)
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
        
        pc_line = None
        for line in block:
            pc_match = re.search(pc_pattern, line)
            if pc_match:
                pc_line = line
                break
                
        if not pc_line:
            return "\n".join(block)  # Return unchanged if no PC found
            
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
        annotated.append(f"Instruction: 0x{instr_hex} - Format: {instr.format}")
        
        if instr.format == "F1":
            annotated.append(f"  Dest: R{instr.fields['a']}, Src: R{instr.fields['b']}, Op: {instr.fields['op']}, Imm: {instr.fields['imm']}")
        elif instr.format == "F0":
            annotated.append(f"  Dest: R{instr.fields['a']}, Src1: R{instr.fields['b']}, Op: {instr.fields['op']}, Src2: R{instr.fields['c']}")
        elif instr.format == "F3":
            target = pc + 4 + (instr.fields['off'] * 4)
            annotated.append(f"  Cond: {instr.fields['cond']}, Offset: {instr.fields['off']} (Target: 0x{target & 0xFFFFFFFF:08x})")
        
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
                annotated.append("Register State:")
                annotated.append(f"  R0={r0}, R1={r1}, R2={r2}, R3={r3}, Z={z}")
                break
        
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
            # Check if we have any instructions from trace blocks
            for pc, instr in self.instructions.items():
                instruction_map[pc] = instr
        
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
    parser = argparse.ArgumentParser(description='Analyze CPU trace output')
    parser.add_argument('trace_file', help='Path to the trace file')
    parser.add_argument('-o', '--output', help='Output file for annotated trace', default='trace/annotated_trace.txt')
    
    args = parser.parse_args()
    
    analyzer = TraceAnalyzer(args.trace_file)
    analyzer.write_annotated_trace(args.output)
    
    print(f"Annotated trace written to {args.output}")


if __name__ == '__main__':
    main() 