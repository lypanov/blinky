# Step 2: fixup ALU on the Primer 20K Dock (DDR3)

`FPGA_IMAGE=ddr3fixup` is the step-1 DDR3 prologue plus the twenty ALU
compares, then Blink3. `FPGA_IMAGE=ddr3` stays the memory-only prologue.
`FPGA_IMAGE=fixup` stays the Nano 4K HyperRAM image. The memory prologue's
success branch goes to the ALU at `0x1400`, and the ALU's success branch
goes to address 0, which is still Blink3's trampoline. The ALU is not in
the delay loop. The failure path is the two-instruction hold at `0x1708`,
so the ALU can sit at `0x1400`.

The DDR3 path is the one the prologue proof already used: 16 controller
clocks after busy, a refresh, 16 more clocks, read calibration committed
after 16 hits, `HOLD` on a user read, and a one-cycle `WLOADN` pulse on
the read's last cycle so the write delay reloads. Lane 0's `WSTEP` stays
forced to 10.

## Locked rate

Verilator, before the load, N = 5, 32, 128, 512, 1024. The edge periods
were 3668, 19220, 74516, 295700, and 590612. That is the step-1 line,
exact:

`pclk/edge = 576*N + 788`

N = 262144 is 150,995,732 controller clocks per edge.

- edge = 96750000/150995732 = 0.640747 Hz
- full blink = 0.320373 Hz
- 93.641 frames at 30 fps

The ALU only moves the first edge. At N = 5 that edge is cycle 25434
instead of the prologue's 22634; the period stays 3668. `+ddr3_corrupt`
returns 0 from every read, the compares miss, and the run ends with 0 LED
edges. `--break-slot 9` bumps the ANN constant, stores a non-zero
difference, and also ends with 0 LED edges.

## What the pin requires

Eight memory differences at `0x7C0`, plus twenty ALU differences at
`0x800+4*slot`. The armed mask is 28 bits, `0x0FFFFFFF`. A missing zero
leaves L14 dark. The expected ALU values are the same Python immediates
as the 4K step (`docs/hyperram/step2.md`): sign-extended MOV of -1,
the shifts and rotates of `0xA5F3C0DE`, ANN, the `WHILE` count, and the
flag tests that need V, C, N, and Z.

## Hardware

SRAM load was `openFPGALoader --busdev-num 003:078 -b tangprimer20k -m`
of `ddr3fixup_n262144.fs`. The delay word at `0x105C` is `60000004`.
Place-and-route reported 0 setup and 0 hold endpoints on `pclk` and
`cpu_clk`. The Nano 4K at `003:081` was not loaded.

UART on M11, 115200, after calibration: mask `0FFFFFFF`, no hold flag,
PC in the Blink3 delay loop (`0x106C`, `0x1074`, `0x1080`, `0x1084`).
R9 still holds the complement sum `FFFFFFE1`. The counter at halfword
`0x38` is live, and MT[2] reads back as `0x70`. Raw `wstep` was `000D`,
`wstep_run` `000A`.

Webcam `measure_blink` `roi=primer20k` `duration=20` `warmup=2`, clip
`blink-measure/20261105-080649-mcp` (661 frames, delivered 30.025 fps).
The tool reported edge 0.32 Hz on the LED at (335, 109). Raw red at
(335, 117) starts mid-blink (2 low frames) and then the complete on+off
runs are 48+46, 48+46, 47+46, 48+46, 48+46, 48+46, 47+46. Those seven
periods are 94, 94, 93, 94, 94, 94, 93. Mean 93.714 frames, 0.320384 Hz,
against the locked 0.320373 Hz (93.718 frames at this fps). The cluster
LED at (321, 143) does not follow that period. (336, 125) rises and falls
with L14, the same spill the prologue clip showed, and it is not a second
rate. The Nano 4K LED in the same clip is still 60-frame periods, 0.5 Hz.
