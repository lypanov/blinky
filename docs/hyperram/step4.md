# Step 4: one BL stored in HyperRAM and fetched back

`tests/BlinkFetch.Mod` is a new file. `tests/BlinkBoot.Mod` and
`tests/BlinkRsc.Mod` were not edited. Nothing under `oberon/src` was
edited. The host has no Oberon compiler in this build, so
`sim/build_fetchbl_imem.py` emits the ORG encodings the module describes.
The formula is `Modules.Mod`, the BL fixup:

```
offset := (dest - adr - 4) DIV 4;
SYSTEM.PUT(adr, (offset MOD 1000000H) + 0F7000000H)
```

`dest` is the stub at `0x1C00`. `adr` is `0x1F00`. Python arithmetic
(arithmetic right shift, then the low 24 bits, then add `0xF7000000`)
gives `0xF7FFFF3F`. That branch target is `0x1C00`, and the link it
plants is `0x1F04`. Dropping the `MOD 1000000H` leaves the sign-filled
shift, which is not `0xF7FFFF3F`. The compare uses ADD, the same operator
as the `+` in `Modules.Mod`.

`FPGA_IMAGE=blink3` stays block RAM. `FPGA_IMAGE=hyperram`, `fixup`, and
`rsc` stay their own images. Rebuilding the step-3 words with the
success-target default of 0 is byte-identical to the accepted image.
`FPGA_IMAGE=fetchbl` is the only image that will be loaded for this step.
It is nano4k HyperRAM, the same top and PLL as the previous HyperRAM
images. `FIRST_VALID` stays 13. The HyperRAM model was not edited.

The chain is the memory prologue, the ALU at `0x1400`, the reader at
`0x1800`, a prologue at `0x1C80`, a fetch of `0x1F00`, the stub at
`0x1C00`, then address 0. None of the new instructions sit in the delay
loop.

## The stored word

The ROM at `0x1F00` is `ADD R1, R1, 1` followed by a branch back to
`0x1F00`. It is not `0xF7FFFF3F`. The BL exists in the ROM only as the
`MHI` / `IOR` immediates of the compare.

The prologue computes the FixP word, stores it at `0x1F00`, and reads
that address back. Slot 32 (`0x880`) is the difference against
`0xF7FFFF3F`. A non-zero `R10` branches to the prologue hold at `0x1CD8`.
A zero `R10` branches (not BL) to `0x1F00`.

The CPU then stalls with the PC on `0x1F00` and reads that address as an
instruction. The ROM output register is loaded from the HyperRAM word for
one clock. The decoder still sees that register. Every other PC keeps the
ROM read. There is no mux after the ROM output, because the step-3
bitstream's worst setup slack on this path was +0.006 ns.

The stub subtracts `0x1F04` from `R15` into slot 33 (`0x884`). A non-zero
difference holds at `0x1C20`. A zero difference branches to address 0.
Setup and the prologues use `B`, so `R15` is still the reset value `0xB0`
until this BL. A `B` that merely jumped at the stub would leave `0xB0`.

`extraChecks` is 34. The pin gate is 42 bits: the previous 40, plus slots
32 and 33. The slot index is `aluDelta[8:2]` plus the 8 memory slots, so
slot 32 (byte offset `0x80`) does not wrap onto slot 0. `io.led` is the
Blink3 LED state AND that mask being all ones.

## Why a wrong result cannot blink at this rate

The step-1, step-2, and step-3 arguments still hold. The reader enters
this prologue only when its own `R10` is zero. Address 0 is reached only
from the stub, after slot 33.

- The data load of `0x1F00` must equal `0xF7FFFF3F`. Anything else holds
  at `0x1CD8` and never fetches. The unmasked sign-filled shift fails
  this compare.
- The ROM word at `0x1F00` is a hold. A split bus that still fetches the
  ROM sits on `0x1F00` / `0x1F04`, never enters the stub, and never arms
  slot 33. `R15` stays `0xB0`.
- HyperRAM returning 0 at that address executes `MOV` and then the ROM
  branch back into the hold. Also dark.
- A `B` instead of `BL`, or a `BL` from another PC, leaves `R15` unequal
  to `0x1F04`. Slot 33 stays clear and the stub holds.
- Skipping the stub's compare and branching to address 0 anyway leaves
  slot 33 clear, so the pin stays dark.
- The same software hole as step 2 remains: a SUB that returns 0 for
  unequal operands stores zeros and skips the hold. It also makes the
  delay compare return 0, so the loop toggles every iteration, at about
  55 kHz, not at half a hertz. The measured rate closes that hole.

