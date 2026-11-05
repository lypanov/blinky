# Step 4: one BL stored in DDR3 and fetched back

`FPGA_IMAGE=ddr3fetch` is the Primer 20K image. It is the DDR3
prologue, the fixup ALU, the byte reader, then the stored-BL prologue
at `0x1C80`, the fetch of `0x1F00`, the stub at `0x1C00`, and Blink3.
`FPGA_IMAGE=fetchbl` stays the Nano 4K HyperRAM image and is not
rebuilt or loaded. `FPGA_IMAGE=ddr3`, `ddr3fixup`, and `ddr3rsc` stay
their own images.

The software is the step-4 chain from `docs/hyperram/step4.md`.
`dest` is `0x1C00`, `adr` is `0x1F00`, and the FixP word is
`0xF7FFFF3F`. The ROM at `0x1F00` is the hold `ADD R1,R1,1`
(`41180001`), not the BL. The BL is stored by the prologue and read
back through the DDR3 bridge. `extraChecks` is 34. The pin gate is
42 bits. The UART mask is still 40 bits, so slots 32 and 33 are not
on the line. A full UART mask plus the blink is those two slots.

The first loaded bitstream forced both write lanes to step 10, the
eye the step-3 place passed on. There is no step sweep. Lane 1 is
not left on the write-level result. The ALU image is unchanged. On
this route those codes are the even-word alias, and so is step 9.
The image on the Dock uses backoff 1 on lane 0 and backoff 3 on
lane 1. On that build the edges were `000C` and `000A`, so the
programmed steps are `000B` and `0007`. The stand-in takes those
steps. It does not take the write-level edge. That pass is the last
section.

The new code is outside the delay loop. The period stays the step-1
line. The HyperRAM formula `103*N+142` is not this board.

## Locked rate, from simulation only

`sim/run_ddr3_standin.sh`, this route's eye
(`+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7`, `HOLD`, `WLOADN`,
no pin mask). Bare `+ddr3_fetch_eye` leaves both lanes at 10 and is
not this table. The period and the first edge are the same numbers
the center-10 eye printed, because offset 0 returns the same bytes.
The loaded step-10 pair is not this table. It is the prologue hold
under "What a DDR3 miss looks like".

| N | period | first edge | mask | R5 | R9 |
| --- | ---: | ---: | --- | --- | --- |
| 5 | 3668 | 33550 | `3FFFFFFFFFF` | `00000000` | `FFFFFFE1` |
| 8 | 5396 | 35278 | `3FFFFFFFFFF` | `00000000` | `FFFFFFE1` |
| 32 | 19220 | 49102 | `3FFFFFFFFFF` | `00000000` | `FFFFFFE1` |

Residual 0 against:

`pclk/edge = 576*N + 788`

The first edge is 648 `pclk` cycles later than the reader image
(32902 at N = 5, 48454 at N = 32). The period did not move. N =
262144 is 150,995,732 controller clocks per edge.

- edge = 96750000/150995732 = 0.640747 Hz
- full blink = 0.320373 Hz
- 93.641 frames at 30 fps, 93.590 frames at 29.984 fps

The sim mask is 42 bits, all ones. The UART prints bits `(39,0)`, so
a pass line shows `FFFFFFFFFF`. The LED is the other two bits.

At the edge the PC was `0x101C`, inside the Blink3 delay loop.

## Dark cases, also before synthesis

None of these images is loaded.

| case | PC | sim mask | edges |
| --- | --- | --- | ---: |
| `--break-slot 32` (expected BL + 1) | `0x1CDC` | `FFFFFFFFFF` | 0 |
| `--break-slot 33` (expected link + 1) | `0x1C20` | `1FFFFFFFFFF` | 0 |
| `FETCH_STORED=0` (ROM fetch of the same words) | `0x1F00` | `1FFFFFFFFFF` | 0 |

