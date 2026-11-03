#!/usr/bin/env python3
import struct
import sys
from mt_table import mt_table  # Import the shared global module table

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
    def __init__(self, num, code=0, data=0, ent=0, entries=None):
        self.num = num      # module number (mod.num in Modules.Mod)
        self.code = code    # base address of its code section
        self.data = data    # base address of its data section
        self.ent = ent      # unused (Modules.Mod reads entries[] from memory)
        self.entries = list(entries or [])  # object-file entry table (byte offsets)

    def entry_at(self, pno):
        if pno < 0 or pno >= len(self.entries):
            raise IndexError(
                f"entry {pno} out of range for module {self.num} "
                f"(have {len(self.entries)} entries)"
            )
        return self.entries[pno]


def _import_mod(imports, mno, mt):
    """Modules.Mod: SYSTEM.GET(mod.imp + (mno-1)*4, impmod)."""
    if imports is not None:
        if mno < 1 or mno > len(imports):
            raise IndexError(f"import mno={mno} out of range (have {len(imports)})")
        return imports[mno - 1]
    # Fallback for standalone parse_rsc --fixup: global MT keyed by mod.num.
    if mt is None or mno not in mt:
        raise KeyError(f"no imported module for mno={mno}")
    return mt[mno]


def fixup_ldr_str_add(code, fixorg_d, mod_num, mt, imports=None):
    """
    Fixup for LDR/STR/ADD. Matches Modules.Mod D-list.
    mno=0: rewrite to LDW/STW via MT (R12) at mod.num*4.
    mno!=0: import — MT slot of the imported module, and the following
    word's offset is entries[vno] (SYSTEM.GET(impmod.ent + vno*4)).
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

        if mno == 0:
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (mod_num * 4)
            code[index] = new_inst
        elif not imports and (mt is None or mno not in mt):
            pass  # standalone --fixup without a loaded import list
        else:
            imp = _import_mod(imports, mno, mt)
            v = imp.num
            new_inst = (((inst // 0x1000000) * 0x10 + MT) * 0x100000) + (v * 4)
            code[index] = new_inst
            if index + 1 < len(code):
                inst_next = code[index + 1]
                vno = inst_next % 0x100
                offset_val = imp.entry_at(vno)
                if ((inst_next // 0x100) % 2) == 1:
                    offset_val += (imp.code - imp.data)
                new_inst_next = ((inst_next // 0x10000) * 0x10000) + (offset_val & 0xFFFF)
                code[index + 1] = new_inst_next
        if disp == 0:
            break
        adr_byte = adr_byte - disp * 4
    return code

def fixup_bl(code, fixorg_p, code_base=0, imports=None, mod_num=None, mt=None):
    """
    Modules.Mod P-list (BL fixup), verbatim:

        adr := mod.code + fixorgP*4;
        WHILE adr # mod.code DO
          SYSTEM.GET(adr, inst);
          mno := inst DIV 100000H MOD 10H;
          pno := inst DIV 1000H MOD 100H;
          disp := inst MOD 1000H;
          SYSTEM.GET(mod.imp + (mno-1)*4, impmod);
          SYSTEM.GET(impmod.ent + pno*4, dest); dest := dest + impmod.code;
          offset := (dest - adr - 4) DIV 4;
          SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H);
          adr := adr - disp*4
        END

    `imports` is this module's import list (mod.imp). `code_base` is mod.code.
    The old (mod_num, mt) keyword form is accepted so parse_rsc --fixup still runs;
    it cannot relocate imported BLs without a real import list.
    """
    if imports is None:
        imports = []
        if mt is not None and mod_num is not None:
            # Best-effort: treat MT values as an import list keyed by mno.
            pass
    adr = code_base + fixorg_p * 4
    while adr != code_base:
        index = (adr - code_base) // 4
        if index < 0 or index >= len(code):
            break
        inst = code[index]
        mno = (inst // 0x100000) % 0x10
        pno = (inst // 0x1000) % 0x100
        disp = inst % 0x1000
        if mno != 0:
            if not imports and mt is None:
                # Standalone --fixup: leave the compiler placeholder.
                pass
            else:
                impmod = _import_mod(imports if imports else None, mno, mt)
                dest = impmod.entry_at(pno) + impmod.code
                offset = (dest - adr - 4) // 4
                code[index] = (offset % 0x1000000) + 0xF7000000
        next_adr = adr - disp * 4
        if next_adr == adr:
            break
        adr = next_adr
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
            imp = mt.get(mno - 1, ImportedModule(0, 0, 0, 0))
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
    verbose = output_format not in ("code_only", "quiet")
    
    if verbose:
        print("=== Parsing .rsc file ===")

    # 1. Module header
    mod_id, offset = read_null_terminated_string(data, offset)
    if verbose:
        print(f"Module ID: {mod_id}")
    
    key, offset = read_int(data, offset)
    if verbose:
        print(f"Key: {key}")
    
    if offset < len(data):
        version = data[offset]
        offset += 1
        if verbose:
            print(f"Version: {version}")
    else:
        version = None
        print("Warning: Could not read version byte")
    
    file_size, offset = read_int(data, offset)
    if verbose:
        print(f"File Size: {file_size} bytes")

    # 2. Import table
    if verbose:
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
            if verbose:
                print(f"Imported Module: {imp_str}, value: {imp_val}")
        else:
            break
    
    # 3. Type descriptors section
    if offset + 4 <= len(data):
        td_byte_size, offset = read_int(data, offset)
        td_count = td_byte_size // 4
        if verbose:
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
        if verbose:
            print(f"\nGlobal variable data size: {data_size} bytes")
    else:
        data_size = 0
        print("\nWarning: Could not read variable space size")

    # 5. String table
    if offset + 4 <= len(data):
        strx, offset = read_int(data, offset)
        if verbose:
            print(f"\nString Table Length: {strx} bytes")
        if offset + strx <= len(data):
            string_table = data[offset:offset + strx]
            offset += strx
            if verbose:
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
        if verbose:
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
    if verbose:
        print("\n-- Commands --")
    while offset < len(data):
        if data[offset] == 0:
            offset += 1
            break
        cmd_name, offset = read_null_terminated_string(data, offset)
        if verbose:
            print(f"Command name: {cmd_name}")
        if offset + 4 <= len(data):
            cmd_val, offset = read_int(data, offset)
            if verbose:
                print(f"Command value: {cmd_val}")
        else:
            print("Warning: Incomplete command entry")
            break

    # 11. Entries
    if offset + 4 <= len(data):
        nofent, offset = read_int(data, offset)
        if verbose:
            print(f"\nNumber of Entries: {nofent}")
        entries = []
        for _ in range(nofent):
            if offset + 4 <= len(data):
                ent_val, offset = read_int(data, offset)
                entries.append(ent_val)
            else:
                print(f"Warning: Could not read all {nofent} entries")
                break
        if verbose:
            print(f"Entries: {entries}")
    else:
        entries = []
        print("Warning: Could not read number of entries")

    # 12. Pointer References
    if verbose:
        print("\n-- Pointer References --")
    pointer_refs = []
    while offset + 4 <= len(data):
        ptr, offset = read_int(data, offset)
        if ptr == 0xFFFFFFFF:
            break
        pointer_refs.append(ptr)
    if verbose:
        print(f"Pointer References: {pointer_refs}")

    # 13 & 14. Fixup Origins and Entry Point
    if offset + 16 <= len(data):
        fix_org_p, offset = read_int(data, offset)
        fix_org_d, offset = read_int(data, offset)
        fix_org_t, offset = read_int(data, offset)
        entry_point, offset = read_int(data, offset)
        if verbose:
            print(f"\nFixup Origins: fixOrgP = {fix_org_p}, fixOrgD = {fix_org_d}, fixOrgT = {fix_org_t}")
            print(f"Entry Point: {entry_point}")
    else:
        print("Warning: Could not read fixup origins and entry point")

    # 15. Marker
    if offset < len(data):
        marker = data[offset]
        if marker == ord('O'):
            if verbose:
                print("Marker: 'O'")
        else:
            print(f"Warning: Unexpected marker: {marker}")
    else:
        print("Warning: No marker found")

    # Default module number (for global D-list fixups in standalone --fixup).
    # Do not write mt_table here: parse_rsc is also used while loading imports,
    # and stuffing a dummy at key 1 used to wipe the real module table.
    mod_num = 1

    # Perform fixup
    if perform_fixup:
        # Standalone --fixup has no loaded import list, so imported BLs are
        # left as compiler placeholders. Linked images go through module_loader.
        code = fixup_bl(code, fix_org_p, code_base=0, imports=[])
        code = fixup_ldr_str_add(code, fix_org_d, mod_num, mt_table, imports=[])
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

    if verbose:
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
