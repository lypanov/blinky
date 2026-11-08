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

## Item 2, measured

The register file is a same-cycle 2-port read. Port B is the `b` field, with no address mux in front of it, and it feeds the address adder and the ALU. Port X is `Ra` on a store and `Rc` otherwise. All 16 registers stay. The compiler does not change. Both blink laws stay: Blink2 is still 84 cycles, and the placed body is still `339*N+228` on the Nano and `1852*N+1252` pclk on the Dock.

`tools/run_verilator_sim.sh` reports six Blink2 edges at a mean of 84 cycles (98, 182, 266, 350, 434, 518). `IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh` prints `PHY_SCORE pass`: period 10512, first edge 306018, PC `0000101c`, R5 `00000000`, R9 `00000000`, mask `ffffffffff`. That period is `1852*5+1252`. No Micron `ERROR`.

The packed baseline on `e89073a` is logic 4481/4608, CLS 2292/2304, 12 free. `modules_n65536` placed at 13:52 (Europe/Amsterdam). Logic 4228/4608 (92%; 3954 LUT and 274 ALU), CLS 2260/2304 (99%, 44 free), registers 1820/3612, 8/10 BSRAM. Freed CLS is 32, from 12 free on that baseline to 44 free. Slow corner 1.14 V 85 C on `clkdiv`: 668 setup endpoints, 0 hold, worst slack −4.477 ns, Fmax 24.088 MHz against 27.000 MHz. The measured rate still matches. The SDC was not relaxed. SRAM load was bus 3 address 081 only.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/modules_n65536.fs
```

Webcam `measure_blink`, `roi=nano4k`, duration 20, warmup 2: `blink-measure/20261107-135604`, status blinking, edge 0.6058 Hz, FFT 0.590 Hz, trusted method edge, confidence 0.9965, 661 frames, 29.986 fps, 26 edges, `/dev/video2`. The expected full blink is 0.607645 Hz.

`place_option 2` on this netlist trained the Dock write eye to `G=FF00` (`F=EB`) and held at `0x1D8C`. `route_option 1` on that placement held at `0x1D90` with the same `G`. `gowin/primer20k/gowin_ddr3.tcl` now uses `place_option 0` and keeps `route_option 2`.

`ddr3modules_n65536` placed at 14:18 (Europe/Amsterdam). Logic 5563/20736 (27%; 5132 LUT and 431 ALU), CLS 3913/10368 (38%), registers 2562/16173, 6/46 BSRAM. 0 setup and 0 hold endpoints. `pclk` Fmax 106.793 MHz against 96.749, worst slack +0.972 ns. `cpu_clk` Fmax 37.065 MHz against 24.187. SRAM load was bus 3 address 078 only. The Nano 4K was not opened for that load. UART on FTDI channel B, 115200 8N1, reopened after the load. The settled lines are `C.` (not held). PC stays in the placed loop (`222C`, `2230`, `2234`, `2238`). Mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. Programmed steps are lane 1 `000C` and lane 0 `000A`. The last pattern-0 read is `A55A`. `F` is `AB`. The write-level edge sample is `FF5A`.

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3modules_n65536.fs
```

`measure_blink`, `roi=primer20k`, duration 30, warmup 2: `blink-measure/20261107-141912`, status blinking, edge 0.3983 Hz, FFT 0.405 Hz, trusted method edge, confidence 0.9978, 962 frames, 30.004 fps, `/dev/video2`. The expected full blink is 0.398561 Hz.

Item 3 was not taken.

## Block RAM (8 Nov 2026)

After Proof 7, block RAM is the wall on the Nano 4K: `modules_n65536` uses 10/10. `sim/link_inner.py` reports `ROM 3930/4096 stub 20 code 3549 init 149 sector 212`. The 4096-word instruction ROM is 8 blocks (512 words of 32 bits each). The inner core's code alone is 3549 words, so the ROM cannot shrink while the core runs from it. The way out is to keep the core on a "disk" and copy it into HyperRAM at boot, as the book does. Item B tests whether the board's external SPI flash can be that disk. Items A and C are space work on the way.

The Nano 4K has no distributed (LUT) RAM and its block RAM has no dual-port mode, so neither can take the register file. Registers stay in flip-flops.

