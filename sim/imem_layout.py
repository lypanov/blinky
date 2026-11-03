"""Instruction-memory layout matching CPUSubset0.scala (sim visualizer only).

Default image: user code at 0x00, setup trampoline at 0x80, halt at 0xB0.
Blink3 custom image: same trampoline, modules from final_system.code at 0x1000+.
"""
from __future__ import annotations

SETUP_START = 0x80
SETUP_END = 0xB0
HALT_START = 0xB0
HALT_END = 0xC0
USER_END = 0x80
BEEF = 0x0000BEEF
HALT_WORD = 0xE7FFFFFF

# Must match CPUSubset0.scala setupInstructions.
SETUP = [
    (0x80, 0x4C000010, "MOV R12, 0x10     ; MT pointer"),
    (0x84, 0x4D000050, "MOV R13, 0x50     ; AMMT vars"),
    (0x88, 0xADC00004, "STW R13, [R12, 4] ; MT[1] = 0x50"),
    (0x8C, 0x4DD80020, "ADD R13, R13, 0x20"),
    (0x90, 0xADC00008, "STW R13, [R12, 8] ; MT[2] = 0x70"),
    (0x94, 0x4E000080, "MOV R14, 0x80     ; SP"),
    (0x98, 0x4F0000B0, "MOV R15, 0xB0     ; LNK = halt (preloaded — not BL)"),
    (0x9C, 0x40000000, "MOV R0, 0         ; user entry / trampoline at 0"),
    (0xA0, 0xC7000000, "BT R0             ; jump to address 0"),
]

# Blink3 linked image (unfixed Python loader). LightToggle entry = 0x1048.
BLINK3_ENTRY = 0x1048
BLINK3_BL_PC = 0x108C
BLINK3_WRONG_LAND = 0x1050
BLINK3_TOGGLE = 0x1000
BLINK3_RETURN = 0x1090  # PC+4 of the BL; CPU never writes this to R15
BLINK3_IMEM_WORDS = 0x1100 // 4  # 0x0000 .. 0x10FC


def setup_word(addr: int) -> int | None:
    for a, w, _ in SETUP:
        if a == addr:
            return w
    if SETUP_START <= addr < SETUP_END:
        return BEEF
    if HALT_START <= addr < HALT_END:
        return HALT_WORD
    return None


def default_imem(user_words: list[int]) -> list[int]:
    """CPUSubset0 default image: user program padded to 0x80, then setup, then halt."""
    if len(user_words) > USER_END // 4:
        raise ValueError(f"user program too long: {len(user_words)} words")
    mem = [BEEF] * (HALT_END // 4)
    for i, w in enumerate(user_words):
        mem[i] = w
    for addr, word, _ in SETUP:
        mem[addr // 4] = word
    for addr in range(HALT_START, HALT_END, 4):
        mem[addr // 4] = HALT_WORD
    return mem


def branch_offset_word(pc: int, target: int, link: bool) -> int:
    """F3 PC-relative branch: PC' = PC + 4 + off*4."""
    off = (target - pc - 4) // 4
    off &= 0xFFFFFF
    prefix = 0xF7000000 if link else 0xE7000000
    return prefix | off


def parse_final_system(path: str) -> tuple[dict[int, int], int]:
    """Return {byte_addr: word}, initial_entry_point from tests/final_system.code."""
    mem: dict[int, int] = {}
    entry = 0
    with open(path) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith("=== System Metadata ==="):
            rest = " ".join(s.strip() for s in lines[i + 1 :])
            import re
            m = re.search(r"initial_entry_point':\s*'0x([0-9A-Fa-f]{8})'", rest)
            if m:
                entry = int(m.group(1), 16)
            break
        if line.startswith("0x") and ":" in line:
            left, right = line.split(":", 1)
            addr = int(left.strip(), 16)
            word_s = right.strip().split()[0]
            mem[addr] = int(word_s, 16)
    return mem, entry


def blink3_imem(final_system_path: str) -> list[int]:
    """Custom memory image: trampoline at 0 jumps to LightToggle; unfixed modules overlaid."""
    overlay, entry = parse_final_system(final_system_path)
    if entry == 0:
        entry = BLINK3_ENTRY
    mem = [BEEF] * BLINK3_IMEM_WORDS
    for addr, word, _ in SETUP:
        mem[addr // 4] = word
    for addr in range(HALT_START, HALT_END, 4):
        mem[addr // 4] = HALT_WORD
    for addr, word in overlay.items():
        idx = addr // 4
        if idx >= len(mem):
            mem.extend([BEEF] * (idx + 1 - len(mem)))
        mem[idx] = word
    # B always (no link) from address 0 to the module entry. Using B not BL so
    # the only BL in the trace is LightToggle's broken call at 0x108C.
    mem[0] = branch_offset_word(0, entry, link=False)
    return mem


def write_words(path: str, words: list[int]) -> None:
    with open(path, "w") as f:
        for w in words:
            f.write(f"{w:08x}\n")
