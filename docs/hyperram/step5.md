# Step 5: P-chain and D-chain fixups on the device

`tests/BlinkChain.Mod` is a new file. `tests/BlinkFetch.Mod`,
`tests/BlinkRsc.Mod`, and `tests/BlinkBoot.Mod` were not edited.
`tests/Blink3test.Mod` and `tests/AMemoryMappedToggle.Mod` were not
edited. Nothing under `oberon/src` was edited. The host has no Oberon
compiler in this build, so `sim/build_pdchain_imem.py` emits the ORG
encodings the module describes. The formulas are `Modules.Mod`, the BL
fixup and the load/store fixup:

```
offset := (dest - adr - 4) DIV 4;
SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H)

(* mno = 0 *)
SYSTEM.PUT(adr, (inst DIV 1000000H * 10H + MT) * 100000H + modnum*4)

(* mno # 0 *)
SYSTEM.PUT(adr, (inst DIV 1000000H * 10H + MT) * 100000H + v*4);
IF ODD(inst DIV 100H) THEN offset := offset + code - data END;
SYSTEM.PUT(adr + 4, inst DIV 10000H * 10000H + offset)
```

`FPGA_IMAGE=blink3` stays block RAM. `FPGA_IMAGE=hyperram`, `fixup`,
`rsc`, and `fetchbl` stay their own images. Rebuilding the step-3 words
with the success-target default of 0 is byte-identical to
`sim/visualizer/imem/rsc-n5.words`. `FPGA_IMAGE=pdchain` is the only
image that will be loaded for this step. It is nano4k HyperRAM, the
same top and PLL as the previous HyperRAM images. `FIRST_VALID` stays
13. The HyperRAM model was not edited.

The chain is the memory prologue, the ALU at `0x1400`, the reader at
`0x1800`, then the chain prologue at `0x1C00`, then address 0. The
walker ends at `0x1EF8`. None of the new instructions sit in the delay
loop.

## What the ROM holds

The ROM is the unfixed fixture words, not `tests/final_system.code`.
The host-fixed image would blink even if the device walk were a no-op.
The sites the host had already rewritten are put back:

| address | ROM placeholder | word the walk must store |
|---|---|---|
| `0x100C` | `0x8D000003` | `0x8DC00004` |
| `0x1034` | `0x8D00000A` | `0x8DC00004` |
| `0x1054` | `0x8D000003` | `0x8DC00008` |
| `0x1068` | `0x8D000005` | `0x8DC00008` |
| `0x1094` | `0x8D00000B` | `0x8DC00008` |
| `0x108C` | `0xF7102011` | `0xF7FFFFDC` |

`0xF7FFFFDC` is the same BL the host linker writes. From `0x108C` it
lands on Toggle at `0x1000`. `0x8DC00004` is `LDW R13, [R12, 4]`,
MT[1], the AMMT data base `0x50` where `light` lives. `0x8DC00008` is
`LDW R13, [R12, 8]`, MT[2]. Setup plants that slot as `0x70`,
LightToggle's own variables. The LED store is inside Toggle, so it
uses the `0x8DC00004` GetSB.

The placeholder BL `0xF7102011` is not in the delay-loop fetch until
the walk has stored the fixed word. A fetch of the placeholder from
`0x108C` targets `0x4090D4`, not Toggle. A fetch of a placeholder GetSB
uses R0 or R1, not R12, so the light store misses `0x50`.

## The two import arms

LightToggle's own chain is only the global arm (`mno = 0`). The
original step still requires the import arm. Two pairs are planted in
the padding after LightToggle and linked onto that chain, so the
existing sites stay the tail. They are not fetched by the delay loop.

