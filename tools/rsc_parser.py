#!/usr/bin/env python3
import struct
import sys

# Global module table: emulates the Oberon MT register.
mt_table = {}

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
        raise struct.error(f"Not enough bytes at offset {offset}")
    val = struct.unpack_from("<I", data, offset)[0]
    return val, offset + 4

class ImportedModule:
    def __init__(self, num, code=0, data=0, ent=0):
        self.num = num      # module number (from import table)
        self.code = code    # base address of its code section (dummy value for now)
        self.data = data    # base address of its data section (dummy value)
        self.ent = ent      # base address of its entry table (dummy value)

def fixup_ldr_str_add(code, fixorg_d, mod_num, mt):
    """
    Fixup for LDR/STR/ADD instructions that uses the emulated MT table.
    """
    MT = 12
    adr_byte = fixorg_d * 4
    while adr_byte != 0:
        index = adr_byte // 4
        if index < 0 or index >= len(code):
            break
        inst = code[index]
        mno = (inst // 0x100000) % 0x10
        disp = inst % 0x1000
        if disp == 0:
            break

        if mno == 0:
            # Global fixup: use current module's number from the MT table.
            current_mod = mt.get(mod_num)
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (mod_num * 4)
            code[index] = new_inst
        else:
            # For imported modules, try looking them up in the MT table.
            imp = mt.get(mno, ImportedModule(0, 0, 0, 0))
            v = imp.num
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (v * 4)
            code[index] = new_inst
            if index + 1 < len(code):
                inst_next = code[index + 1]
                vno = inst_next % 0x100
                offset_val = imp.ent
                if ((inst_next // 0x100) % 2) == 1:
                    offset_val += (imp.code - imp.data)
                new_inst_next = ((inst_next // 0x10000) * 0x10000) + offset_val
                code[index + 1] = new_inst_next
        adr_byte = adr_byte - disp * 4
    return code

def fixup_bl(code, fixorg_p, mod_num, mt):
    """
    Fixup for BL (branch link) instructions that uses the emulated MT table.
    Instead of discarding the original module information, we use the MT table (mt)
    to look up the imported module's descriptor.
    """
    MT = 12  # Constant from Oberon (if needed for adjustments)
    adr_byte = fixorg_p * 4
    while adr_byte != 0:
        index = adr_byte // 4
        if index < 0 or index >= len(code):
            break
        inst = code[index]
        mno = (inst // 0x100000) % 0x10
        pno = (inst // 0x1000) % 0x100
        disp = inst % 0x1000
        if disp == 0:
            # Prevent infinite loop if disp is zero.
            break

        if mno != 0:
            # Retrieve the imported module using the global table.
            impmod = mt.get(mno, ImportedModule(0, 0, 0, 0))
            # Simulate the original Modules.Mod logic:
            #   dest := (impmod.ent + pno*4) + impmod.code
            dest = impmod.ent + (pno * 4) + impmod.code
            offset = (dest - adr_byte - 4) // 4
            new_inst = (offset % 0x1000000) + 0xF7000000
            code[index] = new_inst
        else:
            # For a global (non-import) reference, use the current module from the MT table.
            current_mod = mt.get(mod_num)
            # You may wish to adjust further if needed.
            # Here we leave it as is since no special fixup may be required.
        adr_byte = adr_byte - disp * 4
    return code

def fixup_type(type_descriptors, fixorg_t, mod_data, mt):
    """
    Fixup for type descriptors using the emulated MT table.
    """
    adr = fixorg_t  # Use this as the index into the type descriptor list.
    while adr != 0 and adr < len(type_descriptors):
        inst = type_descriptors[adr]
        mno = (inst // 0x1000000) % 0x10
        vno = (inst // 0x1000) % 0x1000
        disp = inst % 0x1000
        if mno == 0:
            new_inst = mod_data + vno
        else:
            imp = mt.get(mno, ImportedModule(0, 0, 0, 0))
            new_inst = imp.data + (imp.ent + vno * 4)
        type_descriptors[adr] = new_inst
        if disp == 0:
            break
        adr = adr - disp
    return type_descriptors

def parse_rsc(file_path, output_format="default", perform_fixup=False, mod_num=1):
    with open(file_path, "rb") as f:
        data = f.read()
    
    offset = 0
    
    if output_format != "code_only":
        print("=== Parsing .rsc file ===")

    # 1. Module header
    mod_id, offset = read_null_terminated_string(data, offset)
    if output_format != "code_only":
        print(f"Module ID: {mod_id}")
    
    key, offset = read_int(data, offset)
    if output_format != "code_only":
        print(f"Key: {key}")
    
    if offset < len(data):
        version = data[offset]
        offset += 1
        if output_format != "code_only":
            print(f"Version: {version}")
    else:
        version = None
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
        for _ in range(td_count):
            if offset + 4 <= len(data):
                val, offset = read_int(data, offset)
                type_descriptors.append(val)
            else:
                break
    else:
        type_descriptors = []
        print("\nWarning: Could not read type descriptor size")

    # 4. Global variable data size
    if offset + 4 <= len(data):
        data_size, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nGlobal variable data size: {data_size} bytes")
    else:
        data_size = 0
        print("\nWarning: Could not read variable space size")

    # 5. String table
    if offset + 4 <= len(data):
        strx, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nString Table Length: {strx} bytes")
        if offset + strx <= len(data):
            string_table = data[offset:offset + strx]
            offset += strx
            if output_format != "code_only":
                print("String Table content:", string_table.decode('utf-8', errors='replace'))
        else:
            string_table = b''
            print("Warning: String table extends beyond file end")
    else:
        string_table = b''
        print("\nWarning: Could not read string table length")

    # 6. Code section
    if offset + 4 <= len(data):
        code_len, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nCode Section: {code_len} instruction(s)")
        code = []
        for _ in range(code_len):
            if offset + 4 <= len(data):
                inst, offset = read_int(data, offset)
                code.append(inst)
            else:
                print(f"Warning: Expected {code_len} instructions, read fewer")
                break
    else:
        code = []
        print("\nWarning: Could not read code length")

    # 10. Commands
    if output_format != "code_only":
        print("\n-- Commands --")
    while offset < len(data):
        if data[offset] == 0:
            offset += 1
            break
        cmd_name, offset = read_null_terminated_string(data, offset)
        if output_format != "code_only":
            print(f"Command name: {cmd_name}")
        if offset + 4 <= len(data):
            cmd_val, offset = read_int(data, offset)
            if output_format != "code_only":
                print(f"Command value: {cmd_val}")
        else:
            print("Warning: Incomplete command entry")
            break

    # 11. Entries
    if offset + 4 <= len(data):
        nofent, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nNumber of Entries: {nofent}")
        entries = []
        for _ in range(nofent):
            if offset + 4 <= len(data):
                ent_val, offset = read_int(data, offset)
                entries.append(ent_val)
            else:
                print(f"Warning: Could not read all {nofent} entries")
                break
        if output_format != "code_only":
            print(f"Entries: {entries}")
    else:
        entries = []
        print("Warning: Could not read number of entries")

    # 12. Pointer References
    if output_format != "code_only":
        print("\n-- Pointer References --")
    pointer_refs = []
    while offset + 4 <= len(data):
        ptr, offset = read_int(data, offset)
        if ptr == 0xFFFFFFFF:
            break
        pointer_refs.append(ptr)
    if output_format != "code_only":
        print(f"Pointer References: {pointer_refs}")

    # 13 & 14. Fixup Origins and Entry Point
    if offset + 16 <= len(data):
        fix_org_p, offset = read_int(data, offset)
        fix_org_d, offset = read_int(data, offset)
        fix_org_t, offset = read_int(data, offset)
        entry_point, offset = read_int(data, offset)
        if output_format != "code_only":
            print(f"\nFixup Origins: fixOrgP = {fix_org_p}, fixOrgD = {fix_org_d}, fixOrgT = {fix_org_t}")
            print(f"Entry Point: {entry_point}")
    else:
        print("Warning: Could not read fixup origins and entry point")

    # 15. Marker
    if offset < len(data):
        marker = data[offset]
        if marker == ord('O'):
            if output_format != "code_only":
                print("Marker: 'O'")
        else:
            print(f"Warning: Unexpected marker: {marker}")
    else:
        print("Warning: No marker found")

    # Default module number (for global fixups)
    mod_num = 1

    # Create a descriptor for the current module.
    # For example, we assume the module's code base is at index 0 and data base 0 in our simulation.
    current_module = ImportedModule(mod_num, code=0, data=0, ent=0)
    mt_table[mod_num] = current_module

    # Perform fixup
    if perform_fixup:
        code = fixup_bl(code, fix_org_p, mod_num, mt_table)
        code = fixup_ldr_str_add(code, fix_org_d, mod_num, mt_table)
        type_descriptors = fixup_type(type_descriptors, fix_org_t, 0, mt_table)

    # Output code
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
        "fix_org": (fix_org_p, fix_org_d, fix_org_t),
        "entries": entries,
        "pointer_refs": pointer_refs,
        "entry_point": entry_point
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