`--pc` matches an 8-byte window, so the slot-32 hold is the spin at
`0x1CD8` / `0x1CDC`. The UART cannot see bit 40 or bit 41, so all
three print a 40-bit mask of `FFFFFFFFFF` and leave L14 dark. The PC
on the line is what separates them. A pass does not sit on
`0x1390`, `0x1B44`, `0x1CD8`, `0x1C20`, or `0x1F00`.

The fetch stalls on `0x1F00` while the stored word is read, then
leaves. That address is not latched as `H`. `H` is the prologue
hold, the reader hold, or one of the two compare spins.

## What a DDR3 miss looks like on this image

The fetch program does not change the prologue misses. With
`+ddr3_place_fetch` and the lanes left at 10, the loaded bitstream's
pair holds at `0x1394` with R5 `AAAAAAAA`, R9 `55555536`, mask `F0`,
and 0 edges. `+ddr3_center=9` prints that same line. These two still
name other places, and both hold at `0x1394` with mask `F0` and 0
edges:

| plusargs | R5 | R9 |
| --- | --- | --- |
| `+ddr3_pin_even=20FF +ddr3_odd_clear=2` | `DFAADFAA` | `20532036` |

`+ddr3_center=9` with the lanes left at 10 is this route's loaded
pair, not a second place. `55555554` remains the one-column miss one
step below the eye. A sum the stand-in does not print for the
programmed pair is a stop. Do not walk `WSTEP`.

## Pass line, before the load

This was the reader's center, written down before the load. It is
not this route. Calibration `C`, hold `.`, PC in the delay loop,
mask `FFFFFFFFFF`, R5 `00000000`, R9 `FFFFFFE1`, both programmed
steps `000A`. Then L14 at 0.320373 Hz, counted from raw frames, not
from the tool headline.

```
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3fetch_n262144.fs
```

No `-f`. The Nano 4K at `003:081` is not loaded. UART is M11, 115200
8N1, FTDI channel B (libftdi interface 2) on bus 3 address 78, opened
before the SRAM load.

## This place, after the load

Synthesis and place-and-route of `ddr3fetch_n262144.fs` finished with
TNS 0.000 and 0 failing endpoints on `pclk` and on `cpu_clk`, setup
and hold. The delay word in the image is `60000004`. ROM `0x1F00` is
`41180001`. SRAM load was bus 003 device 078 only. The Nano 4K was
not opened.

The repeating line is not the default eye:

```
CH1390 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 000A 000A
```

Calibration done, prologue hold, mask `00000000F0`, R5 `AAAAAAAA`,
R9 `55555536`, both programmed steps `000A`. The read column is
`000003F9`, beats `A5A5A5A5`, last write `000003EF` data `00000000`.
The CPU never left the prologue, so the fetch did not run. L14 stayed
dark. The webcam was not used.

`sim/run_ddr3_standin.sh` prints that PC class, mask, R5, and R9 for
`+ddr3_place_fetch` with both lanes left at 10, and for
`+ddr3_center=9`. Step 3's place at those same steps was the pass.
This place is the one-column miss one step above the eye.

The command stream is not what moved. The prologue is the reader's
prologue, and the CPU never left it, so the stored BL did not run.
Both lanes were the same absolute codes that passed on the reader
route. The burst neighbor is `A5A5A5A5`: the even word was copied
onto the next column on both lanes. That is the whole-column offset
+1, not the earlier pin split (`DFAADFAA`, neighbor `25A5`). The
center is the routed write clock against the DRAM. TNS 0 says the
FPGA's own constraints are met. It does not keep DLL step 10 on a
new route's eye.

`+ddr3_place_fetch +ddr3_lane0=9 +ddr3_lane1=9` is the pass: period
3668, first edge 33550, mask `3FFFFFFFFFF`, R5 `00000000`, R9
`FFFFFFE1`, PC in the delay loop. `DDR3_FETCH` now programs that
pair. One rebuild, one SRAM load. The expected line is calibration
`C`, PC in the delay loop, UART mask `FFFFFFFFFF`, R5 `00000000`,
R9 `FFFFFFE1`, both steps `0009`, then L14 at 0.320373 Hz. If that
trial is `55555554`, or any sum this model does not print for step
9, stop. Do not walk `WSTEP`.

