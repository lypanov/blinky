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

# Blink3 linked image (Python loader matching Modules.Mod). LightToggle entry = 0x1048.
BLINK3_ENTRY = 0x1048
BLINK3_AMMT_BODY = 0x1028  # AMemoryMappedToggle BEGIN (entries[0] = 40)
BLINK3_INIT_CONT = 0x04    # trampoline continuation after AMMT BEGIN returns (BL at 0 plants this)
BLINK3_LIGHT_ADDR = 0x50
BLINK3_BL_PC = 0x108C
BLINK3_WRONG_LAND = 0x1050
BLINK3_TOGGLE = 0x1000
BLINK3_RETURN = 0x1090  # PC+4 of LightToggle's BL Toggle
BLINK3_MAXITER = 262144  # same hardware delay as Blink2hw; 0x40000
BLINK3_MAXITER_ADDR = 0x74
BLINK3_MAXITER_PC = 0x105C  # MHI R0, 4 (imm does not fit MOV)
BLINK3_MAXITER_STORE_PC = 0x1060
BLINK3_MHI_WORD = 0x60000004
BLINK3_IMEM_WORDS = 0x1100 // 4  # 0x0000 .. 0x10FC
# Power-of-two pad so CPUSubset0's PC>>2 index cannot run off the Vec on FPGA.
BLINK3_FPGA_IMEM_WORDS = 2048
BLINK3_CLOCK_HZ = 27_000_000
# Verilator (after BL/R15): skip-loop is 15 cycles; the Toggle iteration is 33.
# LED edge period = (N-1)*15 + 33 = 15N + 18. Full blink (on+off) is two edges.
BLINK3_SKIP_CYCLES = 15
BLINK3_EDGE_EXTRA = 18
MHI_R0 = 0x60000000


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


def mov_imm(rd: int, n: int) -> int:
    """F1 MOV Rd, n (unsigned 16-bit). Matches CPUSubset0 setup encodings."""
    return 0x40000000 | ((rd & 0xF) << 24) | (n & 0xFFFF)


def blink3_startup_trampoline() -> list[tuple[int, int, str]]:
    """Stand-in for Modules.Load calling each module body.

    BL plants R15 = PC+4 (same as Load's `body` statement). BEGIN returns
    with BT R15 into the next word, which BL's LightToggle.
    """
    return [
        (0x00, branch_offset_word(0x00, BLINK3_AMMT_BODY, link=True),
         "BL AMMT BEGIN at 0x1028 ; R15 := 0x04 (light := 0)"),
        (0x04, branch_offset_word(0x04, BLINK3_ENTRY, link=True),
         "BL LightToggle BEGIN at 0x1048 ; R15 := 0x08"),
        (0x08, HALT_WORD,
         "halt if LightToggle BEGIN returns"),
    ]


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
    """Custom image: startup trampoline calls AMMT BEGIN, then LightToggle."""
    overlay, _entry = parse_final_system(final_system_path)
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
    for addr, word, _note in blink3_startup_trampoline():
        mem[addr // 4] = word
    return mem


def mhi_r0(high16: int) -> int:
    """F1 MHI R0, imm — `R0 := imm << 16`. 262144 uses imm=4, 131072 uses imm=2."""
    if high16 < 0 or high16 > 0xFFFF:
        raise ValueError(f"MHI immediate out of range: {high16}")
    return MHI_R0 | (high16 & 0xFFFF)


def patch_blink3_maxiter(words: list[int], n: int) -> list[int]:
    """Replace LightToggle's MHI delay word. n must be a multiple of 65536."""
    if n <= 0 or n & 0xFFFF:
        raise ValueError(f"maxIterations {n} must be a positive multiple of 65536 (MHI high half)")
    out = list(words)
    idx = BLINK3_MAXITER_PC // 4
    if idx >= len(out):
        raise ValueError(f"IMEM too short for MHI at 0x{BLINK3_MAXITER_PC:X}")
    out[idx] = mhi_r0(n >> 16)
    return out


def patch_blink3_sim_n(words: list[int], n: int) -> list[int]:
    """Set LightToggle's maxIterations for a Verilator run.

    Multiples of 65536 stay an MHI, the same encoding the FPGA image uses.
    A smaller N replaces that one F1 instruction with MOV R0, n. Both retire
    in a single cycle and sit outside the skip loop, so an LED edge is still
    15N+18 cycles.
    """
    if n <= 0:
        raise ValueError(f"maxIterations must be positive, got {n}")
    if n % 65536 == 0:
        return patch_blink3_maxiter(words, n)
    if n > 0xFFFF:
        raise ValueError(
            f"maxIterations {n} must fit a 16-bit MOV or be a multiple of 65536 (MHI)"
        )
    out = list(words)
    idx = BLINK3_MAXITER_PC // 4
    if idx >= len(out):
        raise ValueError(f"IMEM too short for delay op at 0x{BLINK3_MAXITER_PC:X}")
    out[idx] = mov_imm(0, n)
    return out


def pad_imem(words: list[int], length: int = BLINK3_FPGA_IMEM_WORDS) -> list[int]:
    if length < len(words):
        raise ValueError(f"cannot pad {len(words)} words down to {length}")
    return list(words) + [BEEF] * (length - len(words))


def blink3_cycles_per_edge(n: int) -> int:
    return BLINK3_SKIP_CYCLES * n + BLINK3_EDGE_EXTRA


def blink3_predicted_hz(n: int, clock_hz: int = BLINK3_CLOCK_HZ) -> dict[str, float | int | str]:
    """Sim-RAM prediction. Hardware SPRAM wait-states may make this an upper bound."""
    cpe = blink3_cycles_per_edge(n)
    toggle = clock_hz / cpe
    blink = toggle / 2.0
    return {
        "max_iterations": n,
        "cycles_per_edge": cpe,
        "clock_hz": clock_hz,
        "toggle_rate_hz": toggle,
        "frequency_hz": blink,
        "period_s": 1.0 / blink,
        "note": (
            "sim says 15N+18 cycles/LED edge at 27 MHz; "
            "Gowin SPRAM wait-states may slow the hardware loop"
        ),
    }


def write_words(path: str, words: list[int]) -> None:
    with open(path, "w") as f:
        for w in words:
            f.write(f"{w:08x}\n")
