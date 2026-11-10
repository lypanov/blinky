# Bring-up ledger

The Nano 4K space list, and a record of the work that got the 4K its room. One numbered list, like `docs/todo.md`. Each item says whether it is done or open. Results are in the "Item N, measured" sections below, in number order.

**When a to-do does not fit on the Nano 4K:** take the open items, lowest number first. Items marked "later" are not taken unless the maintainer says so.

Items 4–8 were lettered A–E until 9 Nov 2026. Older text, including the measured sections, still uses the letters. Item 9 was 4 and item 10 was 5.

CLS is the scarce resource on the 4K. After item 3 and the HDMI square (`docs/hdmi.md`, step 2), the 4K place is CLS 2161/2304 (143 free), block RAM 4/10. Estimates below came from the netlists of their day; re-measure before relying on one.

1. Omit the Logger on the 4K. Done. About 175 CLS. The Dock training UART is a different block and stays.

2. Cut the register file to a same-cycle 2-port read. Done. 32 CLS measured. All 16 registers stay, and the compiler does not change.

3. Time-multiplex a 1-port register file. Done. 43 CLS measured on the flash-boot image. The blink law became `466*N+606`.

4. Count every block RAM and remove the dead ones. Done. Nothing was dead: 8 pROM for the instruction ROM, 2 inside the encrypted HyperRAM controller.

5. External SPI flash pathfinder. Done. The 4K design can write its Puya P25Q32 NOR and read it back after a fresh SRAM load.

6. Replace the pre-armed check mask with an arm word. Done. The LED arms only when Blink5 stores a word computed from its checks.

7. The disk image builder, and the host writes the 4K's flash disk. Done. `tools/build_disk_image.py` and openFPGALoader, inside `0x200000`–`0x3FFFFF`.

8. Boot the 4K from the flash disk. Done. The ROM is a 102-word bootstrap. Block RAM went from 10/10 to 3/10.

9. Replace the 5-stage barrel with a 1-bit-per-clock shifter. Smaller CLS return than the 1-port file, same kind of effort, and the blink slope is unchanged. About 110–150 CLS and 250–280 LUT (about 95% CLS down to about 89% if that CLS comes back). Medium. The 4K netlist elaborates only the slow shifter. A pending shift stalls the same way a memory access does. The patch table is gone. The delay loop does not shift. Open.

10. A 4-bit-per-clock shifter is last. The same medium change, for less area: about 90–120 CLS and 190–220 LUT. The blink slope is unchanged. Open.

11. Retire the old step images from the CPU. Done. The work is `docs/todo.md` item 23. The 0x10/0x50 LED snoop, the patch table, the single fetch at 0x1F00, the zero-store checks, and the ROM address translation are gone. The measured saving is below.

12. Shifts on the hardware multipliers. Open, after `MUL` (`docs/todo.md` item 27). The GW1NSR-4C has 16 unused 18×18 multipliers. One 32×32→64 unsigned multiply does all three shifts: left by n is the low word of `x × 2ⁿ`, right by n is the high word of `x × 2³²⁻ⁿ`, rotate is the two ORed, and an arithmetic right shift inverts, shifts, and inverts back for negative x. A small table turns n into 2ⁿ. Replaces the 5-stage barrel. Estimate 60–100 CLS net. An alternative to 9 and 10.

13. A 24-bit PC and address path. Open. Wirth's own RISC5 does this. The PC, the branch adders, and the address compares shrink from 32 to 24 bits. I/O stays at the top of the address space, decoded from the top bits as in the book. The compiler does not change. Estimate 20–40 CLS.

14. `DIV` in Oberon on the 4K. Open. Remove the hardware divider from the 4K build. `DIV` traps to a short Oberon routine that divides in software. The `.rsc` files stay the same on both boards: the Dock keeps its hardware divider. Slower division on the 4K only. The delay loop does not divide.

15. Sweep Gowin's synthesis and place-and-route settings. Later. A script tries placement, packing, and resource-sharing settings and records CLS. No design risk, but the gain is unknown.

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

## Item 3, measured

The register file has one read port. All 16 registers stay. A store, and an F0 op other than MOV H, reads twice: the first cycle latches Rb and holds PC, and the commit cycle reads Ra or Rc. chainFix does not overlay the next instruction until that commit. The instruction ROM is synchronous, so the held word is written back through the ROM overlay. A sector scan can still take the ROM. The body stays ready across the extra cycle.

