# Step 5: P/D fixups in DDR3

`FPGA_IMAGE=ddr3pd` is the Primer 20K image. The software is the
unfixed ROM and the device walk from `docs/hyperram/step5.md`.
`extraChecks` is 37. The pin stays dark unless that walk passes.
`FPGA_IMAGE=pdchain` stays the Nano 4K HyperRAM image.

The HyperRAM edge formula is not this board. Once the column is
right, `pclk/edge = 576*N+788`. N is 262144, so the full blink is
0.320373 Hz.

## Controller

`gowin/primer20k/ddr3/ddr3_controller.v` follows
nand2mario/ddr3-tang-primer-20k `a6d866d` (2023-07-25). NESTang's
last Primer 20K controller is `8b8f4fa` and does not subtract a
fixed write-level backoff. The local deltas are in
`gowin/primer20k/ddr3/NOTICE`.

Fixed `WLEVEL_BACKOFF` and absolute lane codes are not in this
image. After the read gate, the controller writes eight halfwords
and scans offsets -4..+12 from each lane's own write-level edge.
A point counts only when `dq_in[0]` matches the whole word. The
first row with three consecutive passes locks that lane-0 step and
the center of the lane-1 run. No pass leaves `read_calib_done` low.

Searching only downward from the edge never full-matched on this
Dock. At the edge, pattern 0 came back `A500`: the high byte
matched and the low byte was zero. Byte-wise centers were not a
joint full-word eye. The -4..+12 window is what locked.

## Simulation

`sim/run_ddr3_phy.sh` patches the vendor DQS cascade
(`sim/patch_prim_dqs.py`) and scores `PHY_SCORE pass` with no
Micron `ERROR`. This trainer locks steps 22/23 from model edges
26/26, `rclkpos=1`, `rclksel=3`, at cycle 1984. Those steps are the
model's wide eye, not the Dock pair. `sim/run_ddr3_cpu_phy.sh` on
the N=5 image also scores `PHY_SCORE pass`: period 3668, first edge
38574, PC `0000101c`, R5 `00000000`, R9 `00000008`, mask
`ffffffffff`.

## Nano 4K

`pdchain_n262144.fs` was SRAM-loaded on bus 3 address 081 only.
Webcam MCP `http://127.0.0.1:8766/mcp`, tool `measure_blink`,
`roi=nano4k`, duration 20, warmup 2:

`blink-measure/20261106-032517-mcp`, status blinking, 0.5 Hz,
edge, confidence 1.0. The same frame as the Dock proof below still
shows the Nano at 0.499 Hz.

## Dock

SRAM only, bus 3 address 078:

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3pd_n262144.fs
```

UART was already open on FTDI channel B (libftdi interface 2,
115200 8N1). The settled line is `C`, not held, PC in the delay
loop around the `0x108C` placeholder (`0x1064`..`0x109C`), mask
`FFFFFFFFFF`, R5 `00000000`, R9 `00000008`. Write-level edges were
lane 1 `000A` and lane 0 `000D`. The lock is lane 1 `0007` and
lane 0 `0009`. Pattern 0 at the first scan point read back `A55A`.
`rclkpos=1`, `rclksel=3`.

`measure_blink`, `roi=primer20k`, duration 30, warmup 2:

`blink-measure/20261106-034749-mcp`, status blinking, edge 0.321 Hz,
FFT 0.312 Hz, trusted method edge, confidence 1.0, cv 0.993,
snr 70.22, 962 frames, 32 s. The expected full blink is 0.320373 Hz.

Timing on that bitstream: 0 setup and 0 hold endpoints. `pclk`
Fmax is above the 96.749 MHz constraint.

## Step 6

Step 5 is done on the Dock. Do not extend this image into step 6.
The next image is `FPGA_IMAGE=moddesc` (`docs/hyperram/step6.md`),
HyperRAM first, then DDR3, same fail-closed LED.
