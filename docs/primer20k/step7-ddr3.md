# Step 7: two program files in DDR3, then Load of Blink5

`FPGA_IMAGE=ddr3files` is the Primer 20K image. The software is
the two `.rsc` images and `Load` of Blink5 from
`docs/hyperram/step7.md`. `extraChecks` stays 40. The file
compares still share the step-6 link slot at `0x89C`. The pin
stays dark unless the step-5 mask and the three tail bits all
pass. `FPGA_IMAGE=files` stays the Nano 4K HyperRAM image.
`FPGA_IMAGE=ddr3moddesc` is unchanged.

The Files block sits before the delay loop, so the rate does
not move. HyperRAM is still `103*N+142` cycles per edge. N is
262144, so the full blink is 0.499982 Hz. DDR3 is still
`pclk/edge = 576*N+788`, and the full blink is 0.320373 Hz.

## Controller

`gowin/primer20k/ddr3/ddr3_controller.v` is the same file as step 6.
It follows nand2mario/ddr3-tang-primer-20k `a6d866d`. There is no
fixed `WLEVEL_BACKOFF` and no absolute lane code. The write delay
is the trained eye. `DDR3_FILES` only selects the same UART hold
addresses as ModDesc (`0x1D8C` and `0x1D90`). The Files block at
`0x00C0` is not a hold.

## Simulation

HyperRAM Verilator, `FIRST_VALID` 13. Success leaves R9 at 0:
the Files block uses R9 as the `w` accumulator. R5 is 0 and the
shifter mask is `1fffffffffff`.

| image | edges | first | period | PC | R5 | mask |
| --- | --- | --- | --- | --- | --- | --- |
| N=5 | 3 | 12880 | 657 | `0000101c` | `00000000` | `1fffffffffff` |
| N=6 | 2 | 12983 | 760 | `0000101c` | `00000000` | `1fffffffffff` |
| N=8 | 2 | 13189 | 966 | `0000101c` | `00000000` | `1fffffffffff` |
| break slot 39 | 0 | | | `00001d8c` | `ffffffff` | `1fffffffffff` |
| break slot 40 | 0 | | | `00001d8c` | `00000000` | `1fffffffffff` |
| break slot 41 | 0 | | | `00001d8c` | `00000000` | `1fffffffffff` |
| break slot 42 | 0 | | | `00001d8c` | `00000000` | `1fffffffffff` |
| break slot 43 | 0 | | | `00001d8c` | `00000000` | `1fffffffffff` |
| skip slot 40 | 0 | | | `0000107c` | `00000000` | `1fffffffffff` |
| `--mode none` | 0 | | | `00001d90` | `00000000` | `1fffffffffff` |
| `--mode dir` | 0 | | | `00001d90` | `00000000` | `1fffffffffff` |
| `CHAIN_FIX=0` | 0 | | | `00001d8c` | `fffffff4` | `ffffffffff` |

N=5 edges were 12880, 13537, 14194. Skip slot 40 runs the delay
loop and leaves the pin dark. None of the broken images were
loaded.

`sim/run_ddr3_phy.sh` scores `PHY_SCORE pass` with no Micron
`ERROR`. The model eye is still the model's, not the Dock pair.
`IMAGE=ddr3files sim/run_ddr3_cpu_phy.sh` scores `PHY_SCORE pass`:
period 3668, first edge 58758, PC `0000101c`, R5 `00000000`,
R9 `00000000`, mask `ffffffffff`. The first edge is 17796
controller clocks later than step 6. The period is the same, so
the blink rate is the same. The bench's R9 check for this image
is 0 (`+expect_r9=0`). ModDesc still expects 8.

## Nano 4K

`files_n262144.fs` was SRAM-loaded on bus 3 address 081 only.
Idcode `0x100981b`, GW1NSR-4C. No `-f`. Webcam MCP
`http://127.0.0.1:8766/mcp`, tool `measure_blink`, `roi=nano4k`,
duration 20, warmup 2:

`blink-measure/20261106-043444-mcp`, status blinking, edge
0.499 Hz, FFT 0.5 Hz, trusted method edge, confidence 1.0,
cv 0.972, snr 360.4, 661 frames, 30 fps, `/dev/video2`, 22 s.
The expected full blink is 0.499982 Hz.

Slow corner 1.14 V 85 C on that bitstream: 32 setup endpoints on
`clkdiv`, 0 hold, TNS -20.705, Fmax 26.117 MHz against the
27.000 MHz constraint, worst slack -1.252 ns. Same miss as the
step-6 ModDesc bitstream that still measured 0.5 Hz. The desk
rate is 0.499 Hz. The SDC was not relaxed.

## Dock

SRAM only, bus 3 address 078, idcode `0x81b` GW2A-18:

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3files_n262144.fs
```

UART was opened on FTDI channel B (libftdi interface 2, 115200
8N1) before the load. The resident step-6 lines were `C.`, R9
`00000008`, programmed steps lane 1 `0008` and lane 0 `0009`.
After the load, 69 settled lines are `C.` (not held). PC stays
in the delay loop (`106C`, `1070`, `1074`, `107C`, `1080`,
`1084`). Mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`.
Programmed steps are lane 1 `000C` and lane 0 `0009`. Pattern 0
at the write-level edge and the last pattern-0 read both came
back `A55A`. `F` is `AB`: pass set, not bad, lock set,
`rclkpos=1`, `rclksel=3`. A failed install would sit on
`0x1D8C` or `0x1D90` with the pin dark.

`measure_blink`, `roi=primer20k`, duration 30, warmup 2:

`blink-measure/20261106-044009-mcp`, status blinking, edge
0.32 Hz, FFT 0.312 Hz, trusted method edge, confidence 1.0,
cv 0.967, snr 84.43, 962 frames, 30 fps, 32 s. The expected
full blink is 0.320373 Hz. The same clip shows the Nano at
0.5 Hz.

Timing on that bitstream: 0 setup and 0 hold endpoints. `pclk`
Fmax is 98.031 MHz against the 96.749 MHz constraint. Worst
listed setup slack is +0.135 ns. `cpu_clk` is 24.187 MHz.

## Step 8

Step 7 is done on the Dock. Do not extend this image into step 8.
The next image is `FPGA_IMAGE=modules` (`docs/hyperram/step8.md`),
HyperRAM first, then DDR3, same fail-closed LED. Start that on a
fresh agent.