The period was fixed before either board was trusted. Verilator of the flash-boot modules image, on the bridge clock, gives edges at PC `0x2070`, mask `ffffffffff`, R5 0, R9 0, not halted:

| N | period | edges |
| --- | --- | --- |
| 5 | 2936 | 12382736, 12385672, 12388608 |
| 6 | 3402 | 12383202, 12386604, 12390006 |
| 8 | 4334 | 12384134, 12388468, 12392802 |

That is `466*N+606`. The previous law was `462*N+598`. The skip iteration gained 4 bridge cycles and the toggle gained 12, which is the half-clock form of the old `105*N+146` guess. For `N=65536` the edge is 30,540,382 cycles. At 27 MHz that is an edge every 1.131125 s, a full blink of 0.442038 Hz. At the Dock's 24.187 MHz the same count is 0.395984 Hz.

The Blink2 mill image, block RAM, N=5, is not this law. Its edges are 117, 97, 97. The steady edge is 97 (four skips of 17 and one toggle of 29). The three-sample average is 103, was 89.

The N=65536 disk is the one already on the NOR: checksum `0x8A0987D4`, arm word `0x2B158A31`, 17928 bytes. Nothing was written to flash.

The Nano place at 16:42 (Europe/Amsterdam), `modules_n65536`. Logic 3648/4608 (80%; 3351 LUT, 297 ALU), was 3871/4608 on the item E place. Registers 1889/3612 (1884 FF), was 1791. CLS 2121/2304 (93%, 183 free), was 2164/2304 (140 free). BSRAM 3/10. `cpu_clk` Fmax 15.931 MHz against 13.500 (level 24). Setup TNS 0.000, 0 endpoints, worst slack +2.597 ns. SRAM load was bus 3 address 081 only. `write to ram`, CRC check Success. Device 078 was not opened for that load.

The auto `roi=nano4k` box missed the LED. The same clip, manual box `290,190` 50×50 on the LED: edge 0.427067 Hz, FFT 0.416 Hz, confidence 0.9979, 20 edges, duty 0.515. Against 0.442038 Hz that is the same slow fraction as item E (0.431/0.4459). The LED was not dark. Clip: `/home/lypanov/fpga/blink-measure/20261109-164355/clip.mkv`.

The Dock place of the same netlist with `route_option 1` fits. Logic 5112/20736 (25%; 4652 LUT, 460 ALU), CLS 3541/10368 (35%), registers 2302, BSRAM 8/46. `pclk` Fmax 100.444 MHz against 96.749, worst slack +0.380 ns. `cpu_clk` Fmax 30.038 MHz against 24.187. Setup and hold TNS 0.000. SRAM load was bus 3 address 078 only. The user LED stayed dark. The training UART, FTDI channel B, 115200 8N1, stayed on `..0080` with F `4B`, G `0000`, E0 `FFFF`. That is the route that holds the CPU, not a DDR3 protocol failure. The Micron bench was not run through the LED edges. It had already calibrated (`done=1` at pclk 1984, wstep `1a/1a`) and was stopped there.

`route_option 2` of that same netlist placed at 17:01 (Europe/Amsterdam). Logic, CLS, registers, and BSRAM are unchanged. `pclk` Fmax 109.125 MHz against 96.749, worst slack +1.172 ns. `cpu_clk` Fmax 29.414 MHz against 24.187 (level 25). Setup TNS 0.000, 0 endpoints. SRAM load was bus 3 address 078 only, `write to ram`. The Nano was not opened for that load.

Webcam `/dev/video2`, duration 32, warmup 4, manual box `296,28` 40×40 on the upper LED. Edge 0.396158 Hz, FFT 0.382 Hz, confidence 0.998, 27 edges, duty 0.505. Against 0.395984 Hz the edge is 0.04% high. In the same clip the Nano LED is 0.427 Hz, so the two boards are not the same spot. The LED was not dark. Clip: `/home/lypanov/fpga/blink-measure/20261109-1702-dock-r2/clip.mkv`. The training UART on this image still printed `..0080` with F `4B`. The user LED is the measurement. `tools/gowin_build.sh` now defaults the modules Dock image to `route_option 2`.