`--break-slot 32` adds 1 to the expected BL. `R10` became `0xFFFFFFFF`,
the CPU sat at `0x1CD8`, `0x1F00` was never fetched, and 20000 cycles
produced 0 LED edges. `--break-slot 33` adds 1 to the expected link. The
BL did run (`R15` was `0x1F04`) and the stub then sat at `0x1C20`, again
0 edges in 20000 cycles. `FETCH_STORED=0` is the same words with the ROM
fetch. The data compare passed (`R10` stayed 0) and the CPU sat on the
ROM hold at `0x1F00` / `0x1F04` with `R15` still `0xB0`, 0 edges in 20000
cycles. None of those three images is loaded.

## Simulation, fitted model

`FIRST_VALID` stays 13. Recorded before synthesis.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| fetchbl | 5 | 657 | 6623 |
| fetchbl | 6 | 760 | 6726 |
| fetchbl | 8 | 966 | 6932 |
| blink3, this CPU | 5 | 93 | 111 |
| rsc, this CPU | 5 | 657 | 6503 |

N=5 edges were 6623, 7280, 7937, 8594, 9251, 9908, 10565, 11222. N=6
edges were 6726, 7486, 8246, 9006, 9766, 10526. N=8 edges were 6932,
7898, 8864, 9830, 10796, 11762.

That is still `103*N + 142`. The new prologue and the one HyperRAM fetch
sit before the delay loop. They move the first edge (step 3's N=5 first
edge was 6503; this one is 6623) and they do not change the period.
Blink3 on this CPU is still 111, 204, 297, 390, 483, 576. The step-3
image on this CPU is still 6503 then 657.

On the N=5 success path, all 42 check words were stored as zero. The BL
`0xF7FFFF3F` was stored at `0x1F00` from PC `0x1CAC`. The PC then sat on
`0x1F00` for the load and left for `0x1C00` with `R15` = `0x1F04`. It
never executed `0x1F04`. The holds at `0x1708`, `0x1B44`, `0x1CD8`, and
`0x1C20` were not visited. No `HYPER_TIMING_FAULT`.

N=262144 at the 27 MHz CPU clock, locked from that slope before this
bitstream is built:

- cycles per edge = `103*262144 + 142` = **27,000,974**
- one edge = 1.000036 s
- full blink = **0.499982 Hz**, period **2.000072 s**

Not the block-RAM 3.433 Hz, and not the pre-load 0.520 Hz. A dark hold is
the failure state. The tool's `predicted_blink3_hz` compares against
3.433 Hz and is not this prediction.

The visualizer on 127.0.0.1:8765 has no page for this image. The Primer
20K is not part of this step.

## Hardware

PNR of `fetchbl_n262144` on the GW1NSR-4C: 3332/4608 logic (73%),
2020/2304 CLS (88%), 1321/3612 registers, 6/10 BSRAM of which 4 are the
instruction pROM (plus one SDPB and one SDPX9B). The `if (overlayEn)`
load of the ROM output register still inferred pROM. Setup and hold
total negative slack are 0 on every clock. The worst setup slack is
+0.145 ns, on the 27 MHz `clkdiv` clock (period 37.037 ns), from the
instruction ROM `DO` to the Z flag. The PLL was not edited: IDIV 0,
FBDIV 1, ODIV 16, VCO 864 MHz, CLKOUT 54 MHz, CPU 27 MHz.

SRAM load, Tang Nano 4K only. `lsusb` still showed the two FT2232s at
bus 003 device 078 and bus 003 device 081. `--detect` on 003:081
returned idcode `0x100981b`, GW1NSR-4C. Device 078 was not detected and
not loaded.

```
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/fetchbl_n262144.fs
```

`write to ram`, SRAM load 100%, CRC check success. No `-f`.

`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=nano4k`, duration
20, warmup 2. The server cwd is `blinky-blinkband/tools/webcam-mcp`
(pid 358063), whose detector band starts at 0.2 Hz. Exposure was left
to that tool's existing lock and restore. Run directory
`~/fpga/blink-measure/20261105-014837-mcp/`. The tool's own JSON is
`step4-result.json`. Headline fields:

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
  "measure_roi": {"x": 221, "y": 252, "w": 45, "h": 40}
}
```

SNR on that LED was 255.85. The trace title reads `0.500 Hz`. The
locked prediction was 0.499982 Hz; the tool reports 0.5. Its
`predicted_blink3_hz` is 3.4332275390625 and is not this prediction.
The Primer 20K, in the same frame, was `board present but not blinking`
(frequency null; one steady red LED and one steady orange LED).
`assign_reason` was `upper=primer20k n=2 orange=1 lower=nano4k n=2 orange=0 cy=131/272`.
The fuller payload is `step4-mcp.json`. Frames are `step4-nano4k.png`
and `step4-leds.jpg`.