### Item A — count every block RAM, remove the dead ones

Read the Gowin resource report for `modules_n65536` and write down what each of the 10 blocks is. Expected: 8 for `InstrRom`, the rest unknown.

One suspect is already known. `CPUMinimalWrapper` always builds `RAMController`, a demo that cycles a `Gowin_SP` block (`GowinSP`). Its outputs `io_deadbeef` and `io_addr` go to `unused_deadbeef` and `unused_addr` in `gowin/blinky_top_hyperram.v` and `gowin/primer20k/blinky_top_ddr3.v`. Remove `RAMController` from both elaborations (and the ports from both tops), unless the report shows Gowin already pruned it. Check the HyperRAM IP for blocks too, and remove anything else that drives nothing.

The CPU does not change, so both blink laws stay. Record block RAM, logic, and CLS before and after on both boards, then prove it as usual (sim, 4K webcam, Dock webcam). If nothing is dead, record the per-block list and stop. That list is still the result.

### Item B — external SPI flash pathfinder (Nano 4K only)

The question: can the Nano 4K design write the board's external NOR flash (32 Mbit, the WSON8 chip) and read it back after a fresh SRAM load? If it can, that chip becomes the 4K's disk, and the ROM can shrink to a boot loader.

This is a standalone pathfinder image, not the modules image. It needs no CPU: a small state machine is enough. Rules:

- Every bitstream is SRAM-loaded (`openFPGALoader ... -m`). Never use any openFPGALoader flash-writing option. The only writes to the NOR come from the FPGA design itself.
- Before writing anything, find in the Tang Nano 4K schematic and the GW1NSR-4C pinout which pins reach the NOR. Find out whether the FPGA configures from its own internal flash or from this chip. If the chip could hold a bitstream, write only the last 4 KB sector, and stop if anything suggests that overlaps a bitstream. If the pins are the MSPI configuration pins, Gowin has an option to use them as ordinary I/O after configuration. Find and record it.
- Use only standard SPI NOR commands: `9Fh` (JEDEC ID), `05h` (status), `06h` (write enable), `20h` (4 KB sector erase), `02h` (page program), `03h` (read).

Steps, each with its own blink rate published before loading:

1. Read-only. Read the JEDEC ID and blink at rate A if it is the expected part and size, dark otherwise. Record the ID.
2. Writer image. Erase the last 4 KB sector, program one 256-byte page with a known pattern that includes a per-build number, read it back, and blink at rate B if it matches.
3. Reader image, a separate SRAM load. Read the page and blink at rate C if the pattern and build number match, dark otherwise. A dark LED here is a real result: write it down.
4. Negative check. Load the reader built with a different build number. It must stay dark.

Simulate first with a simple SPI flash model. There is no Dock stage. The Dock has its own storage path, so say that in the write-up rather than skipping silently. A power-cycle check (unplug, replug, load the reader) needs a person and can be left for the morning.

### Item C — replace the pre-armed check mask with an arm word

On the `modules` and `ddr3modules` images, `checkMask` and `CheckTail` start all-ones at reset (`splitFetch`), because the image has no room for the forty zero stores. So today no self-check gates the LED. This item puts a real one back and removes the dead mask.

Hardware: on those two images, drop `checkMask`, `CheckTail`, and their store compares. Add one `armed` flip-flop, cleared by reset and set only by a word store of one exact 32-bit constant to one arm address. The LED is `ledState && armed`.

Software: before its delay loop, Blink5 (or the stub, whichever runs after `Modules.Load`) reads values that are known in advance: `MemLim`, `AllocPtr`, `root`, and the stack origin at 12, 16, 20, and 24, one `DIV` and `MOD` result, and a checksum of Blink5's own placed code that the linker computes. It combines their differences from the expected values into the stored word, so only all-correct values produce the constant. A skipped or wrong check stores a different word, and the LED stays dark. `ASSERT`s may be added as well, but the arm word is what gates the LED.

Proof: sim, 4K, and Dock, as usual. The extra instructions run before the loop, so only the first edge moves and the period formula stays. Also prove the negative: an image with one expected value deliberately wrong must stay dark in simulation, and on the 4K if time allows. Record the logic and CLS freed on the 4K.