## Items 4–6: block RAM (8 Nov 2026)

After Proof 7, block RAM is the wall on the Nano 4K: `modules_n65536` uses 10/10. `sim/link_inner.py` reports `ROM 3930/4096 stub 20 code 3549 init 149 sector 212`. The 4096-word instruction ROM is 8 blocks. Each block is a 4-bit pROM of all 4096 words (item A), not a 512-word slice of the 32-bit word. The inner core's code alone is 3549 words, so the ROM cannot shrink while the core runs from it. The way out is to keep the core on a "disk" and copy it into HyperRAM at boot, as the book does. Item B tests whether the board's external SPI flash can be that disk. Items A and C are space work on the way.

The Nano 4K has no distributed (LUT) RAM and its block RAM has no dual-port mode, so neither can take the register file. Registers stay in flip-flops.

### Item 4 (was A) — count every block RAM, remove the dead ones

Read the Gowin resource report for `modules_n65536` and write down what each of the 10 blocks is. Expected: 8 for `InstrRom`, the rest unknown.

One suspect is already known. `CPUMinimalWrapper` always builds `RAMController`, a demo that cycles a `Gowin_SP` block (`GowinSP`). Its outputs `io_deadbeef` and `io_addr` go to `unused_deadbeef` and `unused_addr` in `gowin/blinky_top_hyperram.v` and `gowin/primer20k/blinky_top_ddr3.v`. Remove `RAMController` from both elaborations (and the ports from both tops), unless the report shows Gowin already pruned it. Check the HyperRAM IP for blocks too, and remove anything else that drives nothing.

The CPU does not change, so both blink laws stay. Record block RAM, logic, and CLS before and after on both boards, then prove it as usual (sim, 4K webcam, Dock webcam). If nothing is dead, record the per-block list and stop. That list is still the result.

### Item 4, measured

Nothing among the ten blocks is dead. The source is unchanged. Before and after are the same packs, because nothing was removed.

The Nano report is the Proof 7 `modules_n65536` place (`f92c3c2`). Logic 4004/4608 (87%; 3703 LUT and 301 ALU), CLS 2229/2304 (97%, 75 free), registers 1627/3456 FF, BSRAM 10/10: 8 pROM, 1 SDPB, 1 SDPX9B.

The eight pROMs are `InstrRom` `mem_mem_0_0_s` through `mem_mem_0_7_s`. Each has `BIT_WIDTH=4` and the Verilog address is `addr[11:0]`, so each block is one nibble of all 4096 words. Eight nibbles are the 32-bit instruction. The image uses 3930 of those words. The spare 166 words are padding inside every block, not a spare block. Shortening the ROM does not return a block while the word stays 32 bits.

The other two sit in `u_hpram`, the encrypted HyperRAM controller. One is SDPB and one is SDPX9B. The place timing path names one leaf: `u_hpram/u_hpram_top/matched_rvld[0].u_matched_rvld_fifo/data_mem_data_mem_0_0_s` at `BSRAM_R10[9]`, with `DI` driven from `rd_data_d`. The power report's other BSRAM-sized leaf is `u_hpram/u_hpram_top/u_hpram_wd/data_lane_gen[0].u_hpram_lane` (1.193 mW). The read-valid FIFO leaf is 1.148 mW. The instruction ROM is 0.344 mW. Those three sit next to the 2.668 mW BSRAM total; the small gap is the logic inside the same leaves. The FIFO is on the live read path and the lane is the live data path. Synthesis did not sweep either. The controller source is encrypted, so neither block can be lifted out.

`RAMController` and its `Gowin_SP` are not among the ten. Synthesis warns NL0002 and sweeps both, on this image and on `ddr3modules_n65536`. The outputs already go to `unused_deadbeef` and `unused_addr`, so the block was gone before this item. It stays in the source. `SpiSector` is flip-flops and uses no block. `CheckTail` is swept on the Nano and is not a block. It stays. That cut is item C.

The Dock report is the same image, `ddr3modules_n65536`. Logic 5257/20736 (26%; 4797 LUT and 460 ALU), CLS 3625/10368 (35%, 6743 free), BSRAM 8/46, all eight the instruction pROM. The Dock has no HyperRAM, so the two controller blocks are absent. `RAMController` is swept here too.

