# Step 7: Files serves two .rsc images, then Load of Blink5

`tests/BlinkFiles.Mod` and `tests/Blink5.Mod` are new files.
`tests/BlinkMod.Mod` and the earlier modules were not edited. Nothing
under `oberon/src` was edited. The host has no Oberon compiler in
this build, and there is no compiled `.rsc` on disk, so
`sim/build_files_imem.py` builds both byte images and emits the ORG
encodings. The formulas are `Files.Mod` and `Modules.Load`:

```
ReadByte     LDB, then advance the rider
ReadInt      x := ((x3 * 100H + x2) * 100H + x1) * 100H + x0
ReadString   ReadByte until 0X
body := code + w
```

`100H` is `LSL 8`. The subroutine does that shift three times, once
per byte, which is the same sum as one `LSL 24`. `FPGA_IMAGE=files`
is the only image loaded for this step. `chainFix` stays on, because
the delay loop still fetches the ten fixed words from step 5.
`FIRST_VALID` stays 13. The PLL was not edited.

HyperRAM powers up empty. The model clears its array, and the device
has no preload of this table, so the CPU stores every word of the
table before it reads one back. `Files.Old` here is a two-entry
directory, not the disk `Old` in `oberon/src/Files.Mod`. Each entry is
a name word, a base, and a length. `Old` returns the base whose name
word matches, or branches to the hold when neither matches. A NIL
file never starts the rider.

The new instructions are one block in the free words at `0x00C0`.
The block is 378 words and the last word is at `0x06A4`. None of them
sit in the delay loop. The step-6 pad at `0x1FE0` used to branch to
`0x1048`. It now enters this block. The pad's store of the link slot
is a `MOV R5, R0` instead, so R5 keeps that difference and the slot
stays clear until this block stores it. The two words at address 0
still branch to the hold.

## What the byte table holds

The directory is at `0x600`. `AMemoryMappedToggle.rsc` is 72 bytes at
`0x620`. `Blink5.rsc` is 83 bytes at `0x670`. Both end before the
check slots at `0x7C0`, and both sit above the prologue series at
`0x400` and `0x500`. Those numbers are data addresses. The same
numbers in the instruction ROM are the tail of this block. The CPU
fetches the pROM and reads HyperRAM, so the two do not alias.

`Load` walks the sections in `Modules.Mod` order: name, key, version,
size, imports, type-descriptor count, variable count, string count,
code-word count, commands, entries, the pointer terminator, `fixorgP`,
`fixorgD`, `fixorgT`, the entry integer `w`, and the trailing `O`.

| field | AMemoryMappedToggle | Blink5 |
|---|---|---|
| name | `AMemoryMappedToggle` | `Blink5` |
| key | `0xA11CE001` | `0xB1150005` |
| version | `1X` | `1X` |
| imports | none | `AMemoryMappedToggle`, key `0xA11CE001` |
| code words | 0 | 0 |
| fixorgT | 0 | 0 |
| w | 0 | `0x48` |
| marker | `O` | `O` |

The code count is 0, so the file has no instruction words. `fixorgT`
is 0, so the type chain is empty. That is a property of these two
images, not a chase to invent. The CPU cannot execute a copy of the
code section out of HyperRAM: fetches come from the instruction pROM.
The body that runs is the host-placed delay loop. The loader's code
base is the immediate `0x1000`, and `w` is the integer `ReadInt`
returns, so `0x1000 + 0x48 = 0x1048`. The success word is `BT R1`
(`0xC7000001`). There is no `MOV` of `0x1048` and no PC-relative
branch to `0x1048` in this block.

`Load("Blink5")` reads the imported file first. The import key is
subtracted from the key `ReadInt` returned for `AMemoryMappedToggle`,
and each of those keys is also subtracted from its immediate. A pair
of zero keys does not match `0xA11CE001`. The block then stores the
resident data addresses again:

```
STW 0x50, [R12, 4]
STW 0x70, [R12, 8]
```

`R12` is restated as `0x10`. Those two addresses are not in the
files. They are the module-table entries the already-fixed loop and
the LED snoop use. The block clears both of them before it reads the
table, so a skipped reinstall leaves `GetSB` at 0.

## Why a wrong result stays dark

