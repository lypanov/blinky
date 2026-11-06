# Step 6: module table in DDR3

`FPGA_IMAGE=ddr3moddesc` is the Primer 20K image. The software is
the module table and the procedure-variable call from
`docs/hyperram/step6.md`. `extraChecks` is 40: the 37 shifter
slots plus the three tail compares at `0x894`, `0x898`, and
`0x89C`. The pin stays dark unless the shifter mask and the tail
bits all pass. `FPGA_IMAGE=moddesc` stays the Nano 4K HyperRAM
image.

The ModDesc block sits before the delay loop, so the rate does
not move. HyperRAM is still `103*N+142` cycles per edge. N is
262144, so the full blink is 0.499982 Hz. DDR3 is still
`pclk/edge = 576*N+788`, and the full blink is 0.320373 Hz.

## Controller

`gowin/primer20k/ddr3/ddr3_controller.v` is the same file as step 5.
It follows nand2mario/ddr3-tang-primer-20k `a6d866d`. NESTang's
last Primer 20K controller is `8b8f4fa` and does not subtract a
fixed write-level backoff. The local deltas stay in
`gowin/primer20k/ddr3/NOTICE`.

There is no fixed `WLEVEL_BACKOFF` and no absolute lane code. The
write delay is the trained eye: eight halfwords, offsets -4..+12
from each lane's own write-level edge, and a point counts only
when `dq_in[0]` matches the whole word.

## Simulation

HyperRAM Verilator, same cycle count as the DDR3 CPU bench:

| image | edges | first | period | PC | R5 | mask |
| --- | --- | --- | --- | --- | --- | --- |
| N=5 | 3 | 8039 | 657 | `0000101c` | `00000000` | `1fffffffffff` |
| N=6 | 2 | 8142 | 760 | `0000101c` | `00000000` | `1fffffffffff` |
| N=8 | 2 | 8348 | 966 | `0000101c` | `00000000` | `1fffffffffff` |
| break slot 37 | 0 | | | `00001d90` | `ffffffff` | `1fffffffffff` |
| break slot 38 | 0 | | | `00001d90` | `00000000` | `1fffffffffff` |
| break slot 39 | 0 | | | `00001d90` | `00000000` | `1fffffffffff` |
| `CHAIN_FIX=0` | 0 | | | `00001d8c` | `fffffff4` | `ffffffffff` |

R9 stays `00000008`. None of the broken images were loaded.

`sim/run_ddr3_phy.sh` scores `PHY_SCORE pass` with no Micron
`ERROR`. The model eye is still the model's, not the Dock pair.
`sim/run_ddr3_cpu_phy.sh` on `ddr3moddesc` N=5 also scores
`PHY_SCORE pass`: period 3668, first edge 40962, PC `0000101c`,
R5 `00000000`, R9 `00000008`, mask `ffffffffff`. The first edge is
2388 controller clocks later than step 5. The period is the same,
so the blink rate is the same.

## Nano 4K

`moddesc_n262144.fs` was SRAM-loaded on bus 3 address 081 only.
Webcam MCP `http://127.0.0.1:8766/mcp`, tool `measure_blink`,
`roi=nano4k`, duration 20, warmup 2:

`blink-measure/20261106-041336-mcp`, status blinking, 0.5 Hz,
edge and FFT both 0.5, trusted method edge, confidence 1.0,
cv 0.976, snr 221.19, 661 frames, 30.045 fps, `/dev/video2`.
That clip still showed the resident step-5 Primer image at
0.32 Hz. After the Dock load below, the same frame shows the
Nano at 0.499 Hz.

Slow corner 1.14 V 85 C on that bitstream: 32 setup endpoints on
`clkdiv`, 0 hold, TNS -20.705, Fmax 26.117 MHz against the
27.000 MHz constraint, worst slack -1.252 ns. The path is
instruction-ROM data out to the next ROM address, 18 levels,
mostly route. `place_option` 0 was worse. `place_option` 1
matched `place_option` 2, which is what the build script keeps.
The desk measurement is still 0.5 Hz. The SDC was not relaxed.

## Dock

SRAM only, bus 3 address 078, idcode `0x81b` GW2A-18:

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3moddesc_n262144.fs
```

UART was already open on FTDI channel B (libftdi interface 2,
115200 8N1). Sixty-eight settled lines, every one `C.` (not
held). PC stays in the delay loop (`106C`, `1070`, `1074`,
`107C`, `1080`, `1084`). Mask `FFFFFFFFFF`, R5 `00000000`,
R9 `00000008`. Programmed steps are lane 1 `0007` and lane 0
`0009`, the same lock as step 5. Pattern 0 at the write-level
edge and the last pattern-0 read both came back `A55A`.
`F` is `AB`: pass set, not bad, lock set, `rclkpos=1`,
`rclksel=3`. A failed install would sit on `0x1D8C` or `0x1D90`
with the pin dark.

`measure_blink`, `roi=primer20k`, duration 30, warmup 2:

`blink-measure/20261106-041724-mcp`, status blinking, edge
0.32 Hz, FFT 0.312 Hz, trusted method edge, confidence 1.0,
cv 0.96, snr 94.0, 961 frames, 30.031 fps, 32 s. The expected
full blink is 0.320373 Hz. The same clip shows the Nano at
0.499 Hz.

Timing on that bitstream: 0 setup and 0 hold endpoints. `pclk`
Fmax is 98.031 MHz against the 96.749 MHz constraint. Worst
listed setup slack is +0.135 ns. `cpu_clk` is 24.187 MHz.

## Step 7

Step 6 is done on the Dock. Do not extend this image into step 7.
The next image is `FPGA_IMAGE=files` (`docs/hyperram/step7.md`),
HyperRAM first, then DDR3, same fail-closed LED. Start that on a
fresh agent.