The CPU is unchanged, so both blink laws stay the Proof 7 laws. This item did not re-simulate and did not reload either board. The standing Nano clip is `/home/lypanov/fpga/blink-measure/20261108-nano-modules/clip.mkv`, edge 0.430473 Hz, against 0.4459 Hz at 27 MHz. The standing Dock clip is `/home/lypanov/fpga/blink-measure/20261108-dock-eye/clip.mkv`, edge 0.397984 Hz, against 0.3995 Hz.

### Item 5 (was B) — external SPI flash pathfinder (Nano 4K only)

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

### Item 5, measured

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

### Item 6 (was C) — replace the pre-armed check mask with an arm word

On the `modules` and `ddr3modules` images, `checkMask` and `CheckTail` start all-ones at reset (`splitFetch`), because the image has no room for the forty zero stores. So today no self-check gates the LED. This item puts a real one back and removes the dead mask.

Hardware: on those two images, drop `checkMask`, `CheckTail`, and their store compares. Add one `armed` flip-flop, cleared by reset and set only by a word store of one exact 32-bit constant to one arm address. The LED is `ledState && armed`.

Software: before its delay loop, Blink5 (or the stub, whichever runs after `Modules.Load`) reads values that are known in advance: `MemLim`, `AllocPtr`, `root`, and the stack origin at 12, 16, 20, and 24, one `DIV` and `MOD` result, and a checksum of Blink5's own placed code that the linker computes. It combines their differences from the expected values into the stored word, so only all-correct values produce the constant. A skipped or wrong check stores a different word, and the LED stays dark. `ASSERT`s may be added as well, but the arm word is what gates the LED.

Proof: sim, 4K, and Dock, as usual. The extra instructions run before the loop, so only the first edge moves and the period formula stays. Also prove the negative: an image with one expected value deliberately wrong must stay dark in simulation, and on the 4K if time allows. Record the logic and CLS freed on the 4K.

### Item 6, measured

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

## Items 7–8: the flash disk (decided 8 Nov 2026)

Item B showed the Nano 4K design can use its external NOR. The maintainer has narrowed the flash rule for this one use (see `AGENTS.md`, "Loading boards"): openFPGALoader may write a data file to the 4K's external NOR, inside `0x200000`–`0x3FFFFF`, and nothing else. A `modules_n65536.fs` is about 1.77 MB, so a bitstream at address 0 would end below `0x200000`. The board boots from its internal flash in any case.

The plan: an image builder on the host makes the disk, openFPGALoader writes it, and the 4K's ROM shrinks to a bootstrap that copies the inner core from the disk into HyperRAM and runs it there. This is the book's boot path, with the NOR as the disk. It is also scaffolding step B (the core runs from memory), and it is how the 4K gets its block RAM back. The Dock is not part of D or E. It has room, and its disk will be the SD card later.

Item C (the arm word) comes first, so that a wrong or stale disk keeps the LED dark.

### Item 7 (was D) — the disk image builder, and the host writes the disk

Builder: a new `tools/build_disk_image.py` that reuses `sim/link_inner.py`'s layout and writes `disk.bin`. The image starts with a header: a magic word, a format version, a build number, the length, and a checksum over everything after the header. After the header come the inner core image (the code and the initial data the stub copies today), then the sector pages the core reads through `SpiSector` (today's directory, `AMemoryMappedToggle.rsc` and `Blink5.rsc`). Write the layout down in this section. Item E's bootstrap and the sector reader both depend on it.

Find the openFPGALoader options that write a raw data file to the Nano 4K's external flash at an offset, and that read it back. Record the exact commands. If openFPGALoader cannot reach this board's external flash, stop and record why. The fallback is an installer bitstream that holds the image in its ROM and writes it from the design, which item B already proved. Name that fallback, but do not build it in this item.

Write `disk.bin` at `0x200000`. Read it back on the host and compare. Then the LED proof: a pathfinder-style reader image, SRAM-loaded, reads the header, checks the magic and the build number, and checksums the whole image. It blinks at a rate published beforehand, and stays dark otherwise. The negative: a reader expecting a different build number stays dark. Simulate the reader first against the SPI flash model loaded with the same `disk.bin`.

Layout, little-endian. The file is the bytes at flash `0x200000`. `tools/build_disk_image.py` builds it from `sim/link_inner.py` (`link(65536)`, the board image). The checksum is the sum of the payload words, mod 2^32. It does not cover the header.