| address | placeholder | fixed word | what it is |
|---|---|---|---|
| `0x10AC` | `0x8D100006` | `0x8DC00004` | imported GetSB, module 1 |
| `0x10B0` | `0x80D00001` | `0x80D00000` | `LDW R0, [R13, 0]`, export 1 |
| `0x10C0` | `0x8D100005` | `0x8DC00004` | imported GetSB, the ODD pair |
| `0x10C4` | `0x40D80102` | `0x40D80FB0` | `ADD R0, R13, 0xFB0` |

The variable's displacement 0 and the placeholder's displacement 1 are
the same HyperRAM beat, so the loaded data cannot prove the fix. Slot
34 compares the stored instruction. The ODD arm adds `code - data`
(`0x1000 - 0x50 = 0xFB0`). Executed after the fixed GetSB, `R0` is
`0x1000`. Leaving the offset at 0 makes `R0` the data base `0x50`.

`fixorgD` for LightToggle is 30, so the chain is
`0x10C0 → 0x10AC → 0x1094 → 0x1068 → 0x1054 → code`.
`fixorgP` is 17, the one BL. AMMT has `fixorgP = 0` and `fixorgD = 13`.
The prologue plants the anchors the walk reads: the import pointer at
`0x300`, the AMMT descriptor at `0x310` (num 1, code `0x1000`, data
`0x50`, entries at `0x330`), and the entry table `40, 0, 0`. It calls
the walker twice, with the link in R11 (`BT R11`, not BL, so R15 stays
the reset value until Blink3). A zero displacement ends that chain, the
same stop the host parser uses. The real chains have no zero
displacement.

## How a fixed word is fetched

pROM cannot be written. A HyperRAM round trip on every fetch of these
sites would sit inside the delay loop. The walker only stores ten
word-aligned addresses in page `0x10`:

`0x0C`, `0x34`, `0x54`, `0x68`, `0x8C`, `0x94`, `0xAC`, `0xB0`, `0xC0`, `0xC4`.

A store whose address is in that page and whose low byte is one of
those offsets marks that slot and keeps the data. The ROM output
register loads the stored word when `overlayEn` is set, on the same
clock as a normal ROM read. There is no mux after the ROM output.
The address compared for that overlay is the registered PC plus 4, or
the registered PC while a memory access is already pending, because
that PC is the instruction being refetched. The compare starts at the
PC register and the N and V flags. The fall-through overlay is
suppressed for the taken branch at `0x1088` (N xor V) and for the
unconditional branch at `0x10A8`. The prologue branches at `0x1D34`
and `0x1D68` force the overlay of `0x10AC` and `0x10C0` once those
slots are valid. Those two branches are the executed import pairs.

A general 12-entry table of 32-bit address compares was 5367 logic
cells (4720 LUT, 647 ALU) on the GW1NSR-4C. The limit is 4608. That
netlist was not used for the slope below and is not loaded.

A marked load does not ask HyperRAM and does not change the ROM
address. The issue cycle records which of the ten slots hit. The
completion cycle selects that stored word. An unmarked load of page
`0x10` holds the PC, points the ROM at the placeholder, writes that
ROM word, refetches PC+4, and only then executes the next instruction.
HyperRAM powers up empty, so a load from there would see 0 and the
walk would fix a zero. `chainFix` is true only for this image. With
it false, Blink3 and the step-4 image stay on their previous paths.

`extraChecks` is 37. The pin gate is 45 bits: the 8 memory slots plus
these 37. Slots 32..36 are the new ones.

- Slot 32 (`0x880`) is the BL at `0x108C` against `0xF7FFFFDC`.
- Slot 33 (`0x884`) is the OR of the two AMMT GetSB differences, both
  against `0x8DC00004`.
- Slot 34 (`0x888`) is the imported load at `0x10B0` against
  `0x80D00000`.
- Slot 35 (`0x88C`) is the OR of (`R13 - 0x50`) and (`R0 - sentinel`)
  after executing the variable pair. Setup leaves R13 at `0x70`. R1 is
  cleared before the branch, so the placeholder base is not MT.
- Slot 36 (`0x890`) is `R0 - 0x1000` after executing the ODD pair.

