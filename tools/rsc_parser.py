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

class ImportedModule:
    def __init__(self, num, code=0, data=0, ent=0):
        self.num = num      # module number (from import table)
        self.code = code    # base address of its code section (dummy value for now)
        self.data = data    # base address of its data section (dummy value)
        self.ent = ent      # base address of its entry table (dummy value)

def fixup_ldr_str_add(code, fixorg_d, mod_num, imp_modules):
    print(f"fixup_ldr_str_add: {fixorg_d} {mod_num} {imp_modules}")
    MT = 12
    # Compute starting byte address. In the .rsc file, instructions are stored as 4-byte words.
    # We assume that mod.code is at byte address 0.
    adr_byte = fixorg_d * 4
    # Loop until adr_byte equals zero (i.e. we've reached the start of mod.code).
    print(f"adr_byte: {adr_byte}")
    while adr_byte != 0:
        print(f"adr_byte: {adr_byte}")
        index = adr_byte // 4
        if index < 0 or index >= len(code):
            print(f"index: {index} out of bounds")
            # Out-of-bound safeguard: break if we step beyond available code.
            break
        inst = code[index]
        # Extract mno:
        #   mno = (inst DIV 0x100000) MOD 0x10.
        mno = (inst // 0x100000) % 0x10
        # disp = inst MOD 0x1000
        disp = inst % 0x1000
        if disp == 0:
            # Avoid infinite loop if disp is zero.
            break

        if mno == 0:
            # Global fixup.
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (mod_num * 4)
            code[index] = new_inst
        else:
            # Import fixup.
            imp_index = mno - 1
            impmod = imp_modules.get(imp_index, ImportedModule(0, 0, 0, 0))
            v = impmod.num
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (v * 4)
            code[index] = new_inst
            # Process the following word (assume it is present).
            if index + 1 < len(code):
                inst_next = code[index + 1]
                vno = inst_next % 0x100
                # In the canonical code:
                #   offset := value retrieved from (impmod.ent + vno*4).
                # Here, we simulate it with impmod.ent (dummy value).
                offset_val = impmod.ent
                # If the quotient (from dividing inst_next by 0x100) is odd then add (impmod.code - impmod.data).
                if ((inst_next // 0x100) % 2) == 1:
                    offset_val += (impmod.code - impmod.data)
                new_inst_next = (inst_next // 0x10000) * 0x10000 + offset_val
                code[index + 1] = new_inst_next
        # Subtract disp*4 (in bytes) from adr_byte. This moves us backwards toward mod.code.
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
    
    # Build a dictionary of imported modules (dummy values for code, data, ent)
    imp_modules = {}
    for i, (name, val) in enumerate(imports):
        # For now, we assume impmod.num comes directly from the import value;
        # other fields are set to zero.
        imp_modules[i] = ImportedModule(num=val, code=0, data=0, ent=0)
    
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
    
    # If fixup is requested, perform the linking fixup for LDR/STR/ADD instructions.
    fix_org_d = None
    # The fixup fields follow later in the file; parse them if available.
    # Advance through commands section.
    while offset < len(data) and data[offset] != 0:
        _, offset = read_null_terminated_string(data, offset)
        _, offset = read_int(data, offset)
    if offset < len(data):
        offset += 1  # skip terminator

    # Skip over entries.
    n_of_ent, offset = read_int(data, offset)
    entry_point, offset = read_int(data, offset)
    for i in range(n_of_ent):
        _, offset = read_int(data, offset)
    # Skip pointer variables until sentinel 0xFFFFFFFF.
    while offset + 4 <= len(data):
        ptr, offset = read_int(data, offset)
        if ptr == 0xFFFFFFFF:
            break
    # Read fixup fields if available.
    fix_org_p = fix_org_d = fix_org_t = None
    if offset + 12 <= len(data):
        fix_org_p, offset = read_int(data, offset)
        fix_org_d, offset = read_int(data, offset)
        fix_org_t, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nFixup Values: fixOrgP = {fix_org_p}, fixOrgD = {fix_org_d}, fixOrgT = {fix_org_t}")
    else:
        if output_format != "code_only":
            print("\nNot enough bytes for fixup values.")
    
    print(f"Performing fixup: {perform_fixup} && {fix_org_d is not None} (fix_org_d: {fix_org_d})")
    if perform_fixup and fix_org_d is not None:
        print("Performing fixup...")
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
    print(f"\nNumber of Entries: {n_of_ent}")
    
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
         "fix_org": (fix_org_p, fix_org_d, fix_org_t),
         "entry_point2": entry_point2 if 'entry_point2' in locals() else None,
         "final_char": final_char if 'final_char' in locals() else None,
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