Header, 5 words, 20 bytes:

| Offset | Field | This image |
|---:|---|---|
| `0x00` | magic `0x314B5344` (`D`,`S`,`K`,`1`) | `0x314B5344` |
| `0x04` | version | `1` |
| `0x08` | build | `0xD1` |
| `0x0C` | payload length, bytes | `17908` |
| `0x10` | checksum of the payload | `0xB0F27DF4` |

Payload, the `length` bytes. A 9-word directory, then the inner core, then the sector pages.

| Offset | Field | This image |
|---:|---|---|
| `0x00` | `core_base`, HyperRAM address of the first code word | `0x18000` |
| `0x04` | `core_bytes` | `14196` |
| `0x08` | `body`, Modules entry | `0x1B740` |
| `0x0C` | `init_bytes`, including the terminating 0 | `604` |
| `0x10` | `sector_bytes`, one page | `1024` |
| `0x14` | `sector_count` | `3` |
| `0x18` | sec0, the directory | `29` |
| `0x1C` | sec1, `AMemoryMappedToggle.rsc` | `58` |
| `0x20` | sec2, `Blink5.rsc` | `87` |

Then, in order: `core_bytes` of the packed code (the ROM slice the stub executes from `core_base`), `init_bytes` of the `(dest, value)` stream the stub stores (a 0 dest ends it), and `sector_count` raw pages of `sector_bytes`. The pages are the three sectors `SpiSector` serves, before the sparse-pair pack. Directory mark `0x9B1EA38D` names the two `.rsc` files. Each file page starts with mark `0x9BA71D86`.

This image is 17928 bytes and ends at `0x204608`. Code starts at flash `0x200038`, the init stream at `0x2037AC`, sector 29 at `0x203A08`, sector 58 at `0x203E08`, sector 87 at `0x204208`. Item E reads the directory and adds those sizes; the addresses move if the core grows.

### Item 7, measured

The host wrote that file and a fresh SRAM load read it back. The reader blinks at 2.0 Hz when the header matches build `0xD1` and the checksum matches. Build `0xD2` stays dark. Nano 4K only. The Primer stayed on its current image. `oberon/src/Modules.Mod` was not edited. openFPGALoader 1.2.0 reached the external NOR, so the installer bitstream item B already proved was left unbuilt.

`sim/run_spi_disk_reader.sh` (Icarus, the 17928-byte image in a small NOR model, no DDR3) prints `SPI_DISK PASS all`. The reader issues one `03h` at `0x200000`, no other command. It reports magic `314b5344`, build `000000d1`, length `17908`, checksum `b0f27df4`, and 17928 bytes. With the shortened divider the high half is 20 cycles. The FPGA half-period is the published `6750000`. A reader built for `0xD2` halts after the 20-byte header and the LED stays 0. Flipping payload byte 0 keeps the header and fails the checksum, and the LED stays 0. A header of `FF` stays dark.

The rate was fixed in `gowin/spi_disk_rates.vh` before either load. The PLLVR bypass is the pathfinder's 27 MHz clock. A 50% blink at 2.0 Hz is half-period 6,750,000. The negative image uses the same half-period and must stay dark.

| Check | Half-period | Rate |
|---|---:|---:|
| Read, build `0xD1`, checksum `0xB0F27DF4` | 6,750,000 | 2.0 Hz |
| Negative, build `0xD2` | 6,750,000 | dark |

The place runs were at 23:54 (Europe/Amsterdam). The place table lists no block RAM.

| Image | Logic | CLS | Free CLS |
|---|---|---|---:|
| `spi_disk_read` | 427/4608 (312 LUT, 115 ALU) | 355/2304 | 1949 |
| `spi_disk_neg` | 425/4608 (310 LUT, 115 ALU) | 351/2304 | 1953 |

Each image is 375 registers (372 FF). The bus was 3 address 081. Idcode `0x100981b`, GW1NSR-4C. JEDEC on the external part is `0x856016`, Puya P25Q32H, 32 Mbit. The data-file write is `-f --external-flash` with a `.bin`, which this loader parses as raw bytes and programs at `-o`. A `.fs` on that path would be a bitstream and was not used. The reader bitstreams were `-m` only. Each SRAM load printed `write to ram` and `CRC check: Success`.

