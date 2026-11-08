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

After Proof 7, block RAM is the wall on the Nano 4K: `modules_n65536` uses 10/10. `sim/link_inner.py` reports `ROM 3930/4096 stub 20 code 3549 init 149 sector 212`. The 4096-word instruction ROM is 8 blocks. Each block is a 4-bit pROM of all 4096 words (item A), not a 512-word slice of the 32-bit word. The inner core's code alone is 3549 words, so the ROM cannot shrink while the core runs from it. The way out is to keep the core on a "disk" and copy it into HyperRAM at boot, as the book does. Item B tests whether the board's external SPI flash can be that disk. Items A and C are space work on the way.

The Nano 4K has no distributed (LUT) RAM and its block RAM has no dual-port mode, so neither can take the register file. Registers stay in flip-flops.

### Item A — count every block RAM, remove the dead ones

Read the Gowin resource report for `modules_n65536` and write down what each of the 10 blocks is. Expected: 8 for `InstrRom`, the rest unknown.

One suspect is already known. `CPUMinimalWrapper` always builds `RAMController`, a demo that cycles a `Gowin_SP` block (`GowinSP`). Its outputs `io_deadbeef` and `io_addr` go to `unused_deadbeef` and `unused_addr` in `gowin/blinky_top_hyperram.v` and `gowin/primer20k/blinky_top_ddr3.v`. Remove `RAMController` from both elaborations (and the ports from both tops), unless the report shows Gowin already pruned it. Check the HyperRAM IP for blocks too, and remove anything else that drives nothing.

The CPU does not change, so both blink laws stay. Record block RAM, logic, and CLS before and after on both boards, then prove it as usual (sim, 4K webcam, Dock webcam). If nothing is dead, record the per-block list and stop. That list is still the result.

### Item A, measured

Nothing among the ten blocks is dead. The source is unchanged. Before and after are the same packs, because nothing was removed.

The Nano report is the Proof 7 `modules_n65536` place (`f92c3c2`). Logic 4004/4608 (87%; 3703 LUT and 301 ALU), CLS 2229/2304 (97%, 75 free), registers 1627/3456 FF, BSRAM 10/10: 8 pROM, 1 SDPB, 1 SDPX9B.

The eight pROMs are `InstrRom` `mem_mem_0_0_s` through `mem_mem_0_7_s`. Each has `BIT_WIDTH=4` and the Verilog address is `addr[11:0]`, so each block is one nibble of all 4096 words. Eight nibbles are the 32-bit instruction. The image uses 3930 of those words. The spare 166 words are padding inside every block, not a spare block. Shortening the ROM does not return a block while the word stays 32 bits.

The other two sit in `u_hpram`, the encrypted HyperRAM controller. One is SDPB and one is SDPX9B. The place timing path names one leaf: `u_hpram/u_hpram_top/matched_rvld[0].u_matched_rvld_fifo/data_mem_data_mem_0_0_s` at `BSRAM_R10[9]`, with `DI` driven from `rd_data_d`. The power report's other BSRAM-sized leaf is `u_hpram/u_hpram_top/u_hpram_wd/data_lane_gen[0].u_hpram_lane` (1.193 mW). The read-valid FIFO leaf is 1.148 mW. The instruction ROM is 0.344 mW. Those three sit next to the 2.668 mW BSRAM total; the small gap is the logic inside the same leaves. The FIFO is on the live read path and the lane is the live data path. Synthesis did not sweep either. The controller source is encrypted, so neither block can be lifted out.

`RAMController` and its `Gowin_SP` are not among the ten. Synthesis warns NL0002 and sweeps both, on this image and on `ddr3modules_n65536`. The outputs already go to `unused_deadbeef` and `unused_addr`, so the block was gone before this item. It stays in the source. `SpiSector` is flip-flops and uses no block. `CheckTail` is swept on the Nano and is not a block. It stays. That cut is item C.

The Dock report is the same image, `ddr3modules_n65536`. Logic 5257/20736 (26%; 4797 LUT and 460 ALU), CLS 3625/10368 (35%, 6743 free), BSRAM 8/46, all eight the instruction pROM. The Dock has no HyperRAM, so the two controller blocks are absent. `RAMController` is swept here too.