A non-zero `R10` branches to the hold at `0x1D8C`. Address 0 is reached
only after that compare. The sentinel written to `0x50` before the
variable pair has bit 0 clear. AMMT's body, using the fixed GetSB,
writes 0 there before the delay loop.

## Why a wrong result cannot blink at this rate

The step-1 through step-4 arguments still hold. The reader enters this
prologue only when its own `R10` is zero.

- The ROM word at `0x108C` is `0xF7102011`. None of `0xF7FFFFDC`,
  `0x8DC00004`, `0x8DC00008`, or `0x40D80FB0` is present in the ROM.
  A walk that does not run leaves the placeholders. The BL misses
  Toggle and the GetSB misses `0x50`, so the pin stays dark.
- Slot 32 fails if the stored BL is not `0xF7FFFFDC`. The CPU holds
  at `0x1D8C` and never enters address 0.
- Both AMMT GetSBs have to become `0x8DC00004`, or slot 33 stays clear
  and the hold is taken. Toggle's store of `light` is the `0x100C`
  site.
- Slot 34 fails if the imported load is left at displacement 1. The
  data value aliases, so the instruction word is the check.
- Slot 35 fails unless the fetched GetSB actually loaded MT[1] into
  R13 and the following load returned the sentinel.
- Slot 36 fails unless the ODD add produced Toggle's address.
- `CHAIN_FIX=0` is the same words with no table and no ROM read of the
  code window. The walk loads HyperRAM, the compare fails, and the
  CPU sits on `0x1D8C`.
- A missing zero among the 45 slots leaves the mask bit clear, so the
  pin stays dark even if the loop runs.
- The same software hole as step 2 remains: a SUB that returns 0 for
  unequal operands stores zeros and skips the hold. It also makes the
  delay compare return 0, so the loop toggles every iteration, at about
  55 kHz, not at half a hertz. The measured rate closes that hole.

`--break-slot 32` adds 1 to the expected BL. 20000 cycles produced 0
LED edges. The CPU sat on the hold at `0x1D8C` / `0x1D90`.
`CHAIN_FIX=0` also produced 0 edges in 25000 cycles and sat on that
same hold. Neither image is loaded.

## Simulation, fitted model

`FIRST_VALID` stays 13. Recorded before synthesis.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| pdchain | 5 | 657 | 7609 |
| pdchain | 6 | 760 | 7712 |
| pdchain | 8 | 966 | 7918 |
| blink3, this CPU | 5 | 93 | 111 |
| fetchbl, this CPU | 5 | 657 | 6623 |

N=5 edges were 7609, 8266, 8923, 9580, 10237, 10894, 11551, 12208.
N=6 edges were 7712, 8472, 9232, 9992, 10752, 11512. N=8 edges were
7918, 8884, 9850, 10816, 11782, 12748.

Those edges were measured again on the RTL that was synthesized: the
constant-offset table, the registered-PC overlay, and the completion
cycle selecting the stored word from the hit bits recorded at issue.
N=5 began 7609, 8266, 8923. N=6 began 7712, 8472. N=8 began 7918,
8884. The periods stayed 657, 760, and 966. That is still
`103*N + 142`. The walk and the two executed pairs sit before the
delay loop. They move the first edge (step 4's N=5 first edge was
6623; this one is 7609) and they do not change the period. The
overlay does not add a stall inside the loop. Blink3 on this CPU is
still 111, 204, 297, 390, 483, 576. The step-4 image on this CPU is
still 6623, 7280, 7937, then period 657.

On the N=5 success path the ten sites were stored once each, as the
words in the tables above. Slots 32..36 were each stored as zero. The
CPU executed `0x10AC`, `0x10B0`, `0x10B4`, `0x10C0`, `0x10C4`, and
`0x10C8`, then address 0. The hold at `0x1D8C` was not visited. No
`HYPER_TIMING_FAULT`.

