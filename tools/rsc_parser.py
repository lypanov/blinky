#!/usr/bin/env python3
import struct
import sys

def read_null_terminated_string(data, offset):
    """Read a null-terminated ASCII string starting at offset."""
    end = data.find(b'\0', offset)
    if end == -1:
        raise ValueError("Null terminator not found in data starting at offset {}".format(offset))
    s = data[offset:end].decode('utf-8', errors='replace')
    return s, end + 1

def read_int(data, offset):
    """Read a 4-byte little-endian integer from data at offset."""
    if offset + 4 > len(data):
        raise struct.error("Not enough bytes to read an integer at offset {}".format(offset))
    val = struct.unpack_from("<I", data, offset)[0]
    return val, offset + 4

def parse_rsc(file_path, output_format="default"):
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
    version = data[offset]
    offset += 1
    if output_format != "code_only":
        print(f"Version: {version}")
    
    file_size, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"File Size: {file_size} bytes")

    # 2. Import table
    if output_format != "code_only":
        print("\n-- Imports --")
    imports = []
    while True:
        if data[offset] == 0:
            offset += 1
            break
        imp_str, offset = read_null_terminated_string(data, offset)
        imp_val, offset = read_int(data, offset)
        imports.append((imp_str, imp_val))
    if output_format != "code_only":
        for imp in imports:
            print(f"Imported Module: {imp[0]}, value: {imp[1]}")
    
    # 3. Type descriptors section
    td_byte_size, offset = read_int(data, offset)
    td_count = td_byte_size // 4
    if output_format != "code_only":
        print(f"\nType Descriptor Section: {td_byte_size} bytes ({td_count} integers)")
    type_descriptors = []
    for i in range(td_count):
        val, offset = read_int(data, offset)
        type_descriptors.append(val)
    if output_format != "code_only":
        print("Type Descriptors:", type_descriptors)

    # 4. Global variable data size (remaining after type descriptors)
    data_size, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"\nGlobal variable data size: {data_size} bytes")

    # 5. String table
    strx, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"\nString Table Length: {strx} bytes")
    string_table = data[offset:offset+strx]
    offset += strx
    if output_format != "code_only":
        try:
            print("String Table content:", string_table.decode('utf-8', errors='replace'))
        except Exception as e:
            print("Error decoding string table:", e)

    # 6. Code section
    code_len, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"\nCode Section: {code_len} instruction(s)")
    code = []
    for i in range(code_len):
        inst, offset = read_int(data, offset)
        code.append(inst)
    
    # Output code in the requested format
    if output_format == "code_only":
        print("BEGIN")
        for inst in code:
            print(f"0x{inst:08x}")
        print("END")
    elif output_format == "default":
        print("Program Code:")
        for i, inst in enumerate(code):
            print(f"  {i:04}: {inst:#010x}")

    # Skip the rest of parsing if we're just extracting code
    if output_format == "code_only":
        return {"code": code}

    # 7. Commands section (if any)
    print("\n-- Commands --")
    commands = []
    while True:
        if data[offset] == 0:
            offset += 1
            break
        cmd, offset = read_null_terminated_string(data, offset)
        cmd_val, offset = read_int(data, offset)
        commands.append((cmd, cmd_val))
    for cmd in commands:
        print(f"Command: {cmd[0]}, value: {cmd[1]}")

    # 8. Entries and final fields
    n_of_ent, offset = read_int(data, offset)
    print(f"\nNumber of Entries: {n_of_ent}")
    
    entry_point, offset = read_int(data, offset)
    print(f"Entry Point: {entry_point}")

    entries = []
    for i in range(n_of_ent):
        ent, offset = read_int(data, offset)
        entries.append(ent)
    print("Entries:", entries)

    print("\n-- Pointer Variables --")
    pointers = []
    # Read pointer variables until we hit the sentinel (0xFFFFFFFF)
    while offset + 4 <= len(data):
        ptr, offset = read_int(data, offset)
        if ptr == 0xFFFFFFFF:
            break
        pointers.append(ptr)
    print("Pointer Variables:", pointers)

    if offset + 12 <= len(data):
        fix_org_p, offset = read_int(data, offset)
        fix_org_d, offset = read_int(data, offset)
        fix_org_t, offset = read_int(data, offset)
        print(f"\nFixup Values: fixOrgP = {fix_org_p}, fixOrgD = {fix_org_d}, fixOrgT = {fix_org_t}")
    else:
        print("\nNot enough bytes for fixup values.")

    if offset + 4 <= len(data):
        entry_point2, offset = read_int(data, offset)
        print(f"Entry Point (again): {entry_point2}")
    else:
        print("Not enough bytes for second entry point.")

    if offset < len(data):
        final_char = data[offset:offset+1].decode('utf-8', errors='replace')
        offset += 1
        print(f"Final character: {final_char}")
    else:
        print("No final character.")

    print("\n=== End of .rsc Parsing ===")
    
    # Return all parsed data as a dictionary (if needed for further processing)
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
         "commands": commands,
         "n_of_entries": n_of_ent,
         "entry_point": entry_point,
         "entries": entries,
         "pointers": pointers,
         "fix_org": (fix_org_p if 'fix_org_p' in locals() else None,
                     fix_org_d if 'fix_org_d' in locals() else None,
                     fix_org_t if 'fix_org_t' in locals() else None),
         "entry_point2": entry_point2 if 'entry_point2' in locals() else None,
         "final_char": final_char if 'final_char' in locals() else None,
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parser.py <path_to_file.rsc> [code_only]")
        sys.exit(1)
    
    output_format = "code_only" if len(sys.argv) > 2 and sys.argv[2] == "code_only" else "default"
    parse_rsc(sys.argv[1], output_format)