The CPU is unchanged, so both blink laws stay the Proof 7 laws. This item did not re-simulate and did not reload either board. The standing Nano clip is `/home/lypanov/fpga/blink-measure/20261108-nano-modules/clip.mkv`, edge 0.430473 Hz, against 0.4459 Hz at 27 MHz. The standing Dock clip is `/home/lypanov/fpga/blink-measure/20261108-dock-eye/clip.mkv`, edge 0.397984 Hz, against 0.3995 Hz.

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

### Item B, measured

The external NOR can be the 4K's disk. A fresh SRAM load read back the page the previous image had written. The Dock was not loaded. Its storage path is the DDR3 image, and this pathfinder does not use it. A power-cycle of the reader is left for the morning. `oberon/src/Modules.Mod` was not edited.

The chip is the Puya P25Q32 on schematic `Tang_Nano_4K_3603` (WSON-8, 32 Mbit, 4 MiB). The GW1NSR-4C QN48P pinout and that schematic put it on the MSPI pins:

| Flash | FPGA pin | Config name | Net |
|---|---|---|---|
| CLK | 1 | IOT10A/MCLK | `MSPI_CLK`, 1 kΩ series R39 |
| CS# | 2 | IOT10B/MCS_N | `MSPI_CS`, 4.7 kΩ pull-up R35 |
| SI | 48 | IOT11A/MO | `MSPI_DI` |
| SO | 47 | IOT11B/MI | `MSPI_DO` |
| WP# | 8 | IOT4B/JTAGSEL_N | `MSPI_WP`, 4.7 kΩ pull-up R37, driven high |
| HOLD# | 9 | IOT5B/DONE | `MSPI_HOLD`, 4.7 kΩ pull-up, driven high |

Pin 10 is IOT7A/MODE1 and IOT7B/MODE2 bonded together, and it is the user LED (anode, R32 330 Ω). UG292 gives GW1NSR-4C QN48P JTAG, AUTO BOOT, MSPI, and DUAL BOOT. MODE `000` is AUTO BOOT from internal flash. MODE `110` is DUAL BOOT. With MODE1 and MODE2 tied, the board can select those two and not MSPI alone (`010`). The strap rests low, so power-up configures from the internal flash. The external chip can hold a bitstream only if pin 10 is high when configuration is sampled, and Gowin reads that image from address 0.

A `modules_n65536.fs` for this part is 1,772,222 bytes. The last 4 KB sector starts at byte 4,190,208 (`0x3FF000`). The gap under a bitstream at address 0 is 2,417,986 bytes. The pathfinder erases that sector and programs only its first 256-byte page. Nothing in the size or the boot address suggests the page overlaps a bitstream.

The MSPI pins are configuration pins. After SRAM configuration they are ordinary I/O when the project sets "Use MSPI as Regular IO" (`set_option -use_mspi_as_gpio 1`). HOLD# is the DONE pin, so "Use DONE as Regular IO" is on as well. JTAG stays the SRAM-load port.

The image is a state machine, not the modules CPU. SPI is mode 0 at 250 kHz. The only commands are `9Fh`, `05h`, `06h`, `20h`, `02h`, and `03h`. The page pattern is `A5 5A`, then the build byte, then `i xor build`. The build byte is `7Bh`. The negative reader is the same reader with `7Ch`. The LED is active high and stays low unless the check passes. Rates, fixed before any load, at the 27 MHz PLLVR bypass:

| Check | Half-period | Rate |
|---|---:|---:|
| A, JEDEC `85 60 16` | 9,000,000 | 1.5 Hz |
| B, erase, program, read-back | 5,400,000 | 2.5 Hz |
| C, fresh SRAM load reads the page | 3,375,000 | 4.0 Hz |

`sim/run_spi_flash_pathfinder.sh` (Icarus, a 4 KB NOR model, no DDR3) prints `SPI_FLASH PASS all`. The ID image blinks on `85 60 16`. A model that answers `EF 40 16` stays dark and does not erase. A reader of a blank page stays dark. The writer erases `0x3FF000` once, programs 256 bytes, and blinks. A second reader instance on that same array blinks. Build `7Ch` stays dark.

The place runs were at 03:38 (Europe/Amsterdam). BSRAM is 0/10 (synthesis of `spi_neg`; the place tables list no block). Each image is 149 FF.

