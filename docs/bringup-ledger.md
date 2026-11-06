# Bring-up ledger

Ranked cuts on the Nano 4K. Three passes (the Logger, the register-file read mux, and the shifter) produced five options. This is that ranking.

CLS is the scarce resource: about 2173/2304 used (95%), 131 free. The figures are from the `modules_n262144` synthesis tree and netlist.

The Logger, one register-file cut, and one shifter are different logic and can be stacked. The two register-file options are one mux, and the two shifter options are one barrel. Picking both of a pair counts that logic twice.

1. Omit the Logger on the 4K. Largest easy cut that leaves both blink laws alone: about 175 CLS, and 209 LUT plus 68 ALU (about 277 logic cells). Free CLS goes from 131 to about 306. Placed logic goes to about 80%. Easy. `103*N+142` and `576*N+788` stay as they are. The Dock training UART is a different block and stays. The trap is a shared generated wrapper: drop the Logger on the 4K elaboration only, and leave the Dock UART in place.

2. Cut the register file to a same-cycle 2-port read. The other easy cut that leaves the blink laws alone. All 16 registers stay, and the compiler does not change. About 128 CLS and 256 LUT3 (about 480 cells). Easy. No instruction reads three registers. The 27 MHz path still runs through a port that remains.

3. Time-multiplex a 1-port register file. This frees the most CLS and sits behind the easy cuts. About 256 CLS and 512 LUT3 (about 960 cells). Medium, because the pipeline has to hold PC and chainFix until the read commits. The skip loop becomes about `105*N+146`. The full blink is still about 0.49 Hz.

4. Replace the 5-stage barrel with a 1-bit-per-clock shifter. Smaller CLS return than the 1-port file, same kind of effort, and the blink slope is unchanged. About 110–150 CLS and 250–280 LUT (about 95% CLS down to about 89% if that CLS comes back). Medium. The 4K netlist elaborates only the slow shifter. chainFix has to treat a pending shift like a memory stall. The delay loop does not shift.

5. A 4-bit-per-clock shifter is last. The same medium change, for less area: about 90–120 CLS and 190–220 LUT. The blink slope is unchanged.

Among the easy cuts that keep both blink laws, omitting the Logger frees the most CLS.

## Item 1, measured

The Nano 4K elaboration of `CPUMinimalWrapper` does not build the Logger. `io_uart_tx` is an idle mark. `io_uart_rx` stays, so the board tops and the CST do not change. A DDR3 elaboration still builds the Logger. `ddr3_uart_tx` was not edited. Both blink laws are unchanged.

Verilator of the modules image, `FIRST_VALID` 13, before either load:

| N | cycles between edges | first edge |
|---:|---:|---:|
| 5 | 657 | 13120 |
| 6 | 760 | 13223 |
| 8 | 966 | 13429 |

Those edges are 13120, 13777, 14434, then 13223, 13983, 14743, then 13429, 14395, 15361. The period is still `103*N+142`. `tools/run_verilator_sim.sh` passes `InstrRom.v` into Verilator and reports six Blink2 edges at a mean of 84 cycles. `IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh` prints `PHY_SCORE pass`: period 3668, first edge 60074, PC `0000101c`, R5 `00000000`, R9 `00000000`, mask `ffffffffff`. That period is still `576*5+788`.

`modules_n262144` placed at 22:11 (Europe/Amsterdam). Logic 3845/4608 (84%; 3637 LUT and 208 ALU), CLS 2146/2304 (94%, 158 free), registers 1491/3612, 6/10 BSRAM. The packed design gave back 27 CLS. The pre-pack figure of about 175 CLS did not return as free slices. Slow corner 1.14 V 85 C on `clkdiv`: 302 setup endpoints, 0 hold, TNS -453.319, worst slack -4.984 ns, Fmax 23.797 MHz against 27.000 MHz. SRAM load was bus 3 address 081 only. Idcode `0x100981b`, GW1NSR-4C. CRC check success. Device 078 was not loaded.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/modules_n262144.fs
```

Webcam `measure_blink`, `roi=nano4k`, duration 20, warmup 2: `blink-measure/20261106-221634-mcp`, status blinking, edge 0.5 Hz, FFT 0.5 Hz, trusted method edge, confidence 1.0, 661 frames, 30.045 fps, `/dev/video2`. The expected full blink is 0.499982 Hz.

`ddr3modules_n262144` placed at 22:18 (Europe/Amsterdam). 0 setup and 0 hold endpoints. `pclk` Fmax 98.031 MHz against 96.749. SRAM load was bus 3 address 078 only. The Nano 4K was not opened for that load. UART on FTDI channel B, 115200 8N1, reopened after the load. The boot line is `..0080`. The settled lines are `C.` (not held). PC stays in the delay loop (`106C`, `1070`, `1074`, `107C`, `1080`, `1084`). Mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. Programmed steps are lane 1 `000C` and lane 0 `0009`. Pattern 0 at the write-level edge and the last pattern-0 read both came back `A55A`. `F` is `AB`.

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3modules_n262144.fs
```

`measure_blink`, `roi=primer20k`, duration 30, warmup 2: `blink-measure/20261106-222338-mcp`, status blinking, edge 0.32 Hz, FFT 0.312 Hz, trusted method edge, confidence 1.0, 962 frames, 30.062 fps. The expected full blink is 0.320373 Hz. The same clip shows the Nano at 0.499 Hz.

The next ledger item, if a later to-do does not fit, is item 2. It was not taken here.
