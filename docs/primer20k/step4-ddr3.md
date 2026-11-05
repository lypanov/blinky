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

The loaded bitstream forces both write lanes to step 10, the eye the
step-3 place passed on. There is no step sweep. Lane 1 is not left
on the write-level result. The ALU image is unchanged. On this route
those codes are one DLL step above the eye. The source now forces
both lanes to step 9, which is the one program named below.

The new code is outside the delay loop. The period stays the step-1
line. The HyperRAM formula `103*N+142` is not this board.

## Locked rate, from simulation only

`sim/run_ddr3_standin.sh`, this route's eye (`+ddr3_place_fetch`,
both lanes at step 9, `HOLD`, `WLOADN`, no pin mask). The period and
the first edge are the same numbers the center-10 eye printed,
because offset 0 returns the same bytes. The loaded step-10 pair is
not this table. It is the prologue hold under "What a DDR3 miss looks like".

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

`+ddr3_place_fetch +ddr3_lane0=9 +ddr3_lane1=9` prints R5
`00000000`, not `AAAAAAAA`. The model does not print this sum for
step 9. No further step was loaded. The webcam was not used. The
Dock is back on the ALU image:

```
C.106C 0FFFFFFF FFFFFFFF 0000000D 00700000 00000039 00000003 FFFFFFE1 000D 000A
```

Tip `878b767` failed on the Dock. The same column, beats, write
address, R5, and R9 came back with the steps changed from `000A` to
`0009`. The stand-in agent now owns finishing step 4, board and
model together, until those two agree. This note is the record of
both trials. The Dock stays on `ddr3fixup_n262144.fs`. No further
fetch bitstream is loaded from here, and step 5 is not started.