The step-1 through step-6 arguments still hold. The file result
reuses the step-6 link slot, so the tail does not grow. A store of a
non-zero difference leaves that bit clear, and `io.led` stays 0 even
if the loop runs. The store does not go through the step-5 mask
shifter. Widening that shifter missed timing in step 6, and adding a
tail bit past these three also missed. `CheckTail` registers the
address on the store cycle and compares it on the next cycle. The pin
needs the three tail bits at `0x894`, `0x898`, and `0x89C`, plus the
step-5 mask. The pad still stores `0x894` and `0x898`. This block is
the only store of `0x89C`.

The word stored at `0x89C` is the OR of the pad's link difference,
kept in R5, and four file compares:

- every name byte's difference from its immediate, for both files and
  for Blink5's import
- the version bytes against `1X`, both keys against their immediates,
  the import key against the key read from the imported file, and both
  trailing bytes against `O`
- `w - 0x48`
- (MT[1] − `0x50`) and (MT[2] − `0x70`) after the reinstall, loaded
  back from the table

Two earlier netlists were placed and not loaded. Giving each of the
four file compares its own tail bit (`extraChecks` 44) missed setup.
Logic was 4093/4608 (3810 LUT, 283 ALU), CLS 2224/2304, registers
1660/3612. Setup total negative slack on `clkdiv` was −531.382 ns
across 312 endpoints. The worst slack was −3.917 ns, from the
instruction ROM `DO[4]` to the next ROM address. Achieved frequency
was 24.418 MHz. Hold slack was 0. Folding those four compares into
one new bit at `0x8A0` (`extraChecks` 41) still missed setup: logic
4075/4608 (3793 LUT, 282 ALU), CLS 2233/2304, registers 1657/3612,
setup total negative slack −0.698 ns across 5 endpoints, worst slack
−0.280 ns from ROM `DO[1]` to `Z`, achieved frequency 26.797 MHz,
hold slack 0. That bitstream was written at 03:33:38 and was not
loaded. The image below keeps the compares and stores them in the
existing link slot.

A zero directory matches neither name, so `Old` branches to the hold
at `0x1D8C` and `0x89C` is never stored. A directory whose files were
not deposited still returns a base; the rider then reads zeros. The
name and version compares are non-zero, and `w - 0x48` is `−0x48`, so
the body `0x1000 + 0` is not taken. Address 0 is the hold, and this
image does not use a body of 0 as its only gate.

On the N=5 success path slot `0x89C` was stored as zero, from PC
`0x654`. At the `BT`, R1 was `0x1048`, R5 was 0, R6 was `0x48`, R10
was 0, and R12 was `0x10`. The next cycle was `0x1048`. The CPU had
executed the step-6 `BLR` at `0x1FC0`, the pad at `0x1FC8`, and the
files block at `0x00C0`. Address 0 and the hold were not visited. The
block had cleared MT[1] and MT[2] and then written `0x50` and `0x70`
back.

`--break-slot 39` bumps the link the pad subtracts. The pad branches
to the hold, `0x89C` is never stored, and `0x1048` does not run.
0 LED edges in 20000 cycles. Top PCs were `0x1D8C` (6317) and
`0x1D90` (6316). Replacing that pad branch with `MOV R1, R1`, so the
bumped difference falls into this block, stores `−1` at `0x89C` from
PC `0x654` and still holds (`0x1D8C` 3888, `0x1D90` 3887, 0 edges, no
`0x1048`). The link difference is in the stored word.

`--break-slot 40` bumps the Blink5 name word. `--break-slot 41` bumps
the version byte. `--break-slot 42` bumps `w`. `--break-slot 43`
bumps the reloaded MT[1]. Each stores `−1` at `0x89C`. Each produced
0 LED edges in 20000 cycles, sat on the hold (top PCs `0x1D8C` 3888
and `0x1D90` 3887), and did not execute `0x1048`.

`--skip-slot 40` stores that zero at `0x8C0` instead of `0x89C`, then
does take `0x1048`. In 20000 cycles the loop wrote `0x50` eleven
times and `io.led` stayed 0. The missing tail bit is what kept the
pin dark.

`--mode none` is the power-up table. 0 edges in 20000 cycles, no
store to `0x89C`, hold at `0x1D8C` and `0x1D90` (6270 each).
`--mode dir` deposits the directory and not the files. 0 edges, the
proof word at `0x89C` is `−1`, and the hold is `0x1D8C` and `0x1D90`
(4267 each). `CHAIN_FIX=0` produced 0 edges in 25000 cycles and sat
on that hold (top PCs `0x1D8C` 9246 and `0x1D90` 9245). It did not
reach `0x00C0`. None of those images is loaded.