| Image | Logic | CLS | Free CLS |
|---|---|---|---:|
| `spi_id` | 314/4608 (272 LUT, 42 ALU) | 188/2304 | 2116 |
| `spi_write` | 309/4608 (267 LUT, 42 ALU) | 186/2304 | 2118 |
| `spi_read` | 308/4608 (266 LUT, 42 ALU) | 185/2304 | 2119 |
| `spi_neg` | 312/4608 (270 LUT, 42 ALU) | 187/2304 | 2117 |

SRAM loads were bus 3 address 081 only. Idcode `0x100981b`, GW1NSR-4C. Each load printed `write to ram` and `CRC check: Success`. No flash-writing flag was passed. The Primer was not opened.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_id.fs
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_write.fs
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_read.fs
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_neg.fs
```

Webcam `measure_blink`, `/dev/video2`, `roi=nano4k`, duration 20, warmup 2. The analyzer's Blink3 "expected" field is not this pathfinder's rate.

| Check | Edge | FFT | Edges | Confidence | Clip |
|---|---:|---:|---:|---:|---|
| A | 1.499438 Hz | 1.497 Hz | 66 | 1.0 | `/home/lypanov/fpga/blink-measure/20261108-spi-id/clip.mkv` |
| B | 2.495420 Hz | 2.495 Hz | 110 | 0.9961 | `/home/lypanov/fpga/blink-measure/20261108-spi-write/clip.mkv` |
| C | 3.995439 Hz | 3.992 Hz | 176 | 0.9767 | `/home/lypanov/fpga/blink-measure/20261108-spi-read/clip.mkv` |

Rate A is the JEDEC record: the image blinks only for `85 60 16`, and the board blinked at 1.5 Hz. That is Puya, type `60h`, capacity `16h` (32 Mbit). Rate B means the erase, the page program, and the read-back matched. Rate C is a separate SRAM load, so the page was still in the NOR.

The negative load used the same camera box as the lit LED (`268,240`, 30×24) so the detector would not hunt another lamp. In the three blink clips that box peaks near 62 and averages about 31. On the negative image it peaks at 0.644 and averages 0.189. The tool's headline 7.11 Hz has confidence 0.35, FFT SNR 2.9, and the warning that the on/off gap is small. That is the noise floor. The LED stayed dark. Clip: `/home/lypanov/fpga/blink-measure/20261108-spi-neg/clip.mkv`.

### Item C — replace the pre-armed check mask with an arm word

On the `modules` and `ddr3modules` images, `checkMask` and `CheckTail` start all-ones at reset (`splitFetch`), because the image has no room for the forty zero stores. So today no self-check gates the LED. This item puts a real one back and removes the dead mask.

Hardware: on those two images, drop `checkMask`, `CheckTail`, and their store compares. Add one `armed` flip-flop, cleared by reset and set only by a word store of one exact 32-bit constant to one arm address. The LED is `ledState && armed`.

Software: before its delay loop, Blink5 (or the stub, whichever runs after `Modules.Load`) reads values that are known in advance: `MemLim`, `AllocPtr`, `root`, and the stack origin at 12, 16, 20, and 24, one `DIV` and `MOD` result, and a checksum of Blink5's own placed code that the linker computes. It combines their differences from the expected values into the stored word, so only all-correct values produce the constant. A skipped or wrong check stores a different word, and the LED stays dark. `ASSERT`s may be added as well, but the arm word is what gates the LED.

Proof: sim, 4K, and Dock, as usual. The extra instructions run before the loop, so only the first edge moves and the period formula stays. Also prove the negative: an image with one expected value deliberately wrong must stay dark in simulation, and on the 4K if time allows. Record the logic and CLS freed on the 4K.

### Item C, measured

The LED on `modules` and `ddr3modules` arms only when a word store of `0xA11C0DE5` lands at `0x7C0`. `checkMask` and `CheckTail` are gone on those two images. One flip-flop starts clear. The pin is `ledState && armed`, and `dbgMask` is `40'hffffffffff` once that store hits and zero until then. Every other image keeps the zero-store mask. `oberon/src/Modules.Mod` was not edited.

`sim/link_inner.py` appends the arm sequence after Blink5's compiled body and points the entry at it, so the sequence runs once, before the delay loop. It folds the differences of the words at 12, 16, 20, and 24 (`MemLim` `0x14000`, `AllocPtr` `0x2000`, root `0x161A0`, stack `0xC000`), checks that 58 DIV 29 is 2 and that the remainder in H is 0, and sums Blink5's placed code words against the sum planted at address 28. The store is `0xA11C0DE5` xor that OR. The delay loop in `tests/Blink5.Mod` is unchanged (`maxIterations := 65536`). The same N=65536 image was SRAM-loaded on both boards. Simulation patches that delay to 5.