No second bitstream was loaded to move `WSTEP` on the step-10 image.
The Dock was put back on `ddr3fixup_n262144.fs`. A fresh line
from that image:

```
C.106C 0FFFFFFF FFFFFFFF 0000000D 00700000 00000039 00000003 FFFFFFE1 000D 000A
```

## Step 9 trial

One rebuild of `ddr3fetch_n262144.fs` at `878b767`, TNS 0.000 on
`pclk` and `cpu_clk`. One SRAM load on bus 003 device 078. The
repeating line is the same whole-column miss, with the programmed
steps now `0009`:

```
CH1390 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 0009 0009
```

At `878b767`, `+ddr3_place_fetch +ddr3_lane0=9 +ddr3_lane1=9` printed
R5 `00000000`, not `AAAAAAAA`. No further step was loaded. The
webcam was not used. The Dock is back on the ALU image:

```
C.106C 0FFFFFFF FFFFFFFF 0000000D 00700000 00000039 00000003 FFFFFFE1 000D 000A
```

Tip `878b767` failed on the Dock. The same column, beats, write
address, R5, and R9 came back with the steps changed from `000A` to
`0009`. The absolute code is not the center on this route. Steps 9
and 10 are the same even-word alias.

## Both lanes at the write-level edge minus 3

On the ALU place the write-level edge is `000D` and the passing
delay is `000A`, three codes earlier. Lane 0 at the edge itself is
the odd-column-reads-as-even failure. The fetch route moved that
edge. Forcing 9 or 10 does not track it, and one code does not leave
the alias. The next bitstream loaded each lane with its own edge
minus 3. The UART steps are those delays, not constants.

`+ddr3_place_fetch` reads the step. Lanes at 10 and lanes at 9 both
print the Dock line, because those two codes were measured as offset
+1. A different code is not forced onto that line. Lane 8 is the
eye check that shows the step is read.

## Edge minus 3

One SRAM load of that bitstream, TNS 0 on `pclk` and `cpu_clk`. The
line repeats:

```
CH1394 00000000F0 00550054 000003F9 A5A5A5A5 000003EF 00000000 FFAAFF8C 0007 000A
```

Mask `F0`, R5 `00550054`, R9 `FFAAFF8C`, steps `0007` `000A`. UART
order is lane 1 then lane 0, so lane 1 is `0007` and lane 0 is
`000A`. Against the centers of the image that passed (lane 0 at 11,
lane 1 at 7) this is lane 0 one below its eye, not the pass and not
`AAAAAAAA`. `+ddr3_fetch_eye +ddr3_lane0=10 +ddr3_lane1=7` prints
this line. This build's lane 0 edge was `000D` (`000A` plus 3). The
image that passed measured that edge as `000C`. The stand-in does
not take either edge.

## Edge minus 2 / edge minus 3

One SRAM load of lane 0 at edge-2 and lane 1 at edge-3, TNS 0 on
`pclk` and `cpu_clk`. The line repeats:

```
CH1390 00000000F0 DFFFDFFF 000003F9 A5A5A5A5 000003EF 00000000 1FFE1FE1 0007 000B
```

Steps `0007` `000B` are lane 1 at `000A-3` and lane 0 at `000D-2`.
The sum is not the pass and not `00550054`. Fourteen pins are on the
eye. DQ1 is one column early, and DQ13 carries the even word of its
BC4 group onto both words. MT[1], MT[2], the alias word, and the
sentinel still match, so the mask stays `F0`. `+ddr3_fetch_split`
prints this line. That is the pin split, not offset 0. The same
codes `0007` `000B` are the pass on a later image. The model cannot
choose between them from the codes, because it has no write-level
edge.

