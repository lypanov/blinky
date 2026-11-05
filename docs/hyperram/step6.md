# Step 6: ModDesc, the module table, and a procedure-variable call

`tests/BlinkMod.Mod` is a new file. `tests/BlinkChain.Mod` and the
earlier modules were not edited. Nothing under `oberon/src` was
edited. The host has no Oberon compiler in this build, so
`sim/build_moddesc_imem.py` emits the ORG encodings the module
describes. The formulas are `Modules.Mod`:

```
SYSTEM.PUT(num * 4 + MTOrg, data)
body := code + w
body
```

`DescSize` is 80. The fields this image writes are `name` at offset 0,
`next` at 32, `num` at 40, `data` at 52, and `code` at 56. `MTOrg` is
R12, which setup leaves at `0x10`. `w` is the entry integer Load reads
before the call. The call is `BLR`, which plants R15 with the return
address. `FPGA_IMAGE=moddesc` is the only image loaded for this step.
`chainFix` stays on, because the delay loop still fetches the ten
fixed words from step 5. `FIRST_VALID` stays 13. The PLL was not edited.

The new instructions are one block after the step-5 walker, at
`0x1EF8`. The block is 65 words and ends at `0x1FFC`. None of them sit
in the delay loop. The step-5 success branch now enters this block.
The two words at address 0 branch to the hold, so a procedure variable
of 0 does not enter Blink3.

## What the block does

The setup has already written MT[1] = `0x50` and MT[2] = `0x70`. The
block stores 0 over both. It then fills two descriptors:

| field | LightToggle at `0x2A0` | AMMT at `0x240` |
|---|---|---|
| name | `0x4C540000` (`LT`) | `0x4D4D0000` (`MM`) |
| next | `0x240` | 0, left as NIL |
| num | 2 | 1 |
| data | `0x70` | `0x50` |
| code | `0x1048` | `0x1000` |

`w` is stored at `0x2F0`. For this image it is `0xF80`, so
`0x1048 + 0xF80 = 0x1FC8`. That address is the procedure the call
enters. The procedure compares R15 with the word after the `BLR` and
then branches to LightToggle at `0x1048`.

Install is the loop body of Load, once per descriptor:

```
LDW num, [desc, 40]
LDW data, [desc, 52]
STW data, [R12, num*4]
```

The procedure variable is reloaded from the descriptor, not taken from
the register that was just stored:

```
LDW code, [desc, 56]
LDW w, [0x2F0]
ADD body, code, w
BLR body
```

`0xD7000001` is that `BLR R1`. On the success path R1 is `0x1FC8` and
the pad reads R15 as `0x1FC4`, which is the address of the word after
the call. The pad does not execute that word.

## Why a wrong result stays dark

The step-1 through step-5 arguments still hold. Three new slots arm
the pin. A store of a non-zero difference leaves that bit clear, and
`io.led` stays 0 even if the loop runs.

- Slot 37 (`0x894`) is the OR of (MT[2] − `0x70`) and (MT[1] − `0x50`)
  after install. The values are loaded back from the table.
- Slot 38 (`0x898`) is the reloaded procedure variable minus `0x1FC8`.
- Slot 39 (`0x89C`) is R15 minus `0x1FC4` at the pad.

Those three stores do not go through the step-5 mask shifter. Widening
that shifter added about 50 LUTs and the 27 MHz path from the
instruction ROM missed timing, so that bitstream was not loaded.
`CheckTail` watches the store port instead. It registers the address
on the store cycle and compares it on the next cycle. A zero store at
`0x894`, `0x898`, or `0x89C` sets one of its three bits. The pin needs
those bits as well as the step-5 mask. The extra cycle is hundreds of
cycles before the delay loop. After this change, N=5 still edged at
8039, 8696, and 9353, and `--break-slot 39` still produced no edges.

`--break-slot 37` and `--break-slot 38` take the hold at `0x1D8C` and
do not execute the `BLR`. `--break-slot 39` does execute the `BLR` and
the pad, then takes the same hold, and does not enter `0x1048`. Each
of those runs produced 0 LED edges in 20000 cycles.
`CHAIN_FIX=0` produced 0 edges in 25000 cycles and sat on that hold
(top PCs `0x1D8C` 9246 and `0x1D90` 9245). None of those images is loaded.

A `SUB` that returns 0 for unequal operands still collapses the delay
compare, so the loop toggles at about 55 kHz. The measured rate closes
that hole. With the table left at 0, Toggle's store of `light` misses
`0x50` and the pin stays dark even if the compare is ignored.

