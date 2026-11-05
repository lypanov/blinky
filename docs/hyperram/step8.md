# Step 8: Modules.Init is the reset path, then Load of Blink5

`tests/BlinkModules.Mod` is a new file. `docs/OberonSources/Modules.Mod`
was not edited, and neither were `tests/BlinkFiles.Mod` or the earlier
modules. Nothing under `oberon/src` was edited. The host has no Oberon
compiler, so `sim/build_modules_imem.py` emits the ORG encodings. The
formula is `Modules.Init`, with the reserve immediate changed:

```
SYSTEM.GET(16, AllocPtr)
SYSTEM.GET(20, root)
SYSTEM.GET(24, limit)
DEC(limit, 1000H)
```

`1000H` is 4 KB. The published source subtracts `8000H`. That
immediate is not in this image. `FPGA_IMAGE=modules` is the only image
loaded for this step. `chainFix` stays on. `FIRST_VALID` stays 13.
The tail stays 40 checks, the same width as step 7. Init's difference
is XOR-ed into the store that already arms the link slot. The PLL was
not edited.

Reset still begins at `0x80`. Setup plants the module table, then the
MOV at `0x9C` loads this body instead of the memory prologue at
`0x1200`. The body is 46 words at `0x06C0` and the last word is at
`0x0774`. On a matching reserve it executes `MOV R0, 0x1200` and
`BT R0`. The prologue's success path is still Load of Blink5, and
that Load still enters the delay loop through `BT R1`.

## What Init reads

HyperRAM powers up empty. Setup has already stored `0x50` at address
20 and `0x70` at address 24, because those addresses are also MT[1]
and MT[2]. The body stores the three BootLoad words, reads them back,
and writes `0x50` and `0x70` back before the prologue's compare.

| address | value read back | role |
|---|---:|---|
| 16 | `0x0C00` | AllocPtr, above the resident tables |
| 20 | `0x0020` | root, a non-zero token |
| 24 | `0x2000` | stack origin |

`DEC(limit, 1000H)` leaves `0x1000`. R14 is the word read from address
24, so the stack top is `0x2000` and the reserve is `0x1000` through
`0x2000`. The behavioural model is 8 KB, and this reserve is the top
half of it. The delay loop's existing `STW` of the link lands at
`0x1FFC`, from PC `0x104C`. The saved link on the N=5 run was
`0x1FC4`.

The proof word is the OR of the three differences, XOR `0xDEC0`,
stored at `0x05F0`. A difference of zero stores `0xDEC0`. Power-up
memory is zero, so a skipped store does not look like that nonce.
Load's stub at `0x0760` loads `0x05F0`, XOR-s the nonce, and OR-s the
result into the link-slot word. The tail does not grow.

## Why a wrong reserve stays dark

The step-1 through step-7 arguments still hold. The pin still needs
the three tail bits at `0x894`, `0x898`, and `0x89C`. This body is the
only writer of `0x05F0`, and the files block is still the only writer
of `0x89C`. A non-zero word at `0x89C` leaves that bit clear.

`--break-dec` subtracts `1001H`. The proof word at `0x05F0` is
`0xFFFF213F`, the body branches to the hold, and `0x1200` is not
fetched. 0 LED edges. Replacing that branch with `MOV R1, R1` does
enter the prologue. The stub then stores `−1` at `0x89C`, from PC
`0x0770`. 0 edges in 20000 cycles, hold at `0x1D8C` (3768) and
`0x1D90` (3767), and `0x1048` does not run.

`--skip-proof` stores the good nonce at `0x05E0` and leaves `0x05F0`
at its power-up zero. The register compare passes, the prologue runs,
and the stub's XOR of zero is `0xDEC0`. 0 edges, same hold, no
`0x1048`.

`--break-slot 40` still bumps the Blink5 name. Init's nonce is the
good one, and the name difference keeps the link slot non-zero.
0 edges, same hold, no `0x1048`. `--skip-slot 40` stores the zero at
`0x8C0` instead. The loop does run. In 20000 cycles it wrote `0x50`
eleven times and `io.led` stayed 0.

`--mode none` and `--mode dir` are the step-7 failures, reached after
a good Init. 0 edges. The holds are `0x1D8C`/`0x1D90` at 6162 each,
and 4147 each. `CHAIN_FIX=0` produced 0 edges in 25000 cycles and sat
on that hold (`0x1D8C` 9138, `0x1D90` 9137). It did enter this body.
It did not reach the delay loop. None of those images is loaded.