## Backoff 1 and backoff 4

One SRAM load with lane 0 backoff 1 and lane 1 backoff 4. Lane 0's
edge came back `000C`, so code `000B` is still edge-1 of that edge.
Lane 1's edge stayed `000A`, so backoff 4 is `0006`. The line repeats:

```
CH1394 00000000F0 AAFFAAFF 000003F9 A5A5A5A5 000003EF 00000000 550054E1 0006 000B
```

Mask `F0`, sentinel beats `A5A5A5A5`. The bytes have the shape of
lane 0 centered and lane 1 in the even-word alias. That is not
`+ddr3_lane1=11`: that plusarg leaves lane 0 at the old center 10
and prints R5 `FFAAFFAA`. Under the Dock centers, lane 1 at `0006`
with lane 0 at `000B` is one below, R5 `550054FF`
(`+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=6`), the same row as
`+ddr3_lane1=9` on center 10. The even-word alias with lane 0 on
its eye is lane 1 one above, step 8
(`+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=8`, R5 `AAFFAAFF`).
`0006` is not both rows. This UART is an earlier image. The model
has no edge, so it does not map that image's `0006` onto either
row of the pass image.

## Pass

Lane 0 stays at backoff 1. Lane 1 is backoff 3. TNS is 0.000 on
`pclk` and `cpu_clk`. The edges stayed `000C` and `000A`, so the
steps are `0007` `000B`. Edge `000A` minus 4 is `0006`, the miss in
the previous section. Edge `000C` minus 1 and edge `000A` minus 3
are these steps. The line repeats, and the PC moves through the
delay loop (`0x106C`, `0x1074`, `0x107C`, `0x1080`):

```
C.1080 FFFFFFFFFF 00000000 00000038 00031B62 00000039 00000003 FFFFFFE1 0007 000B
```

Calibration is `C`. The PC is not `0x1390`. The mask is
`FFFFFFFFFF`. R5 is `00000000`. R9 is `FFFFFFE1`.
`+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7` is this line: period
3668, first edge 33550, mask `3FFFFFFFFFF`, R5 `00000000`, R9
`FFFFFFE1`. Bare `+ddr3_fetch_eye` is not the witness.

The clip is `blink-measure/20261105-121417-mcp` from
`measure_blink` on `http://127.0.0.1:8766/mcp`, `roi=primer20k`,
`duration=20`, `warmup=2`, `/dev/video2`, 661 frames, 30 fps. The
tool headline was `edge=0.32`. Raw red at (334, 108), threshold 100,
starts with 11 low frames and then the complete on+off runs are
47+46, 48+46, 48+46, 47+47, 47+46, 48+46. Those six periods are 93,
94, 94, 94, 93, 94. Mean 93.667 frames, 0.320285 Hz. At 30 fps the
locked length is 93.641 frames. The Nano 4K LED in the same clip is
the 0.499 Hz blinker. L14 is the Dock.

Root cause: the eye of the image on the Dock is programmed step 11
on lane 0 and programmed step 7 on lane 1.
`+ddr3_fetch_eye` sets those two centers, and the witness is
`+ddr3_lane0=11 +ddr3_lane1=7`. The stand-in has no write-level
input, so it does not say whether the next build's edge-1 and
edge-3 pair is still this eye. Lane 0's edge was `000D` on the
both-backoff-3 trial and `000C` on the later trials. Steps 9 and 10
on the earlier absolute-step image are both offset +1, and the
model reads the step. The pin split `DFFFDFFF` is
`+ddr3_fetch_split`, not offset 0. Step `0006` is not both
one-below-center and the even-word alias: one below is lane 1 at 6
(R5 `550054FF`) and the even-word alias is lane 1 at 8
(R5 `AAFFAAFF`).

Step 5 is not started. The Nano 4K was not loaded. Nothing was
written to flash. The Dock is on this SRAM image.