The erase log prints start `00200000` and the tool's 64 KB display figure `00210000`. On this part a 64 KB erase is aligned to `0x200000`, so the erased block is `0x200000`–`0x20FFFF`, inside the disk region. The 256 bytes at `0x1FFF00` were `FF` before the write and `FF` after. `--verify` passed, and `cmp` of the 17928-byte dump against `disk.bin` passed.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  sim/out/guard_before.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  -f --external-flash -o 0x200000 --verify \
  sim/out/disk.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x200000 --file-size 17928 \
  sim/out/disk_readback.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  sim/out/guard_after.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_disk_read.fs
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/spi-fs/spi_disk_neg.fs
```

Webcam `measure_blink`, `/dev/video2`, `roi=nano4k`, duration 20, warmup 2. The analyzer's Blink3 "expected" field is not this reader's rate.

The read image: edge 1.999583 Hz, period 0.500104 s, 88 edges, duty 0.516, FFT 1.996558 Hz, SNR 899, confidence 1.0, 661 frames, 29.994 fps, ROI `272,240` 28×20. The implied edge is 6,751,406 cycles against 6,750,000. Clip: `/home/lypanov/fpga/blink-measure/20261108-disk-read/clip.mkv`.

The negative load used that same box. In the blink clip the on samples average 61.2 and the off samples average 5.88. On the negative image the same box averages 5.85 and peaks at 10.3, which is the off floor. The tool reports no blink: edge 0.877 Hz against FFT 0.272 Hz, SNR 13.5, confidence 0.12. The LED stayed dark. Clip: `/home/lypanov/fpga/blink-measure/20261108-disk-neg/clip.mkv`.

### Item 8 (was E) — boot the 4K from the flash disk

The 4K ROM holds only a bootstrap, about one block. It reads the header from `0x200000`, checks the magic, the build number and the checksum, copies the core into HyperRAM, and branches to the `Modules` body, as the book's boot loader does. From then on every instruction is fetched from HyperRAM: the core translation (`CoreMap` `coreRom`/`coreBase`, `holdForCode`) is not elaborated in this image. `SpiSector` reads sectors from the NOR instead of from the ROM.

The checksum result also feeds item C's arm word. A stale or damaged disk leaves the LED dark.

Blink law: Blink5's loop already runs from HyperRAM, so the period formula should be unchanged, and only the first edge moves (the SPI copy at boot). Compute both before the board is trusted. Record ROM words and block RAM before and after. The expectation is the ROM going from 4096 words to 512 or fewer, and block RAM from 10/10 to about 3/10. Prove it in sim (the SPI flash model loaded with `disk.bin`), then on the 4K. No Dock stage, and say so in the write-up.

### Item 8, measured

The 4K boots from the disk. The ROM is a 102-word bootstrap in a 512-word block. It reads the header at `0x200000`, checks magic `0x314B5344`, build `0xE1`, and the payload checksum, copies the core into HyperRAM, and branches to the Modules body. From then on every instruction is fetched from HyperRAM, and `SpiSector` reads its sectors from the NOR. There is no Dock stage. `ddr3modules` is not linked with `--flash-boot`, and the Primer was not placed or loaded. It stayed on its current image.

The period was fixed before the board was trusted. Blink5's loop is `462*N+598` bridge cycles at 27 MHz. For `N=65536` that is 30,278,230 cycles, an edge every 1.121416 s, a full blink of 0.4459 Hz. The SPI copy moves only the first edge.

`sim/run_disk_boot.sh` builds the Verilator top: `CPUSimTop` plus `sim/spi_disk_model.v` loaded with `sim/out/disk.bin`. HyperRAM starts as ones (`+init_fill=ffffffff`). The model is on the bridge clock. No DDR3 device and no Micron model.

The `N=65536` image, the one on the board: edge 1 at cycle 42,566,064 (LED 1), edge 2 at cycle 72,844,294 (LED 0). The interval is 30,278,230. Mask `ffffffffff`, R5 0, R9 0, not halted, PC `0x2070`. A disk whose build byte is `0xE2` halts at cycle 3238, LED 0, PC `0x214`. Flipping payload byte 40 halts at cycle 4,944,516, LED 0, PC `0x214`. Neither negative image turns the LED on.

The standing modules image used 3930 of 4096 ROM words and 10/10 block RAM: 8 pROM plus the HyperRAM controller's SDPB and SDPX9B. This image uses 102 of 512. The other 410 words are the halt word `E7FFFFFF`. The place at 00:40 (Europe/Amsterdam), `modules_n65536`, reports one pROM. Block RAM is 3/10: 1 pROM, 1 SDPB, 1 SDPX9B. Logic 3871/4608 (84%; 3574 LUT, 297 ALU, 0 ROM16), was 3967/4608 on the item C place. Registers 1791/3612 (1786 FF). CLS 2164/2304 (94%, 140 free), was 2173/2304.

The host image is build `0xE1`, so the `0xD1` disk item D left on the board fails the build check and stays dark. Header checksum `0x8A0987D4`. The elaborated arm word is `0xA11C0DE5` xor that checksum, `0x2B158A31`. The bootstrap stores the checked sum at address 8. The arm prologue xors that word in. The checksum is not an immediate in the payload. The directory is unchanged in shape: core at `0x18000`, 3549 code words, body `0x1B740`, 151 init words, sectors 29, 58, and 87. The file is 17928 bytes. The delay word in `Blink5.rsc` is still `0x60000001`.

Bitstreams stay SRAM-loaded. The data-file write is inside `0x200000`–`0x3FFFFF`. Nothing was written below `0x200000`, and no bitstream was written to flash. Bus 3 address 081, idcode `0x100981b`, GW1NSR-4C. The 256 bytes at `0x1FFF00` were `FF` before the write and `FF` after. `--verify` passed, and `cmp` of the 17928-byte dump against `disk.bin` passed. The SRAM load printed `write to ram` and `CRC check: Success`.

```bash
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  sim/out/guard_before.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  -f --external-flash -o 0x200000 --verify \
  sim/out/disk.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x200000 --file-size 17928 \
  sim/out/disk_readback.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  sim/out/guard_after.bin