N=262144 at the 27 MHz CPU clock, locked from that slope before this
bitstream is built:

- cycles per edge = `103*262144 + 142` = **27,000,974**
- one edge = 1.000036 s
- full blink = **0.499982 Hz**, period **2.000072 s**

Not the block-RAM 3.433 Hz, and not the pre-load 0.520 Hz. A dark hold
is the failure state. The tool's `predicted_blink3_hz` compares against
3.433 Hz and is not this prediction.

The visualizer on 127.0.0.1:8765 has no page for this image. The Primer
20K is not part of this step.

## Hardware

PNR of `pdchain_n262144` on the GW1NSR-4C: 4058/4608 logic (89%; 3775
LUT and 283 ALU), 2190/2304 CLS (96%), 1636/3612 registers, 6/10 BSRAM
of which 4 are the instruction pROM (plus one SDPB and one SDPX9B).
The `if (overlayEn)` load of the ROM output register still inferred
pROM. Setup and hold total negative slack are 0 on every clock. The
worst setup slack is +0.082 ns, on the 27 MHz `clkdiv` clock (period
37.037 ns), from the instruction ROM `DO` to the Z flag. That clock's
achieved frequency is 27.060 MHz. The same report lists 0 setup
endpoints and 0 hold endpoints violated on `clkdiv`. The PLL was not
edited: IDIV 0, FBDIV 1, ODIV 16, VCO 864 MHz, CLKOUT 54 MHz, CPU
27 MHz. Gowin still warns that `clkdiv` was determined to be a clock
but was not created (TA1132) and that `clock_d` uses a generic routing
resource (PR1014). Both warnings are on the earlier HyperRAM images.

SRAM load, Tang Nano 4K only. `lsusb` showed the two FT2232s at bus
003 device 078 and bus 003 device 081. `--detect` on 003:081 returned
idcode `0x100981b`, GW1NSR-4C. `--detect` on 003:078 returned idcode
`0x81b`, GW2A-18. Device 078 was not loaded. An unscoped `--detect`
hits 078 first, so the load named the bus address.

```
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/pdchain_n262144.fs
```

The file is the 02:39:19 bitstream, the run whose slack is above.
`write to ram`, SRAM load 100%, CRC check success. No `-f`.

`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=nano4k`, duration
20, warmup 2. The server cwd is `blinky-blinkband/tools/webcam-mcp`
(pid 358063), whose detector band starts at 0.2 Hz. Exposure was left
to that tool's existing lock and restore. Run directory
`~/fpga/blink-measure/20261105-024044-mcp/`. Capture was `/dev/video2`,
640x480, 661 frames, delivered 30.045 fps. The tool's own JSON is
`step5-result.json`. Headline fields:

```json
{
  "frequency_hz": 0.499,
  "edge_frequency_hz": 0.499,
  "fft_frequency_hz": 0.5,
  "trusted_method": "edge",
  "trusted_reason": "blinking LED edge period is regular",
  "status": "blinking",
  "confidence": 1.0,
  "source": "blinking-led",
  "board": "nano4k",
  "n_leds": 2,
  "n_blinking": 1,
  "n_steady": 1,
  "colors": ["red"],
  "target_led_id": 0,
  "measure_roi": {"x": 220, "y": 253, "w": 46, "h": 38}
}
```

SNR on that LED was 394.47 and its chroma coefficient of variation was
0.97. The locked prediction was 0.499982 Hz; the tool reports 0.499.
Its `predicted_blink3_hz` is 3.4332275390625 (`error_pct_vs_blink3`
-85.47) and is not this prediction. The Primer 20K, in the same frame,
was `board present but not blinking` (frequency null; two steady red
LEDs). `assign_reason` was
`upper=primer20k n=2 orange=0 lower=nano4k n=2 orange=0 cy=130/272`.
The fuller payload is `step5-mcp.json`. Frames are `step5-nano4k.png`
and `step5-leds.jpg`.