## Simulation, fitted model

`FIRST_VALID` stays 13. Recorded before synthesis.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| moddesc | 5 | 657 | 8039 |
| moddesc | 6 | 760 | 8142 |
| moddesc | 8 | 966 | 8348 |

N=5 edges were 8039, 8696, 9353. N=6 edges were 8142, 8902, 9662.
N=8 edges were 8348, 9314, 10280. The periods are still
`103*N + 142`. The first edges are 430 cycles later than step 5 and
move by 103 when N moves by 1. The added block and the skipped AMMT
`BEGIN` are both before the delay loop.

On the N=5 success path the descriptors were stored once, as the table
above. Install wrote `0x70` at `0x18` and `0x50` at `0x14`. Slots
`0x894`, `0x898`, and `0x89C` were stored as zero. The CPU executed
the `BLR` at `0x1FC0`, the pad at `0x1FC8`, and LightToggle at
`0x1048`. Address 0 and the hold were not visited. No
`HYPER_TIMING_FAULT`.

`light` still holds the chain's sentinel `0x3C3C3C3C`, because this
call enters LightToggle and not AMMT's `BEGIN`. Toggle computes
`1 - light`, so bit 0 of the store at `0x50` still alternates. That is
the pin the measurement watches.

N=262144 at the 27 MHz CPU clock, locked from that slope before this
bitstream is built:

- cycles per edge = `103*262144 + 142` = **27,000,974**
- one edge = 1.000036 s
- full blink = **0.499982 Hz**, period **2.000072 s**

The tool's `predicted_blink3_hz` compares against 3.433 Hz and is not
this prediction. The visualizer on 127.0.0.1:8765 has no page for this
image. The Primer 20K is not part of this step.

## Hardware

PNR of `moddesc_n262144` on the GW1NSR-4C: 4045/4608 logic (88%; 3762
LUT and 283 ALU), 2235/2304 CLS (97%), 1656/3612 registers, 6/10 BSRAM
of which 4 are the instruction pROM (plus one SDPB and one SDPX9B).
Setup and hold total negative slack are 0 on every clock. The worst
setup slack is +0.040 ns, on the 27 MHz `clkdiv` clock (period 37.037
ns), from the instruction ROM `DO` to the Z flag. That clock's
achieved frequency is 27.029 MHz. The same report lists 0 setup
endpoints and 0 hold endpoints violated. The PLL was not edited: IDIV
0, FBDIV 1, ODIV 16, VCO 864 MHz, CLKOUT 54 MHz, CPU 27 MHz. Gowin
still warns that `clkdiv` was determined to be a clock but was not
created (TA1132) and that `clock_d` uses a generic routing resource
(PR1014). Both warnings are on the earlier HyperRAM images.

SRAM load, Tang Nano 4K only. `lsusb` showed the two FT2232s at bus
003 device 078 and bus 003 device 081. `--detect` on 003:081 returned
idcode `0x100981b`, GW1NSR-4C. `--detect` on 003:078 returned idcode
`0x81b`, GW2A-18. Device 078 was not loaded. An unscoped `--detect`
hits 078 first, so the load named the bus address.

```
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/moddesc_n262144.fs
```

The file is the 03:07:50 bitstream, the run whose slack is above.
`write to ram`, SRAM load 100%, CRC check success. No `-f`.

`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=nano4k`, duration
20, warmup 2. The server cwd is `blinky-blinkband/tools/webcam-mcp`
(pid 358063), whose detector band starts at 0.2 Hz. Exposure was left
to that tool's existing lock and restore. Run directory
`~/fpga/blink-measure/20261105-030829-mcp/`. Capture was `/dev/video2`,
640x480, 661 frames, delivered 30.045 fps. The tool's own JSON is
`step6-result.json`. Headline fields:

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
  "measure_roi": {"x": 220, "y": 253, "w": 46, "h": 38}
}
```

SNR on that LED was 346.06 and its chroma coefficient of variation was
0.975. The locked prediction was 0.499982 Hz. The tool reports 0.5,
which is that rate at the thousandths it prints. Its
`predicted_blink3_hz` is 3.4332275390625 (`error_pct_vs_blink3`
-85.44) and is not this prediction. The Primer 20K, in the same frame,
was `board present but not blinking` (frequency null; two steady red
LEDs). `assign_reason` was
`upper=primer20k n=2 orange=0 lower=nano4k n=2 orange=0 cy=139/272`.
The fuller payload is `step6-mcp.json`. Frames are `step6-nano4k.png`
and `step6-leds.jpg`.