Verilator of the N=5 image reaches edges at 3291119, 3294027, and 3296935. Both periods are 2908, which is `462*5+598`. Edge PC `0x2070`, R5 0, R9 0, mask `0xffffffffff`. The prologue sits before that loop, so the CPU-cycle law is unchanged. `--break-arm` plants `code_sum+1` at address 28: 0 LED edges in 5,000,000 cycles, LED still 0, PC `0x2224` inside the delay loop. Blink2 is unchanged: six edges, mean 84.00, cycles 98, 182, 266, 350, 434, 518.

`IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh +max_pclk=12000000` prints `PHY_SCORE pass` and exits 0. Calibration is `wstep=1a/1a`, `run=16/17`, `rclkpos=1`, `rclksel=3`, at cycle 1984. Three edges, at pclk 9936550, 9948222, and 9959894. Both intervals are 11672. Edge PC `00002070`, R5 0, R9 0, mask `ffffffffff`, 74969 reads, no Micron `ERROR`. The bench counts pclk and the CPU clock is pclk/4, so a stall-free copy of the 2908-cycle edge is 11632 pclk. The measured edge is `4*(462*5+598)+40`. The constant this bench used to require, 10512, is `1852*5+1252`, the body at PC `0x101c`. The arm store is before the first edge. At N=65536 those extra 40 pclk are under a microsecond, so the Dock rate stays the Proof 7 law: 30278230 CPU cycles at 24.187 MHz, a full blink of 0.3995 Hz.

The Nano place is 06:00 (`modules_n65536`). Logic 3967/4608 (87%; 3666 LUT, 301 ALU), was 4004/4608 (3703 LUT, 301 ALU). CLS 2173/2304 (95%, 131 free), was 2229/2304 (75 free). That is 37 logic and 56 CLS back. Registers 1629 FF, was 1627. BSRAM 10/10. Clock Fmax 101.066 MHz at the 27 MHz constraint (level 8), HyperRAM clkdiv 64.987 MHz (level 6), cpu_div 18.244 MHz at 13.5 MHz (level 20). Setup TNS 0.000, 0 endpoints.

Webcam `measure_blink`, `roi=nano4k`, duration 22, warmup 2: `/home/lypanov/fpga/blink-measure/20261108-arm-nano`, status blinking, edge 0.429982 Hz, period 2.325678 s, 19 edges, duty 0.487, FFT 0.408 Hz, SNR 320, confidence 0.9978, 661 frames, 29.991 fps, ROI `268,240` 30×23. The Proof 7 law at 27 MHz is 0.4459 Hz. This is the same 3.7% slow as the standing modules clip (0.430473 Hz). Clip: `/home/lypanov/fpga/blink-measure/20261108-arm-nano/clip.mkv`.

The Dock netlist does not train with `route_option` 2. That place leaves a one-point eye (best pop 16, no 3-wide window), holds the CPU at `0x0080`, and reports F `4B`. `place_option` 0 with `route_option` 1 trains it. `tools/gowin_build.sh` sets `DDR3_ROUTE_OPTION=1` for `ddr3modules` only. Other DDR3 images stay on `route_option` 2. The loaded bitstream is that route, placed 13:14.

The Dock place: logic 5200/20736 (26%; 4740 LUT, 460 ALU), was 5257 (4797 LUT, 460 ALU). CLS 3612/10368 (35%, 6756 free), was 3625 (6743 free). BSRAM 8/46. pclk Fmax 101.713 MHz at 96.749 MHz (level 13), cpu_clk Fmax 39.930 MHz at 24.187 MHz (level 20). Setup TNS 0.000, 0 endpoints.

SRAM load, bus 3 address 078 only, no flash flag:

```bash
openFPGALoader --busdev-num 003:078 -b tangprimer20k -m \
  gowin/primer20k/impl/pnr/ddr3modules_n65536.fs
```

