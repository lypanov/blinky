# Step 3: LDB/STB and the .rsc reader on the Primer 20K (not proven)

`FPGA_IMAGE=ddr3rsc` is the DDR3 prologue, the fixup ALU, then the
byte reader at `0x1800`, then Blink3. `FPGA_IMAGE=ddr3` stays the
memory-only prologue. `FPGA_IMAGE=ddr3fixup` stays the ALU image.
`FPGA_IMAGE=rsc` stays the Nano 4K HyperRAM reader. The failure path
is the two-instruction hold, so the ALU still sits at `0x1400` and the
reader at `0x1800`. The reader hold is `0x1B44`.

The DDR3 path is unchanged from the ALU proof: 16 controller clocks
after busy, a refresh, 16 more clocks, read calibration after 16 hits,
`HOLD` on a user read, and a one-cycle `WLOADN` pulse so the write
delay reloads. Lane 0's `WSTEP` stays forced to 10.

## Locked rate, from simulation only

Verilator, before any load, N = 5, 32, 128, 512, 1024. The edge
periods were 3668, 19220, 74516, 295700, and 590612. Residual 0
against the step-1 line:

`pclk/edge = 576*N + 788`

N = 262144 is 150,995,732 controller clocks per edge.

- edge = 96750000/150995732 = 0.640747 Hz
- full blink = 0.320373 Hz
- 93.641 frames at 30 fps

The reader is outside the delay loop. At N = 5 the first edge moved
from the ALU image's cycle 25434 to cycle 32902; the period stayed
3668. The trace stored a zero at all 40 check addresses (`0x7C0`
through `0x87C`) and never visited `0x1B44`. `+ddr3_corrupt` and
`--break-slot 30` both ended with 0 LED edges.

The pin requires those 40 zeros. The armed mask is 40 bits. Slots
20..31 are the lane word `0x44332211`, the four lane bytes, the
neighbour `0xA5A5A5A5`, the updated byte `0x77`, the surviving byte
`0x33`, the name, the key `0x13579BDF`, version 1, and size `0x100`.

## Hardware

The first SRAM load of `ddr3rsc_n262144.fs` on bus 003 device 078 did
not blink. UART on M11, after calibration: PC `0x1394` (the prologue
hold), mask `00000000F0`, R5 `AAAAAAAA`, raw `wstep` `000D`,
`wstep_run` `000A`. That is the same odd-column pattern-sum the first
ALU placement produced. Place algorithms 0, 1, and 2 all sat there.
The reader never started, so this was not an LDB/STB failure.

Forcing lane 0 to step 9, with lane 1 left on its calibrated step,
changed R5 from `AAAAAAAA` to `AAFFAAFF`: lane 0's bytes became `FF`
and lane 1's stayed `AA`. A later placement that walked lane 1 across
0..255 with lane 0 held at 9 parked at lane 1 = `0xFA` with R5
`65FFFFFF` and the complement sum `A9FFFFE1`. Three bytes matched.
The CPU stayed in the prologue hold and L14 stayed dark. Lane 0 at 8
and at 10 were worse (`20AA38AA`, `9AFF9AFF`). No pair put R5 at
`FFFFFFFF`.

The webcam was not used. The locked rate was not changed to chase the
camera. The Nano 4K was not loaded. The Dock was put back on the
accepted ALU bitstream `ddr3fixup_n262144.fs`.