openFPGALoader --busdev-num 003:081 -b tangnano4k -m \
  gowin/impl/pnr/modules_n65536.fs
```

Webcam `measure_blink`, `/dev/video2`, `roi=nano4k`, duration 22, warmup 2. The analyzer's Blink3 "expected" field is not this rate. Status blinking, edge 0.431 Hz, FFT 0.438 Hz, confidence 1.0, 480 frames at 30 fps, ROI `264,222` 48×39. Against 0.4459 Hz that is the same slow side as the item C clip (0.430 Hz). The LED was not dark. Clip: `/home/lypanov/fpga/blink-measure/20261109-004330-mcp/clip.mkv`.

## Item 11, measured

The retired paths were already switched off on the two disk images, except the 0x10 and 0x50 compares, the fetch-state registers, and, on the Dock, the old hold-PC compares. Removing them is what the place can see. The patch table, the zero-store mask, and the ROM translation were not in the current netlist.

4K, `modules_n65536`, square, against the item 22 place. Logic 3752/4608 was 3792 (40 LUT, ALU stays 322). Registers 1973/3612, unchanged. CLS 2149/2304 was 2156, so 7 CLS, and 155 are free. Block RAM 4/10, unchanged (2 SDPB, 1 SDPX9B, 1 pROM). Setup violated endpoints 0. Worst setup slack +2.595 ns. `cpu_clk` Fmax 15.065 MHz against 13.500. Hold violated endpoints 2, the same cpu-to-pixel synchronizers (`armed_s1` −0.211 ns, button latch to `blank_s1` −0.068 ns).

Dock, `ddr3modules_n65536`, text, route_option 2, place_option 0, against the item 22 place. Logic 5455/20736 was 5524 (69 LUT, ALU stays 490). Registers 2916/16173 was 2921. CLS 3962/10368 was 3990. Block RAM 2/46, unchanged (1 SDPB, 1 pROM). OSER10 4, rPLL 3/4. Setup and hold violated endpoints 0. Worst listed setup slack +1.657 ns. `pclk` Fmax 115.227 MHz against 96.749. `cpu_clk` Fmax 27.002 MHz against 24.187. Pixel clock Fmax 96.508 MHz against 64.800.

Place is not reproducible, so the slack and the Fmax are not the saving. The resource counts are. The write-up, including both blinks, is `docs/next-steps.md` item 23.