UART is FTDI channel B of that device, 115200 8N1, purged after the load. 82 of 82 lines are `C.` with mask `FFFFFFFFFF`, R5 0, R9 0, G `A55A`, F `AB`. Sixty-eight lines are steps `000D`/`0002`, E0 `A55A`, C0 `01`, C1 `0F`. The last fourteen snap to steps `000C`/`0003`, E0 `FF5A`, C0 `02`, C1 `0D`, still G `A55A` and F `AB`, with PC in the delay loop. One line:

```
C.222C FFFFFFFFFF 00000000 00001117 000080D0 000010F9 00000000 00000000 000D 0002 E0 A55A G A55A C0 01 C1 0F BO 10 F AB
```

Webcam `measure_blink`, `roi=primer20k`, duration 32, warmup 2, filmed after that capture: `/home/lypanov/fpga/blink-measure/20261108-arm-dock`, status blinking, edge 0.397817 Hz, period 2.513717 s, 26 edges, duty 0.514, FFT 0.405 Hz, SNR 440, confidence 0.9977, 962 frames, 30.002 fps, ROI `328,71` 26×29. Against 0.3995 Hz that is the same match as the Proof 7 Dock clip (0.397984 Hz). Clip: `/home/lypanov/fpga/blink-measure/20261108-arm-dock/clip.mkv`.

## The flash disk (decided 8 Nov 2026)

Item B showed the Nano 4K design can use its external NOR. The maintainer has narrowed the flash rule for this one use (see `AGENTS.md`, "Loading boards"): openFPGALoader may write a data file to the 4K's external NOR, inside `0x200000`–`0x3FFFFF`, and nothing else. A `modules_n65536.fs` is about 1.77 MB, so a bitstream at address 0 would end below `0x200000`. The board boots from its internal flash in any case.

The plan: an image builder on the host makes the disk, openFPGALoader writes it, and the 4K's ROM shrinks to a bootstrap that copies the inner core from the disk into HyperRAM and runs it there. This is the book's boot path, with the NOR as the disk. It is also scaffolding step B (the core runs from memory), and it is how the 4K gets its block RAM back. The Dock is not part of D or E. It has room, and its disk will be the SD card later.

Item C (the arm word) comes first, so that a wrong or stale disk keeps the LED dark.

### Item D — the disk image builder, and the host writes the disk

Builder: a new `tools/build_disk_image.py` that reuses `sim/link_inner.py`'s layout and writes `disk.bin`. The image starts with a header: a magic word, a format version, a build number, the length, and a checksum over everything after the header. After the header come the inner core image (the code and the initial data the stub copies today), then the sector pages the core reads through `SpiSector` (today's directory, `AMemoryMappedToggle.rsc` and `Blink5.rsc`). Write the layout down in this section. Item E's bootstrap and the sector reader both depend on it.

Find the openFPGALoader options that write a raw data file to the Nano 4K's external flash at an offset, and that read it back. Record the exact commands. If openFPGALoader cannot reach this board's external flash, stop and record why. The fallback is an installer bitstream that holds the image in its ROM and writes it from the design, which item B already proved. Name that fallback, but do not build it in this item.

Write `disk.bin` at `0x200000`. Read it back on the host and compare. Then the LED proof: a pathfinder-style reader image, SRAM-loaded, reads the header, checks the magic and the build number, and checksums the whole image. It blinks at a rate published beforehand, and stays dark otherwise. The negative: a reader expecting a different build number stays dark. Simulate the reader first against the SPI flash model loaded with the same `disk.bin`.

### Item E — boot the 4K from the flash disk

The 4K ROM holds only a bootstrap, about one block. It reads the header from `0x200000`, checks the magic, the build number and the checksum, copies the core into HyperRAM, and branches to the `Modules` body, as the book's boot loader does. From then on every instruction is fetched from HyperRAM: the core translation (`CoreMap` `coreRom`/`coreBase`, `holdForCode`) is not elaborated in this image. `SpiSector` reads sectors from the NOR instead of from the ROM.

The checksum result also feeds item C's arm word. A stale or damaged disk leaves the LED dark.

Blink law: Blink5's loop already runs from HyperRAM, so the period formula should be unchanged, and only the first edge moves (the SPI copy at boot). Compute both before the board is trusted. Record ROM words and block RAM before and after. The expectation is the ROM going from 4096 words to 512 or fewer, and block RAM from 10/10 to about 3/10. Prove it in sim (the SPI flash model loaded with `disk.bin`), then on the 4K. No Dock stage, and say so in the write-up.