A `SUB` that returns 0 for unequal operands still collapses the delay
compare, so the loop toggles at about 55 kHz. The measured rate closes
that hole. With the table left at 0, Toggle's store of `light` misses
`0x50` and the pin stays dark even if the compare is ignored.

## Simulation, fitted model

`FIRST_VALID` stays 13. Recorded before synthesis.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| files | 5 | 657 | 12880 |
| files | 6 | 760 | 12983 |
| files | 8 | 966 | 13189 |

N=5 edges were 12880, 13537, 14194. N=6 edges were 12983, 13743,
14503. N=8 edges were 13189, 14155, 15121. The periods are still
`103*N + 142`. The first edges are 4841 cycles later than step 6 and
move by 103 when N moves by 1. The added block is before the delay
loop.

`light` still holds the chain's sentinel `0x3C3C3C3C`, because this
call enters the delay loop and not AMMT's `BEGIN`. Toggle computes
`1 - light`, so bit 0 of the store at `0x50` still alternates
(`0xC3C3C3C5`, then `0x3C3C3C3C`). That is the pin the measurement
watches. The store PC is `0x1018`.

N=262144 at the 27 MHz CPU clock, locked from that slope before this
bitstream is built:

- cycles per edge = `103*262144 + 142` = **27,000,974**
- one edge = 1.000036 s
- full blink = **0.499982 Hz**, period **2.000072 s**

The tool's `predicted_blink3_hz` compares against 3.433 Hz and is not
this prediction. The visualizer on 127.0.0.1:8765 has no page for this
image. The Primer 20K is not part of this step.

## Hardware

PNR of `files_n262144` on the GW1NSR-4C: 4045/4608 logic (88%; 3762
LUT and 283 ALU), 2235/2304 CLS (97%), 1656/3612 registers, 6/10 BSRAM
of which 4 are the instruction pROM (plus one SDPB and one SDPX9B).
Setup and hold total negative slack are 0 on every clock, and 0
endpoints are violated. The worst setup slack is +0.040 ns, on the
27 MHz `clkdiv` clock (period 37.037 ns), from the instruction ROM
`DO[4]` to the Z flag. That clock's achieved frequency is 27.029 MHz.
The PLL was not edited: IDIV 0, FBDIV 1, ODIV 16, VCO 864 MHz, CLKOUT
54 MHz, CPU 27 MHz. Gowin still warns that `clkdiv` was determined to
be a clock but was not created (TA1132) and that `clock_d` uses a
generic routing resource (PR1014). The two earlier files netlists,
with 44 and 41 checks, missed setup and were not loaded. This report
is the 40-check image.

SRAM load, Tang Nano 4K only. `lsusb` showed the two FT2232s at bus
003 device 078 and bus 003 device 081. `--detect` on 003:081 returned
idcode `0x100981b`, GW1NSR-4C. `--detect` on 003:078 returned idcode
`0x81b`, GW2A-18. Device 078 was not loaded. An unscoped `--detect`
hits 078 first, so the load named the bus address.

```
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/files_n262144.fs
```

The file is the 03:40:11 bitstream, the run whose slack is above.
`write to ram`, SRAM load 100%, CRC check success. No `-f`.

`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=nano4k`, duration
20, warmup 2. The server cwd is `blinky-blinkband/tools/webcam-mcp`
(pid 358063), whose detector band starts at 0.2 Hz. Exposure was left
to that tool's existing lock and restore. Run directory
`~/fpga/blink-measure/20261105-034055-mcp/`. Capture was `/dev/video2`,
640x480, 661 frames, delivered 30.045 fps. The tool's own JSON is
`step7-result.json`. Headline fields:

```json
{
  "frequency_hz": 0.5,
  "edge_frequency_hz": 0.5,
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
  "measure_roi": {"x": 220, "y": 252, "w": 44, "h": 38}
}
```

SNR on that LED was 238.45 and its chroma coefficient of variation was
0.972. The locked prediction was 0.499982 Hz. The tool reports 0.5,
which is that rate at the thousandths it prints. Its
`predicted_blink3_hz` is 3.4332275390625 (`error_pct_vs_blink3`
-85.44) and is not this prediction. The Primer 20K, in the same frame,
was `board present but not blinking` (frequency null; two steady red
LEDs). `assign_reason` was
`upper=primer20k n=2 orange=0 lower=nano4k n=2 orange=0 cy=139/272`.
The fuller payload is `step7-mcp.json`. Frames are `step7-nano4k.png`
and `step7-leds.jpg`.
