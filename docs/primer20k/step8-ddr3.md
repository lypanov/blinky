# Step 8: Modules.Init on DDR3, then Load of Blink5

`FPGA_IMAGE=ddr3modules` is the Primer 20K image. The software is
`Modules.Init` with a 4 KB reserve, then `Load` of Blink5, from
`docs/hyperram/step8.md`. `extraChecks` stays 40. Init's difference
is XOR-ed into the step-7 store at the link slot `0x89C`. The pin
stays dark unless the step-5 mask and the three tail bits all
pass. `FPGA_IMAGE=modules` stays the Nano 4K HyperRAM image.
`FPGA_IMAGE=ddr3files` is unchanged.

The Modules body sits before the delay loop, so the rate does
not move. HyperRAM is still `103*N+142` cycles per edge. N is
262144, so the full blink is 0.499982 Hz. DDR3 is still
`pclk/edge = 576*N+788`, and the full blink is 0.320373 Hz.

## Controller

`gowin/primer20k/ddr3/ddr3_controller.v` is the same file as step 7.
It follows nand2mario/ddr3-tang-primer-20k `a6d866d`. There is no
fixed `WLEVEL_BACKOFF` and no absolute lane code. The write delay
is the trained eye. `DDR3_MODULES` only selects the same UART hold
addresses as Files (`0x1D8C` and `0x1D90`). The Modules body at
`0x06C0` is not a hold.

## Simulation

HyperRAM Verilator, `FIRST_VALID` 13. Success leaves R9 at 0:
Load of Blink5 still uses R9 as the `w` accumulator. R5 is 0 and
the shifter mask is `1fffffffffff`.

| image | edges | first | period | PC | R5 | R9 | mask |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N=5 | 3 | 13120 | 657 | `0000101c` | `00000000` | `00000000` | `1fffffffffff` |
| N=6 | 3 | 13223 | 760 | `0000101c` | `00000000` | `00000000` | `1fffffffffff` |
| N=8 | 3 | 13429 | 966 | `0000101c` | `00000000` | `00000000` | `1fffffffffff` |
| `--break-dec` | 0 | | | `00001d8c` | `00000000` | `00000000` | `0` |
| `--break-dec --fall` | 0 | | | `00001d8c` | `00000000` | `00000000` | `1fffffffffff` |
| `--skip-proof` | 0 | | | `00001d8c` | `00000000` | `00000000` | `1fffffffffff` |
| break slot 40 | 0 | | | `00001d8c` | `00000000` | `00000000` | `1fffffffffff` |
| skip slot 40 | 0 | | | `0000106c` | `00000000` | `00000000` | `1fffffffffff` |
| `--mode none` | 0 | | | `00001d90` | `00000000` | `00000000` | `1fffffffffff` |
| `--mode dir` | 0 | | | `00001d90` | `00000000` | `ffffffb8` | `1fffffffffff` |
| `CHAIN_FIX=0` | 0 | | | `00001d8c` | `fffffff4` | `00000008` | `ffffffffff` |

N=5 edges were 13120, 13777, 14434. N=6 edges were 13223, 13983,
14743. N=8 edges were 13429, 14395, 15361. Skip slot 40 runs the
delay loop and leaves the pin dark. `CHAIN_FIX=0` stops in the
step-5 hold with R9 still 8. None of the broken images were
loaded.

`sim/run_ddr3_phy.sh` scores `PHY_SCORE pass` with no Micron
`ERROR`. The model eye is the model's (`wstep` `1a`/`1a`, run
`16`/`17`). `IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh` scores
`PHY_SCORE pass`: period 3668, first edge 60074, PC `0000101c`,
R5 `00000000`, R9 `00000000`, mask `ffffffffff`. The first edge is
1316 controller clocks later than step 7. The period is the same,
so the blink rate is the same. The bench's R9 check for this image
is 0 (`+expect_r9=0`).

## Nano 4K

`modules_n262144.fs` is the 04:54:39 bitstream. PNR on the
GW1NSR-4C: 3982/4608 logic (87%; 3699 LUT and 283 ALU), 2173/2304
CLS (95%), 1656/3612 registers, 6/10 BSRAM (4 pROM, one SDPB, one
SDPX9B). SRAM-loaded on bus 3 address 081 only. Idcode
`0x100981b`, GW1NSR-4C. No `-f`. `write to ram`, SRAM load 100%,
CRC check success. Device 078 was not loaded.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/modules_n262144.fs
```

Webcam MCP `http://127.0.0.1:8766/mcp`, tool `measure_blink`,
`roi=nano4k`, duration 20, warmup 2:

`blink-measure/20261106-045544-mcp`, status blinking, edge
0.5 Hz, FFT 0.5 Hz, trusted method edge, confidence 1.0,
cv 0.975, snr 283.62, 661 frames, 30.045 fps, `/dev/video2`, 22 s.
The expected full blink is 0.499982 Hz.

Slow corner 1.14 V 85 C on that bitstream: 32 setup endpoints on
`clkdiv`, 0 hold, TNS -20.705, Fmax 26.117 MHz against the
27.000 MHz constraint, worst slack -1.252 ns. Same miss as the
step-7 Files bitstream that still measured 0.5 Hz. The desk
rate is 0.5 Hz. The SDC was not relaxed. The PLL was not edited.

## Dock

SRAM only, bus 3 address 078, idcode `0x81b` GW2A-18. The file
is the 04:55:56 bitstream.

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3modules_n262144.fs
```

UART was opened on FTDI channel B (libftdi interface 2, 115200
8N1) before the load. The resident step-7 lines were `C.`, R9
`00000000`, programmed steps lane 1 `000C` and lane 0 `0009`.
The SRAM load resets the FTDI link. Reopened after the load, the
boot line is `..0080`, then 54 settled lines are `C.` (not held).
PC stays in the delay loop (`106C`, `1070`, `1074`, `1080`,
`1084`). Mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`.
Programmed steps are lane 1 `000C` and lane 0 `0009`. Pattern 0
at the write-level edge and the last pattern-0 read both came
back `A55A`. `F` is `AB`: pass set, not bad, lock set,
`rclkpos=1`, `rclksel=3`. Locked backoff is `C0 00`, `C1 06`,
`BO 07`. A failed install would sit on `0x1D8C` or `0x1D90` with
the pin dark.

`measure_blink`, `roi=primer20k`, duration 30, warmup 2:

`blink-measure/20261106-045752-mcp`, status blinking, edge
0.32 Hz, FFT 0.312 Hz, trusted method edge, confidence 1.0,
cv 0.969, snr 92.11, 962 frames, 30.062 fps, 32 s. The expected
full blink is 0.320373 Hz. The same clip shows the Nano at
0.499 Hz.

Timing on that bitstream: 0 setup and 0 hold endpoints. `pclk`
Fmax is 98.031 MHz against the 96.749 MHz constraint. Worst
listed setup slack is +0.135 ns. `cpu_clk` is 24.187 MHz.

## Ladder

Step 8 is the last software-ladder step on this DDR3 path.
The Nano slow-corner miss on `clkdiv` is the same one recorded
in steps 6 and 7. The measured rate is 0.5 Hz. The SDC was not
relaxed.
