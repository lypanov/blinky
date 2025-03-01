#!/usr/bin/env python3
import struct
import sys

def read_null_terminated_string(data, offset):
    """Read a null-terminated ASCII string starting at offset."""
    if offset >= len(data):
        raise ValueError(f"Offset {offset} is beyond end of data (length {len(data)})")
    
    end = data.find(b'\0', offset)
    if end == -1:
        # If we can't find a null terminator, assume the rest of the data is the string
        # (this is a fallback, not ideal)
        end = len(data)
        s = data[offset:end].decode('utf-8', errors='replace')
        return s, end
    
    s = data[offset:end].decode('utf-8', errors='replace')
    return s, end + 1

def read_int(data, offset):
    """Read a 4-byte little-endian integer from data at offset."""
    if offset + 4 > len(data):
        raise struct.error(f"Not enough bytes to read an integer at offset {offset} (data length {len(data)})")
    val = struct.unpack_from("<I", data, offset)[0]
    return val, offset + 4

class ImportedModule:
    def __init__(self, num, code=0, data=0, ent=0):
        self.num = num      # module number (from import table)
        self.code = code    # base address of its code section (dummy value for now)
        self.data = data    # base address of its data section (dummy value)
        self.ent = ent      # base address of its entry table (dummy value)

def fixup_ldr_str_add(code, fixorg_d, mod_num, imp_modules):
    MT = 12
    # Compute starting byte address
    adr_byte = fixorg_d * 4
    # Loop until adr_byte equals zero
    while adr_byte != 0:
        index = adr_byte // 4
        if index < 0 or index >= len(code):
            # Out-of-bound safeguard
            break
        inst = code[index]
        # Extract mno and disp
        mno = (inst // 0x100000) % 0x10
        disp = inst % 0x1000
        if disp == 0:
            # Avoid infinite loop if disp is zero
            break

        if mno == 0:
            # Global fixup
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (mod_num * 4)
            code[index] = new_inst
        else:
            # Import fixup
            imp_index = mno - 1
            impmod = imp_modules.get(imp_index, ImportedModule(0, 0, 0, 0))
            v = impmod.num
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (v * 4)
            code[index] = new_inst
            # Process the following word (if present)
            if index + 1 < len(code):
                inst_next = code[index + 1]
                vno = inst_next % 0x100
                # Simulate offset retrieval
                offset_val = impmod.ent
                # Adjust if odd
                if ((inst_next // 0x100) % 2) == 1:
                    offset_val += (impmod.code - impmod.data)
                new_inst_next = (inst_next // 0x10000) * 0x10000 + offset_val
                code[index + 1] = new_inst_next
        # Move backwards
        adr_byte = adr_byte - disp * 4
    return code

def parse_rsc(file_path, output_format="default", perform_fixup=False, mod_num=1):
    with open(file_path, "rb") as f:
        data = f.read()
    
    offset = 0
    
    # Skip parsing output if we're just extracting code
    if output_format != "code_only":
        print("=== Parsing .rsc file ===")

    # 1. Module header
    mod_id, offset = read_null_terminated_string(data, offset)
    if output_format != "code_only":
        print(f"Module ID: {mod_id}")
    
    key, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"Key: {key}")
    
    # Read version (assume 1 byte)
    if offset < len(data):
        version = data[offset]
        offset += 1
        if output_format != "code_only":
            print(f"Version: {version}")
    else:
        version = None
        if output_format != "code_only":
            print("Warning: Could not read version byte")
    
    file_size, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"File Size: {file_size} bytes")

    # 2. Import table
    if output_format != "code_only":
        print("\n-- Imports --")
    imports = []
    imp_modules = {}  # Map from import index to ImportedModule
    imp_index = 0
    
    while offset < len(data):
        if data[offset] == 0:
            offset += 1
            break
        imp_str, offset = read_null_terminated_string(data, offset)
        if offset + 4 <= len(data):
            imp_val, offset = read_int(data, offset)
            imports.append((imp_str, imp_val))
            # Create a dummy ImportedModule for this import
            imp_modules[imp_index] = ImportedModule(imp_val)
            imp_index += 1
            if output_format != "code_only":
                print(f"Imported Module: {imp_str}, value: {imp_val}")
        else:
            break
    
    # 3. Type descriptors section
    if offset + 4 <= len(data):
        td_byte_size, offset = read_int(data, offset)
        td_count = td_byte_size // 4
        if output_format != "code_only":
            print(f"\nType Descriptor Section: {td_byte_size} bytes ({td_count} integers)")
        type_descriptors = []
        for i in range(td_count):
            if offset + 4 <= len(data):
                val, offset = read_int(data, offset)
                type_descriptors.append(val)
            else:
                break
        if output_format != "code_only":
            print("Type Descriptors:", type_descriptors)
    else:
        td_byte_size = 0
        type_descriptors = []
        if output_format != "code_only":
            print("\nWarning: Could not read type descriptor size")

    # 4. Global variable data size
    if offset + 4 <= len(data):
        data_size, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nGlobal variable data size: {data_size} bytes")
    else:
        data_size = 0
        if output_format != "code_only":
            print("\nWarning: Could not read global variable data size")

    # 5. String table
    if offset + 4 <= len(data):
        strx, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nString Table Length: {strx} bytes")
        if offset + strx <= len(data):
            string_table = data[offset:offset+strx]
            offset += strx
            if output_format != "code_only":
                try:
                    print("String Table content:", string_table.decode('utf-8', errors='replace'))
                except Exception as e:
                    print("Error decoding string table:", e)
        else:
            string_table = b''
            if output_format != "code_only":
                print("Warning: String table extends beyond file end")
    else:
        strx = 0
        string_table = b''
        if output_format != "code_only":
            print("\nWarning: Could not read string table length")

    # 6. Code section
    if offset + 4 <= len(data):
        code_len, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nCode Section: {code_len} instruction(s)")
        code = []
        for i in range(code_len):
            if offset + 4 <= len(data):
                inst, offset = read_int(data, offset)
                code.append(inst)
            else:
                if output_format != "code_only":
                    print(f"Warning: Expected {code_len} instructions, but only read {i}")
                break
    else:
        code_len = 0
        code = []
        if output_format != "code_only":
            print("\nWarning: Could not read code length")
    
    # Try to find fixup values
    fix_org_p = fix_org_d = fix_org_t = None
    
    # Skip commands section if present
    if output_format != "code_only":
        print("\n-- Commands --")
    
    # Try to safely skip the commands section
    try:
        # First check if we have a zero byte (empty commands section)
        if offset < len(data) and data[offset] == 0:
            offset += 1
        else:
            # Otherwise try to read commands until we hit a zero or run out of data
            while offset < len(data):
                # Check if we've reached the end of commands (zero byte)
                if data[offset] == 0:
                    offset += 1
                    break
                
                # Try to read a command name
                try:
                    cmd_name, offset = read_null_terminated_string(data, offset)
                    if output_format != "code_only":
                        print(f"Command name: {cmd_name}")
                    
                    # Try to read the command value
                    if offset + 4 <= len(data):
                        cmd_val, offset = read_int(data, offset)
                        if output_format != "code_only":
                            print(f"Command value: {cmd_val}")
                    else:
                        break
                except ValueError:
                    # If we can't read a string, we've probably reached the end
                    break
    except Exception as e:
        if output_format != "code_only":
            print(f"Error parsing commands: {e}")
    
    # Try to read entries section
    n_of_ent = entry_point = None
    if offset + 8 <= len(data):
        try:
            n_of_ent, offset = read_int(data, offset)
            entry_point, offset = read_int(data, offset)
            if output_format != "code_only":
                print(f"\nNumber of Entries: {n_of_ent}")
                print(f"Entry Point: {entry_point}")
            
            # Skip entry values
            for _ in range(n_of_ent):
                if offset + 4 <= len(data):
                    _, offset = read_int(data, offset)
                else:
                    break
        except Exception as e:
            if output_format != "code_only":
                print(f"Error reading entries: {e}")
    
    # Try to skip pointer variables
    if output_format != "code_only":
        print("\n-- Pointer Variables --")
    try:
        while offset + 4 <= len(data):
            ptr, offset = read_int(data, offset)
            if ptr == 0xFFFFFFFF:
                offset += 4  # Skip the sentinel
                break
            if output_format != "code_only":
                print(f"Pointer: {ptr}")
    except Exception as e:
        if output_format != "code_only":
            print(f"Error reading pointers: {e}")
    
    # Try to read fixup values
    if offset + 12 <= len(data):
        try:
            fix_org_p, offset = read_int(data, offset)
            fix_org_d, offset = read_int(data, offset)
            fix_org_t, offset = read_int(data, offset)
            if output_format != "code_only":
                print(f"\nFixup Values: fixOrgP = {fix_org_p}, fixOrgD = {fix_org_d}, fixOrgT = {fix_org_t}")
        except Exception as e:
            if output_format != "code_only":
                print(f"Error reading fixup values: {e}")
    else:
        if output_format != "code_only":
            print("\nNot enough bytes for fixup values.")
    
    # Perform fixup if requested and possible
    if output_format != "code_only":
        print(f"Performing fixup: {perform_fixup} && {fix_org_d is not None} (fix_org_d: {fix_org_d})")
    
    if perform_fixup and fix_org_d is not None:
        code = fixup_ldr_str_add(code, fix_org_d, mod_num, imp_modules)
    
    # Output code in the requested format
    if output_format == "code_only" or perform_fixup:
        print("BEGIN")
        for inst in code:
            print(f"0x{inst:08x}")
        print("END")
    elif output_format == "default":
        print("Program Code:")
        for i, inst in enumerate(code):
            print(f"  {i:04}: 0x{inst:08x}")
    
    if output_format != "code_only":
        print("\n=== End of .rsc Parsing ===")
    
    return {
        "module_id": mod_id,
        "key": key,
        "version": version,
        "file_size": file_size,
        "imports": imports,
        "type_descriptors": type_descriptors,
        "data_size": data_size,
        "string_table": string_table,
        "code": code,
        "fix_org": (fix_org_p, fix_org_d, fix_org_t)
    }

if __name__ == "__main__":
    usage = "Usage: python parser.py <path_to_file.rsc> [code_only|fixup]"
    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)
    
    mode = "default"
    perform_fixup = False
    if len(sys.argv) > 2:
        if sys.argv[2] == "code_only":
            mode = "code_only"
        elif sys.argv[2] == "fixup":
            mode = "code_only"
            perform_fixup = True

    parse_rsc(sys.argv[1], output_format=mode, perform_fixup=perform_fixup)