A `SUB` that returns 0 for unequal operands still collapses the delay
compare, so the loop toggles at about 55 kHz. The measured rate closes
that hole.

## Simulation, fitted model

`FIRST_VALID` stays 13. Recorded before synthesis.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| modules | 5 | 657 | 13120 |
| modules | 6 | 760 | 13223 |
| modules | 8 | 966 | 13429 |

N=5 edges were 13120, 13777, 14434. N=6 edges were 13223, 13983,
14743. N=8 edges were 13429, 14395, 15361. The periods are still
`103*N + 142`. The first edges are 5081 cycles later than step 6 and
move by 103 when N moves by 1. Init is before the delay loop.

On the N=5 success path the proof word at `0x05F0` was `0xDEC0`, from
PC `0x0728`. MT[1] and MT[2] were `0x50` and `0x70` again before the
prologue. At the `BT` of Load, R1 was `0x1048`, R6 was `0x48`, R10
was 0, R12 was `0x10`, and R14 was `0x2000`. The next cycle was
`0x1048`. Address 0 and the hold were not visited.

`light` still alternates through the store at `0x1018`
(`0xC3C3C3C5`, then `0x3C3C3C3C`).

N=262144 at the 27 MHz CPU clock, locked from that slope before this
bitstream is built:

- cycles per edge = `103*262144 + 142` = **27,000,974**
- one edge = 1.000036 s
- full blink = **0.499982 Hz**, period **2.000072 s**

The tool's `predicted_blink3_hz` compares against 3.433 Hz and is not
this prediction. The visualizer on 127.0.0.1:8765 has no page for this
image. The Primer 20K is not part of this step.

## Hardware

PNR of `modules_n262144` on the GW1NSR-4C: 4045/4608 logic (88%; 3762
LUT and 283 ALU), 2235/2304 CLS (97%), 1656/3612 registers, 6/10 BSRAM
of which 4 are the instruction pROM (plus one SDPB and one SDPX9B).
Setup and hold total negative slack are 0 on every clock, and 0
endpoints are violated. The worst setup slack is +0.040 ns, on the
27 MHz `clkdiv` clock (period 37.037 ns), from the instruction ROM
`DO[4]` to the Z flag. That clock's achieved frequency is 27.029 MHz.
The PLL was not edited: IDIV 0, FBDIV 1, ODIV 16, VCO 864 MHz, CLKOUT
54 MHz, CPU 27 MHz. Gowin still warns that `clkdiv` was determined to
be a clock but was not created (TA1132) and that `clock_d` uses a
generic routing resource (PR1014). The check width is the step-7
40-check image. No route option and no max-fan override were set.

SRAM load, Tang Nano 4K only. `lsusb` showed the two FT2232s at bus
003 device 078 and bus 003 device 081. `--detect` on 003:081 returned
idcode `0x100981b`, GW1NSR-4C. `--detect` on 003:078 returned idcode
`0x81b`, GW2A-18. Device 078 was not loaded. An unscoped `--detect`
hits 078 first, so the load named the bus address.

```
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/modules_n262144.fs
```

The file is the 03:52:46 bitstream, the run whose slack is above.
`write to ram`, SRAM load 100%, CRC check success. No `-f`.

`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=nano4k`, duration
20, warmup 2. The server cwd is `blinky-blinkband/tools/webcam-mcp`
(pid 358063), whose detector band starts at 0.2 Hz. Exposure was left
to that tool's existing lock and restore. Run directory
`~/fpga/blink-measure/20261105-035318-mcp/`. Capture was `/dev/video2`,
640x480, 661 frames, delivered 30.045 fps. The tool's own JSON is
`step8-result.json`. Headline fields:

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
  "measure_roi": {"x": 220, "y": 252, "w": 46, "h": 38}
}
```

SNR on that LED was 283.42 and its chroma coefficient of variation was
0.974. The locked prediction was 0.499982 Hz. The tool reports 0.5,
which is that rate at the thousandths it prints. Its
`predicted_blink3_hz` is 3.4332275390625 (`error_pct_vs_blink3`
-85.44) and is not this prediction. The Primer 20K, in the same frame,
was `board present but not blinking` (frequency null; three steady red
LEDs). `assign_reason` was
`upper=primer20k n=3 orange=0 lower=nano4k n=2 orange=0 cy=141/272`.
The fuller payload is `step8-mcp.json`. Frames are `step8-nano4k.png`
and `step8-leds.jpg`.
