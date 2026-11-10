# Next steps (to-do items 19–31)

The write-ups for `docs/todo.md` items 19–31. The rules in `docs/strategy.md` apply to every item: each one keeps the LED blinking at a rate published before the board is trusted, a failed check leaves the LED (and the screen) dark, and Oberon code is preferred to FPGA logic where it is not much slower. Both boards are built at every item. If the Nano 4K does not fit, follow the open items in `docs/bringup-ledger.md`.

## Item 19 — button gate on both boards, proved on hardware

Done. Rebuilt on the counter images, not merged from PR #22. The gate sits after the CPU's LED register. `cpu_led` keeps toggling. The pin is that register while the gate is released, and 0 while it is pressed, so a release shows the phase the blink already reached. The same pressed signal blanks the screen. The square bit and the four digit registers keep updating. Nothing here stalls the CPU, and there is no second video block RAM.

Press sources OR together. The button is active-low, through two flops. The UART is 8N1 at 115200. Press bytes are `0x01`, ASCII `1`, and space. Release bytes are `0x00` and ASCII `0`. Any other byte leaves the latch. The 4K samples on `cpu_clk` (13.5 MHz, 117 clocks a bit). The Dock samples on `cpu_clk` (24.1875 MHz, 210 clocks a bit). The edge is still `466*N+780`. N=65536 is 0.442035 Hz on the 4K and 0.39598 Hz on the Dock. Blink5 and the disk were not rewritten.

Verilator, `sim/run_button_gate.sh`: both divisors. The pin follows `cpu_led` until the button or a press byte forces it off, the CPU edge keeps its period while the pin is held, and a release follows the register. `0x55` does not latch. A button held across an ASCII `0` keeps the pin off. `sim/run_video.sh`: a blanked flash frame is black, a blanked square frame has no block, and a blanked text frame has no white pixels. Releasing the blank shows the block and the digits again.

4K place, `modules_n65536`, square: logic 3792/4608 (83%; 3470 LUT, 322 ALU), registers 1973/3612, CLS 2156/2304 (94%, 148 free), block RAM 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). The counter place was 3779 logic and 2161 CLS. Setup violated endpoints 0. Worst setup slack +2.955 ns. `cpu_clk` Fmax 14.061 MHz against 13.500. Two hold endpoints are the cpu-to-pixel synchronizers, relationship 0: `armed_s1` at −0.543 ns, and the new `uart_latch` to `blank_s1` at −0.367 ns. `io_btn_n` is pin 14, IOB4[B], LVCMOS18, pull-up. S2 on pin 15 stays reset. SRAM load was bus 003:081 (`-m` only, `write to ram`, Load SRAM 100%, CRC check Success). Idcode `0x100981b`, GW1NSR-4C. Nothing was written to flash.

Webcam `/dev/video2`, the Nano LED near (210, 193), box `190,170` 50×45, 15 fps: edge 0.425923 Hz, period 2.347841 s, duty 0.511, 20 edges, confidence 0.9969. Against 0.442035 Hz that is 3.64% slow, the same side as the square measurement. The LED was not dark. Clip: `/home/lypanov/fpga/blink-measure/button-gate-7540-nano/clip.mkv`. The 4K UART pins 18 and 19 do not reach the BL702, so the unattended press is the Dock's. S1 itself needs a person.

Dock place, `ddr3modules_n65536`, text, route_option 2, place_option 0: logic 5408/20736 (27%; 4915 LUT, 493 ALU), registers 2468/16173, CLS 3738/10368 (37%), block RAM 9/46 (1 SDPB, 8 pROM), OSER10 4, rPLL 2/4. The counter place was 5396 logic and 3743 CLS. Setup and hold violated endpoints 0. The worst listed setup slack is +2.088 ns. `pclk` Fmax is 121.861 MHz against 96.749. `cpu_clk` Fmax is 28.912 MHz against 24.187. The placed report names `ddr3_hdmi.cst`. Clock is H11, the blink pin is L14, `uart_tx` is M11, `uart_rx` is T13, and `btn_n` is T3, bank 4, LVCMOS15, pull-up. The DDR3 balls stay SSTL15.

An unconstrained gate held DDR3 training. Two SRAM loads stayed at PC `0080` with F `4B`, and the LED at (322, 39) stayed dark. The same pins with the gate removed trained (F `AB`, G `A55A`, the LED blinking), and the item 18 bitstream still trains on this board, so it is not a Micron failure. The DQS primitive sits at R56C45. `ddr3.cst` keeps the gate in the opposite corner, `R[2:22]C[2:18]`. The first SRAM load of that image released the CPU at PC `0004` with G `FF00` and a dark LED. The second load of the same file settled: PC in the delay loop (`2214` through `2238`, and `225C`), mask `FFFFFFFFFF`, E0 `A55A`, G `A55A`, F `AB`. SRAM loads were bus 003:078 only (`-m`, `write to ram`). Idcode `0x81b`, GW2A-18. The Nano was not opened for those loads. Nothing was written to flash.

Webcam `/dev/video2`, the Dock LED, box `300,28` 50×40, 15 fps: edge 0.395578 Hz, period 2.527949 s, duty 0.5125, 25 edges, confidence 0.9964. Capture card UGREEN 15389, `/dev/video0`, same run, 1801 frames at 60 fps. The frame grabbed just before it was green snow. The clip is a locked field, about (3,3,3), with no green frame. A lit square is 440 pixels above luma 80, at x=338..359 and y=220..239. One frame also lights y=240 under that box. The glyphs sit at y=48..54, x=342..377. The opening rise-to-rise is an 80-frame fragment. The next ten are 151 or 152 frames, six of 151 and four of 152. The mean is 2.5233 s, 0.39630 Hz. The two rates differ by 0.18%. Against 0.39598 Hz the screen is 0.08% fast and the LED is 0.10% slow. Clips: `/home/lypanov/fpga/blink-measure/button-gate-7540-dock/screen.mkv` and `/home/lypanov/fpga/blink-measure/button-gate-7540-dock/led/clip.mkv`.

UART press, FTDI channel B, 115200 8N1, opened without an FTDI chip reset. The host sent `0x01`, held about 9 s, then `0x00`. The training line stayed `C.` with F `AB` and G `A55A`, and the PC stayed in the delay loop. The LED was dark for 8.87 s (133 frames at 15 fps). The square was dark for 8.83 s and the glyphs for 8.27 s; a natural off-half is about 76 frames, so the dark stretch covers three on-edges. The digits read `0066` on the last lit frame before the press and `0069` on the frame the glyphs return. The next on-edges read `0070` and `0071`. The LED and the square come back on the same edge. After that the square periods are 151 or 152 frames. Clips: `/home/lypanov/fpga/blink-measure/button-gate-7540-press/screen.mkv` and `/home/lypanov/fpga/blink-measure/button-gate-7540-press/led.mkv`.

Needs a person. Do not hold the item open for these. On the 4K, hold S1 (pin 14, active-low). The LED and the square go dark and stay dark. Release them and they come back together, in the phase the blink already reached, still at 0.442035 Hz. Do not hold S2; that pin is reset. On the Dock, hold S2 (ball T3, active-low). The LED, the square, and the digits go dark and stay dark. Release them and they come back together, in phase, at 0.39598 Hz. Do not hold S1; that key is reset. The UART press above is the same gate, already measured.

## Item 20 — screen check in Verilator

Done. `sim/run_frame_check.sh` taps `word0`, `word1`, and `word2`, the pixel words before the HDMI serializer, and writes one 640×480 frame. The host draws the picture that frame should hold (`tools/frame_expect.py`, the same 8×8 font). Any difference fails. The Nano runs 1 CPU clock per 2 pixel clocks (13.5 MHz and 27 MHz). The Dock runs 43 CPU clocks per 48 pixel clocks (24.1875 MHz and 27 MHz). The arm rises at CPU cycle 2. The on-store, and the LED rise for flash, is CPU cycle 64. Blank rises at CPU cycle 128 when that picture is the one under test. Each run holds those levels and writes the next whole frame.

Cycle 32 is the off picture. Flash and square are black, 0 white pixels. The Dock counter shows `0000`, 88 white pixels, the reset value of the four digit registers. Cycle 200 is the on picture. Flash is white, 307200 pixels. Square is the 20×20 block at (15, 11), 400 white pixels. The Dock counter is `0001` plus that block, 485 white pixels. The same on picture with blank held is black, 0 white pixels, on the square and on the counter. The 4K image stops at square, so that on-store there is the block alone, 400 white pixels.

On the Nano the captured frame starts at CPU cycle 210000. On the Dock it starts at 376250. The Nano and Dock files of each flash picture match, and so do the square pictures. A host picture of `0002` plus the block differs in 21 pixels. A black picture against the white flash differs in all 307200 pixels. Neither board was loaded. Nothing was written to flash. Gowin does not define `FRAME_CHECK`. The board path is still the four digit registers and the one screen block RAM.

## Item 21 — Dock: the screen at 1024×768

Done. The book's 1024×768 timing, counted from the start of the sync pulse. Horizontal 136 + 160 + 1024 + 24 = 1344. Vertical 6 + 29 + 768 + 3 = 806. `hs` is `hx >= 136`, `vs` is `vy >= 6`, and the active pixels are hx 296..1319 and vy 35..802. The same black and white TMDS words. The same one screen block RAM and the same 32×24 grid of 20×20 blocks, placed at the top left of the active area. The square is still block (15, 11), pixels (300, 220). The text window is still the 8×8 glyphs at (160, 48). The digits stay registers. The 4K stays at 640×480.

`CLKOUTD` divides by an even number only, so one rPLL cannot make a 50% pixel clock at one fifth of the serializer. Two rPLLs, both 50%. The pixel PLL is 27×12/5 = 64.8 MHz (ODIV 16, VCO 1036.8). The serializer PLL locks to that clock at 5×, 324 MHz (VCO 648). 64.8 is 0.31% under 65 MHz. 1344×806 at 64.8 MHz is 59.82 Hz. The capture card lists 1024×768 at 60 Hz. The locked frames below are that mode.

`sim/run_frame_check.sh` builds the Dock pictures with `VIDEO_DOCK`. The Dock ratio is 215 CPU clocks per 576 pixel clocks (24.1875 MHz and 64.8 MHz). The Nano stays 1 per 2, and its frame still starts at CPU cycle 210000. The Dock frame starts at CPU cycle 404343. Dock flash off is black. Dock flash on is 786432 white pixels. Dock square on is 400. The Dock counter off is `0000`, 88 white pixels. On is `0001` plus the block, 485. Blank is black. A host picture of `0002` plus the block differs in 21 pixels. The Nano pictures are unchanged.

4K place, `modules_n65536`, square, not loaded: logic 3792/4608 (83%; 3470 LUT, 322 ALU), registers 1973/3612, CLS 2156/2304 (94%, 148 free), block RAM 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Same counts as the item 19 place. Setup violated endpoints 0. Worst setup slack +2.955 ns. `cpu_clk` Fmax 14.061 MHz against 13.500. The two hold endpoints are the same cpu-to-pixel synchronizers: `armed_s1` at −0.543 ns, and `uart_latch` to `blank_s1` at −0.367 ns. The Nano was not opened.

Dock place, `ddr3modules_n65536`, text, route_option 2, place_option 0: logic 5523/20736 (27%; 5029 LUT, 494 ALU), registers 2469/16173, CLS 3821/10368 (37%), block RAM 9/46 (1 SDPB, 8 pROM), OSER10 4, rPLL 3/4. The button-gate place was 5408 logic, 3738 CLS, and 2 rPLL. Setup and hold violated endpoints 0. The worst listed setup slack is +1.249 ns. The pixel clock is 64.800 MHz, Fmax 85.123. The serializer is 324.000 MHz, generated from the pixel PLL. `pclk` Fmax is 110.047 MHz against 96.749. `cpu_clk` Fmax is 30.407 MHz against 24.187. The placed report names `ddr3_hdmi.cst`. Clock is H11, the blink pin is L14, `uart_tx` is M11, `uart_rx` is T13, and `btn_n` is T3. The gate stays in `R[2:22]C[2:18]`.

SRAM load was bus 003:078 only (`-m`, `write to ram`, Load SRAM 100%). Idcode `0x81b`, GW2A-18. The Nano was not opened. Nothing was written to flash. The first load left the delay loop: PC `2214` through `2230` and `225C`, mask `FFFFFFFFFF`, E0 `A55A`, G `A55A`, F `AB`. There was no second load. UART was FTDI channel B, 115200 8N1, opened without a USB reset of the chip.

The frame grabbed just after the capture card was set to 1024×768 was green snow, mean about (2, 97, 3), with a noisy 640×480 window in the corner. The following frames are a locked black field across the whole 1024×768, about (3, 3, 3). A lit square is 400 pixels above luma 80, at x=300..319 and y=220..239, about (211, 211, 211). The glyphs sit at y=48..54, x=304..335, 68 to 89 of those pixels. No pixel above luma 80 left x=300..335, y=48..239.

Webcam `/dev/video2`, the Dock LED, box `300,28` 50×40, 14.962 fps: edge 0.395625 Hz, period 2.527644 s, duty 0.50625, 25 edges, confidence 0.9964. Capture card UGREEN 15389, `/dev/video0`, same run, 2161 frames, span 35.981 s, delivered 60.032 fps. Frames 5 through 79 are black, with no glyphs. The next thirteen rise-to-rise gaps are 151 or 152 frames, eleven of 151 and two of 152. The mean is 2.5172 s, 0.39726 Hz. Full-frame mean luma is 3.126 on and 3.021 off. Against 0.39598 Hz the screen is 0.32% fast and the LED is 0.09% slow. The two rates differ by 0.41%. Clips: `/home/lypanov/fpga/blink-measure/dock-1024-0a59/screen.mkv` and `/home/lypanov/fpga/blink-measure/dock-1024-0a59/led/clip.mkv`.

## Item 22 — Dock boots like the 4K

Done. The Dock boots from the same `disk.bin` as the 4K. `tools/build_disk_image.py` still writes that file, and the Dock host sends those bytes after the SRAM load. The ROM is the 512-word bootstrap. It checks the magic, the version, the build, and the payload checksum, stores every file word in DDR3, and copies the core and the init stream to the addresses the 4K uses. The body is fetched from DDR3. Training stays in the controller. The button gate ignores the UART until the arm word, because a disk contains `0x01` and `0x00`.

The edge is `466*N+780` CPU clocks. At N=65536 that is 30540556 clocks. At the Dock `cpu_clk` of 24.1875 MHz the edge is 1.26266 s and the full blink is 0.39598 Hz. The UART transfer moves only the first edge.

HyperRAM, N=5: the good disk blinks at period 3110, PC `0x2070`. A wrong build halts at PC `0x260` with the LED off. One flipped payload byte does the same. The 4K flash path, re-run with `sim/run_disk_boot.sh 5`, is period 3110 at PC `0x2070`.

4K place, `modules_n65536`, square, not loaded: logic 3792/4608 (83%; 3470 LUT, 322 ALU), registers 1973/3612, CLS 2156/2304 (94%), block RAM 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Setup violated endpoints 0. Worst setup slack +2.955 ns. `cpu_clk` Fmax 14.061 MHz against 13.500. Hold violated endpoints 2, the same cpu-to-pixel synchronizers as item 21. The Nano was not opened.

Dock place, `ddr3modules_n65536`, text, route_option 2, place_option 0: logic 5524/20736 (27%; 5034 LUT, 490 ALU), registers 2921/16173, CLS 3990/10368 (39%), block RAM 2/46 (1 SDPB, 1 pROM), OSER10 4, rPLL 3/4. Setup and hold violated endpoints 0. The worst listed setup slack is +1.380 ns. `pclk` Fmax 111.660 MHz against 96.749. `cpu_clk` Fmax 27.508 MHz against 24.187. The pixel clock Fmax is 91.176 MHz against 64.800. The placed report names `ddr3_hdmi.cst`. The gate and the UART receiver stay in `R[2:22]C[2:18]`.

The trainer on this place locked lane 0 at step 1. The directory words read back, and the body instruction did not. The write delay used after training is lane 1 step 12 and lane 0 step 10, the pair the working Modules boots on this board have trained. The status line shows that pair as `000C 000A`. The trainer's own lock stays in `C0`/`C1`.

SRAM load was bus 003:078 only (`-m`, `write to ram`, Load SRAM 100%). Idcode `0x81b`, GW2A-18. The Nano was not opened. Nothing was written to flash. UART was FTDI channel B, 115200 8N1, opened without a USB reset. The line starts `C.`. After `tools/send_dock_disk.py` sent the 17928-byte disk, the PC sits in the delay loop (`2214` through `2238` and `225C`), mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The write halfword is `000010F9`.

Webcam `/dev/video2`, the Dock LED, box `300,28` 50×40, 29.988 fps: edge 0.395875 Hz, period 2.52605 s, duty 0.5189, 18 edges, confidence 0.998, FFT SNR 274. Against 0.39598 Hz the LED is 0.03% slow. Clip: `/tmp/blink-dock-uart-39e7/clip.mkv`.

Capture card UGREEN 15389, `/dev/video0`, already at 1024×768. The first frames were green snow, mean about (5.5, 47.2, 6.7). Frame 17 is a locked black field, about (3, 3, 3). A lit square is 400 pixels above luma 80, at x=300..319 and y=220..239. The glyphs at y=48..54, x=304..335 are 78 pixels. One rise-to-rise gap in that 6 s clip is 152 frames, 2.5333 s, 0.39474 Hz. Clip: `/tmp/dock-screen-39e7/screen.mkv`.

A disk with the build byte flipped halts at PC `0260`, mask `0000000000`, R9 `0002100C`. The LED box stays near 0.69 with no swing (the good clip swings from 0.08 to 25.5). One hundred and twenty locked capture frames have no lit square. A disk with payload byte 40 flipped consumes the file and halts at PC `0260`, mask `0000000000`, R9 `00025608`.

## Item 23 — retire the old step images

Done. The CPU no longer carries the paths that only existed for past bring-up steps. The LED store is the address the linker records. The 0x10/0x50 snoop, the patch table, the single fetch at 0x1F00, the zero-store check mask, and the ROM address translation are gone, and so is the in-ROM image that needed them. `SpiSector` reads the NOR or the DDR3 word only. The Dock status line no longer compares the old hold PCs, so `H` stays `.`. The 128-byte line and the write-step fields stay. The blink edge is still `466*N+780`.

The current images are the two disk boots. `FPGA_IMAGE` and `SIM_IMAGE` accept `modules` and `ddr3modules`. The 4K ROM is the NOR bootstrap. The Dock ROM is the UART bootstrap. The same `disk.bin` is both. N=65536 disk bytes match the previous tip: 17928 bytes, checksum `6bae42b7`, arm word `cab24f52`. Nothing was written to the NOR.

Verilator, N=5. The NOR disk blinks at period 3110, PC `0x2070`, mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The UART disk, on the HyperRAM stand-in, does the same. A wrong build halts at PC `0x260` with the LED off. One flipped payload byte does the same. `tools/run_verilator_sim.sh` runs those two. The Blink2 mill test, the ignored `final_system` test, and the three Blink3 IMEM checks are gone. The ISA tests stay.

4K place, `modules_n65536`, square. Against the item 22 place this frees 40 logic (40 LUT, the ALU stays 322), 0 registers, and 7 CLS. Block RAM stays 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Logic 3752/4608 (82%; 3430 LUT, 322 ALU), registers 1973/3612, CLS 2149/2304 (94%, 155 free). Setup violated endpoints 0. Worst setup slack +2.595 ns. `cpu_clk` Fmax 15.065 MHz against 13.500. Hold violated endpoints 2, the same cpu-to-pixel synchronizers: `armed_s1` at −0.211 ns, and the button latch to `blank_s1` at −0.068 ns. Place is not reproducible; the slack and the Fmax moved, and both stay on the same side of the constraint.

Dock place, `ddr3modules_n65536`, text, route_option 2, place_option 0. Against the item 22 place this frees 69 logic (69 LUT, the ALU stays 490), 5 registers, and 28 CLS. Block RAM stays 2/46 (1 SDPB, 1 pROM). Logic 5455/20736 (27%; 4965 LUT, 490 ALU), registers 2916/16173, CLS 3962/10368 (39%), OSER10 4, rPLL 3/4. Setup and hold violated endpoints 0. The worst listed setup slack is +1.657 ns. `pclk` Fmax 115.227 MHz against 96.749. `cpu_clk` Fmax 27.002 MHz against 24.187. The pixel clock Fmax is 96.508 MHz against 64.800. The serializer is 324 MHz. The placed report names `ddr3_hdmi.cst`. The gate group stays in `R[2:22]C[2:18]`.

The first SRAM load stayed in training: PC `0080`, `F` `4B`, dark line `..`. The second load of the same bitstream trained. The line starts `C.`. The write delay after training is lane 1 step 12 and lane 0 step 10, shown as `000C 000A`. `G` is `A55A`, `E0` is `A500`, `F` is `AB`. SRAM load was bus 003:078 only (`-m`, `write to ram`, Load SRAM 100%). Idcode `0x81b`, GW2A-18. UART was FTDI channel B, 115200 8N1, opened without a USB reset. After `tools/send_dock_disk.py` sent the 17928-byte disk, the PC sits in the delay loop (`2214`, `2220`, `2224`, `222C`, `2230`, `2238`, `225C`), mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The write halfword is `000010F9`.

Webcam `/dev/video2`, the Dock LED, box `300,28` 50×40, 30.003 fps: edge 0.396672 Hz, period 2.52098 s, duty 0.4983, 24 edges, confidence 0.9978, FFT SNR 417. Against 0.39598 Hz the LED is 0.17% fast. Clip: `/tmp/blink-retire-4b73/clip.mkv`.

Capture card UGREEN 15389, `/dev/video0`, already at 1024×768, 60 fps. The first frames were green snow, mean about (6.3, 36.6, 7.6). Frame 17 is a locked black field, about (3, 3, 3). A lit square is 400 pixels above luma 80, at x=300..319 and y=220..239. The glyphs at y=48..54, x=304..335 reach 88 pixels. One full rise-to-rise gap is 151 frames, 2.5167 s, 0.39735 Hz. Clip: `/tmp/dock-screen-4b73/screen.mkv`.

The Nano load needed the FTDI serial interface released first. `ftdi_usb_reset` returned busy while `ftdi_sio` held interface 1 of bus 003:081. After that driver was detached, a USB reset (VBUS stayed on) let the SRAM load through. `write to ram`, Load SRAM 100%, CRC check Success. The serial driver was attached again afterwards. Nothing was written to flash.

Webcam `/dev/video2`, the Nano LED, `roi=nano4k` resolved to `206,240` 18×14, 30.002 fps: edge 0.426723 Hz, period 2.34344 s, duty 0.5135, 28 edges, confidence 0.9977, FFT 0.436619 Hz, SNR 252. Against 0.442035 Hz the LED is 3.46% slow, the same side as item 19's 0.425923 Hz. Clip: `/tmp/blink-nano-4b73/clip.mkv`.

## Item 24 — move the bootstrap flash ports off −64 and −60

Done. The bootstrap's two flash ports moved out of the book's window. A load from −72 (`0xFFFFFFB8`) returns one disk word and advances the pointer. A store to −72 sets the NOR byte address the next load reads. The Dock has no NOR, so the same load takes one word from the UART. A store to −68 (`0xFFFFFFBC`) sets the sector base `SpiSector` adds its word index to. The SD window stays −48 and −44. The blink edge stays `466*N+780`.

The book's I/O is the top 64 bytes. `RISC5Top.v` (14 October 2014) decodes that window, and `Input.Mod` and `PIO.Mod` name the same words. Sixteen words, −64 through −4:

| Address | Read | Write |
|---|---|---|
| −64 | millisecond counter | |
| −60 | buttons and switches | LEDs |
| −56 | RS232 received byte | RS232 transmit byte |
| −52 | RS232 status, transmit-ready and receive-ready | RS232 bit-rate bit |
| −48 | SPI received word | SPI transmit word, starts the transfer |
| −44 | SPI ready | SPI control |
| −40 | mouse, and keyboard-ready in bit 28 | |
| −36 | keyboard byte | a read acknowledges the keyboard |
| −32 | general-purpose pins | general-purpose pins |
| −28 | pin direction | pin direction |
| −24, −20, −16, −12, −8, −4 | 0 | |

The file's own comment swaps the mouse and the keyboard. The mux and `Input.Mod` (`msAdr = -40`, `kbdAdr = -36`) are the ones above. The book's picture is the bitmap at `0E7F00H`, 1024×768, one bit per pixel. It is not one of these words.

This machine's ports sit under that window:

| Address | What it is |
|---|---|
| −80 `0xFFFFFFB0` | Screen block. Bit 0 is block (15, 11). Blink5 stores `MMT.light` here. The store is decoded and dropped. The Dock counts the on-edges of this store into the four digit registers. |
| −76 `0xFFFFFFB4` | Reserved for a blink-count store. `video.v` names it. The CPU does not decode it, and the Dock ties that write to 0. |
| −72 `0xFFFFFFB8` | Flash word port. NOR on the 4K, UART on the Dock. |
| −68 `0xFFFFFFBC` | Sector base for the disk pages. |

The arm word is a RAM store, at `0x7C0`. Blink5 stores `0xA11C0DE5` xor the disk checksum. This disk's checksum is `0x6BAE42B7`, so the word the hardware compares is `0xCAB24F52`. A different word leaves the LED dark. The address is below the heap and outside the I/O window.

The CPU already decodes the book's SPI words, −48 and −44. It does not decode the timer or the switches. Those two stay free for items 25 and 26.

Verilator, N=5. The NOR disk blinks at period 3110, PC `0x2070`, mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The UART disk, on the HyperRAM stand-in, does the same. A wrong build halts at PC `0x260` with the LED off, at cycle 3996. One flipped payload byte does the same, at cycle 5737128. `tools/run_verilator_sim.sh` runs those two. The N=5 disk checksum is `4bae469b` and its arm word is `eab24b7e`, because that run patches the delay word. The N=65536 disk bytes match the previous tip: 17928 bytes, checksum `6bae42b7`, arm word `cab24f52`. Nothing was written to the NOR.

4K place, `modules_n65536`, square. Against the item 23 place this uses 61 more logic (61 LUT, the ALU stays 322), the same 1973 registers, and 16 more CLS. Block RAM stays 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Logic 3813/4608 (83%; 3491 LUT, 322 ALU), registers 1973/3612, CLS 2165/2304 (94%, 139 free). Setup violated endpoints 0. Worst setup slack +3.220 ns, the HyperRAM chip-select path. `cpu_clk` Fmax 14.973 MHz against 13.500. Hold violated endpoints 1: `u_gate/uart_latch_s0` to `u_video/blank_s1_s1`, slack −0.385 ns, the cpu clock into the pixel clock. `armed_s1` to `armed_s1_s0` is +0.441 ns. Place is not reproducible; the slack and the Fmax moved, and both stay on the same side of the constraint.

Dock place, `ddr3modules_n65536`, text, route_option 2, place_option 0. Against the item 23 place this uses 76 more logic (76 LUT, the ALU stays 490), the same 2916 registers, and 15 more CLS. Block RAM stays 2/46 (1 SDPB, 1 pROM). Logic 5531/20736 (27%; 5041 LUT, 490 ALU), registers 2916/16173, CLS 3977/10368 (39%), OSER10 4, rPLL 3/4. Setup and hold violated endpoints 0. The worst listed setup slack is +1.447 ns. `pclk` Fmax 112.493 MHz against 96.749. `cpu_clk` Fmax 29.523 MHz against 24.187. The pixel clock Fmax is 94.233 MHz against 64.800. The serializer is 324 MHz. The placed report names `ddr3_hdmi.cst`. The gate group stays in `R[2:22]C[2:18]`.

The first SRAM load, bus 003:078 only (`-m`, `write to ram`, Load SRAM 100%), was followed by a listen that still showed the previous image in the delay loop and then dropped to training: PC `0080`, `F` `4B`. The second load of the same bitstream started there. Idcode `0x81b`, GW2A-18. UART was FTDI channel B, 115200 8N1, opened without a USB reset. After `tools/send_dock_disk.py` sent the 17928-byte disk, the line trained. It starts `C.`. The write delay is lane 1 step 12 and lane 0 step 10, shown as `000C 000A`. `G` is `A55A`, `E0` is `A55A`, `F` is `AB`. The PC moved through `0094`, `0164`, and `01C4` into the delay loop. A later listen, still without a USB reset, stays there (`2214`, `2218`, `221C`, `2220`, `2224`, `2228`, `222C`, `2230`, `2234`, `2238`, `225C`), mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The write halfword is `000010F9`. The write delay was not moved.

Webcam `/dev/video2`, the Dock LED, box `300,28` 50×40, 30.001 fps: edge 0.396708 Hz, period 2.52074 s, duty 0.5081, 25 rising edges, confidence 0.9978, FFT 0.402807 Hz, SNR 859. Against 0.39598 Hz the LED is 0.18% fast. Clip: `/tmp/blink-dock-299c/clip.mkv`.

Capture card UGREEN 15389, `/dev/video0`, already at 1024×768, 60 fps. A six-second peek opens on green snow, mean about (7.2, 27.0, 8.9), then a locked black field, about (3, 3, 3). The twenty-second clip stays locked: green mean 3.0, no frame above 20. A lit square is 400 pixels above luma 80, at x=300..319 and y=220..239, and 0 when dark. The glyphs at y=48..54, x=304..335 are 74 to 90 pixels on every lit frame, and on 580 of 654 dark frames. Six rise-to-rise gaps: five of 151 frames (2.5167 s, 0.39735 Hz) and one of 152 frames (2.5333 s, 0.39474 Hz). The mean is 0.39692 Hz, beside the LED. Clips: `/tmp/dock-screen-299c/peek.mkv`, `/tmp/dock-screen-299c/screen.mkv`.

The Nano detect on bus 003:081 returned idcode `0x100981b`, GW1NSR-4C. `ftdi_sio` held both interfaces of `3-3.1.1`. The SRAM load did not find the reset busy, so the driver stayed bound and VBUS stayed on. `write to ram`, Load SRAM 100%, CRC check Success. Nothing was written to flash. The NOR disk already on the board is those same 17928 bytes, so this bootstrap read it at −72 and −68.

Webcam `/dev/video2`, the Nano LED, box `206,240` 18×14, 30.002 fps: edge 0.427142 Hz, period 2.34114 s, duty 0.4952, 26 rising edges, confidence 0.9974, FFT 0.418938 Hz, SNR 383. Against 0.442035 Hz the LED is 3.37% slow, the same side as item 19's 0.425923 Hz and item 23's 0.426723 Hz. Clip: `/tmp/blink-nano-299c/clip.mkv`.

## Item 25 — the millisecond timer

Done. A counter at −64 that goes up by one every millisecond, as in the book. `Kernel.Time` reads it. Blink waits on `Kernel.Time` instead of counting loop turns, so the blink rate is set in milliseconds and no longer depends on the CPU's speed. Both boards blink at the same published rate. −60 stays free for item 26.

Published before the loads. Blink's wait is 1000 ms. A toggle is one second, and a full blink is 0.500 Hz, on both boards. The old edge `466*N+780` is retired.

The counter adds one every millisecond. On the Nano 4K, `cpu_clk` is 13.5 MHz. The divider adds 2 every clock and wraps at 27000, which is 13500 clocks and 1.000 ms. On the Dock, `cpu_clk` is 24.1875 MHz. The same adder wraps at 48375, which is 24187.5 clocks, alternating 24188 and 24187, and every 2 ms is exact. `Kernel.Time` is `SYSTEM.GET(−64)`. Blink waits until that reading has advanced by the wait, then adds the wait to its last sample, so a late poll does not accumulate.

Verilator, wait 2 ms. `tools/run_verilator_sim.sh`. The NOR image's edge is 54000 bridge clocks, which is 13500 CPU clocks per millisecond and two bridge clocks per CPU clock. Blink polls `Time`, so one edge can miss the tick by a poll. The checker allows 2048 bridge clocks, and the gaps have to add up inside that same window. The measured gaps are 54268 and 54268. PC `0x2070`, mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. The UART disk, on the HyperRAM stand-in, uses the Dock divider: 96750 bridge clocks for 2 ms. The gaps are 97388 and 96604, same PC and mask. A wrong build halts at PC `0x260` with the LED off, at cycle 3996. One flipped payload byte does the same, at cycle 5771688. The N=2 disk checksum is `8a33689f` and its arm word is `2b2f657a`. The hardware disk is the 1000 ms image: 18036 bytes, build `0xE1`, checksum `8a33706b`, arm word `2b2f7d8e` (`A11C0DE5` xor that checksum). The two board links produce the same disk bytes.

4K place, `modules_n1000`, square. Against the item 24 place this uses 181 more logic (149 LUT, 32 ALU), 48 more registers, and 76 more CLS. Block RAM stays 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Logic 3994/4608 (87%; 3640 LUT, 354 ALU), registers 2021/3612, CLS 2241/2304 (98%, 63 free). Setup violated endpoints 0. Worst setup slack +3.077 ns, the HyperRAM chip-select path. `cpu_clk` Fmax 14.665 MHz against 13.500. Hold violated endpoints 2, both the cpu clock into the pixel clock: `u_gate/btn1_s0` to `u_video/blank_s1_s1` at −0.686 ns, and `armed_s1` to `armed_s1_s0` at −0.544 ns.

Dock place, `ddr3modules_n1000`, text, route_option 2, place_option 0. Against the item 24 place this uses 121 more logic (89 LUT, 32 ALU), 48 more registers, and 14 more CLS. Block RAM stays 2/46 (1 SDPB, 1 pROM). Logic 5652/20736 (28%; 5130 LUT, 522 ALU), registers 2964/16173, CLS 3991/10368 (39%), OSER10 4, rPLL 3/4. Setup and hold violated endpoints 0. The worst listed setup slack is +2.088 ns. `pclk` Fmax is 121.428 MHz against 96.749. `cpu_clk` Fmax is 30.107 MHz against 24.187. The pixel clock Fmax is 75.857 MHz against 64.800. The serializer is 324 MHz. The placed report names `ddr3_hdmi.cst`. The gate group stays in `R[2:22]C[2:18]`.

The NOR disk had to be rewritten. The new Blink imports `Kernel`, so the 18036 bytes are not the item 24 image. The write was the data file only, at `0x200000`, bus 003:081. JEDEC `856016`. The read-back matches. The 256 bytes at `0x1FFF00` are unchanged. `ftdi_sio` held both interfaces of `3-3.1.1`. The write and the SRAM load did not find the reset busy, so the driver stayed bound and VBUS stayed on. `write to ram`, Load SRAM 100%, CRC check Success. Idcode `0x100981b`, GW1NSR-4C.

Webcam `/dev/video2`, the Nano LED, box `205,240` 19×14, 30.011 fps: edge 0.499391 Hz, period 2.00244 s, median 1.99927 s, duty 0.5038, 22 rising edges, confidence 0.9983, FFT 0.499427 Hz, SNR 229. Against 0.500 Hz the LED is 0.12% slow. Clip: `/home/lypanov/fpga/blink-measure/20261110-083446/clip.mkv`.

Dock detect on bus 003:078 returned idcode `0x81b`, GW2A-18. The first SRAM load (`-m`, `write to ram`, Load SRAM 100%) trained. No second load. UART was FTDI channel B, 115200 8N1, opened without a USB reset. The listen still had the previous image in its loop (`2214` through `225C`), then the new image at `0094`, mask `0000000000`, line `C.`. The write delay was already lane 1 step 12 and lane 0 step 10. After `tools/send_dock_disk.py` sent the 18036-byte disk, the PC moved through `0164` into the blink loop (`221C`, `2220`, `2224`, `2228`, `222C`, `2230`, `2234`, `2238`) and through `Kernel.Time` (`8B48`, `8B4C`, `8B54`, `8B58`, `8B5C`, `8B60`). Mask `FFFFFFFFFF`, R5 `00000000`, R9 `00000000`. `E0` is `FF5A`, `G` is `A55A`, `F` is `A8`. The lanes stay `000C` `000A`. The write delay was not moved. Nothing was written to Dock flash.

Webcam `/dev/video2`, the Dock LED, box `310,31` 28×24, 30.012 fps: edge 0.499401 Hz, period 2.00240 s, median 1.99923 s, duty 0.5061, 22 rising edges, confidence 0.9983, FFT 0.499437 Hz, SNR 992. Against 0.500 Hz the LED is 0.12% slow, 0.000010 Hz from the Nano. Clip: `/home/lypanov/fpga/blink-measure/20261110-083825/clip.mkv`.

Capture card UGREEN 15389, `/dev/video0`, 1024×768, 60 fps. The clip opens locked, mean luma about 0.1, no green snow. A lit square is 400 pixels above luma 80, at x=300..319 and y=220..239, and 0 when dark. The glyphs at y=48..54, x=304..335 are 78 to 92 pixels on the later frames, lit and dark. Eleven rise-to-rise gaps: eight of 120 frames (2.000 s, 0.500 Hz), two of 121 frames (2.0167 s, 0.49587 Hz), and one of 119 frames (1.9833 s, 0.50420 Hz). The mean is 0.49962 Hz, beside the LED. Clip: `/tmp/dock-screen-ms/screen.mkv`.

## Item 26 — the button as Oberon input

Make the buttons readable at −60, as the book's switches are (and the Dock's UART press sets the same bit). Blink reads it and decides what to do, for example pausing the blink while it is held. Then remove item 19's hardware gate: the decision now lives in Oberon, not in the FPGA. Project Oberon has no interrupts: input is polled, so Blink polls too. Verilator and the Dock UART press are automated. The 4K button check is the maintainer's, by hand.

## Item 27 — hardware `MUL`

RISC5's `MUL`, with the high word in H, as in the book. On both boards it goes on the FPGA's hardware multiplier blocks: Gowin's synthesis should map a plain `*` onto them, and the report must show it did. Take two clocks if one is too tight. `sim/link_inner.py` then stops rewriting multiplies. The arm checks gain a multiply result. This opens bring-up ledger item 12 (shifts on the multipliers).

## Item 28 — `NEW` and garbage collection

Blink allocates a small record with `NEW` every blink and drops it. The memory limit is lowered on purpose, so that without garbage collection Blink runs out after a known number of blinks, traps, and goes dark. Every so many blinks, Blink runs the collector the way `Oberon.GC` does (`Kernel.Mark` over the loaded modules, then `Kernel.Scan`). The collector is ordinary Kernel code, so this mostly tests that the loader sets up the type information correctly.

Proof: Blink keeps blinking well past the point where it would have run out. The negative: with the collector call removed, the LED goes dark at the predicted blink (the Dock's counter shows which).

## Item 29 — the blink rate from a file

The disk image builder adds a small data file, for example `Blink.Rate`. Blink opens it with `Files.Old` and reads its delay from it. Two disks with two rates, nothing else changed, must blink at their two published rates. On the 4K only the disk is rewritten; on the Dock only the UART upload changes. The bitstream stays the same.

## Item 30 — file writes through a RAM overlay

Writing to the flash needs 4 KB erases, so start in the Kernel instead: changed sectors are kept in a small table in RAM and are lost at power-off. That is Oberon code, not FPGA logic. It is the first change to the book's inner-core source, so record it carefully.

After a set number of blinks, Blink writes a new rate into `Blink.Rate`, closes the file, reads it back, and continues at the new rate. The rate change must happen at the predicted moment and at the predicted new rate. A variant: Blink hands over to a second module that reads the changed file.

## Item 31 — Oberon's own boot linker and `BootLoad`

In the book, `Modules` cannot load the inner core, because it is part of it. A boot linker joins Kernel, FileDir, Files, and Modules into one boot file, written to the boot area of the disk, and the small `BootLoad` in ROM copies it into memory and starts it. Today `sim/link_inner.py` does that job in Python, with hand patches.

Run the book's boot linker under Norebo on the host to make the boot file, build the disk in the book's layout, and use the book's `BootLoad` as the ROM bootstrap, keeping the header, checksum, and arm checks. Replace each remaining patch with an Oberon answer: `MUL` (item 27) ends the multiply rewrite, and a small module actually called `Oberon` that loads the blinker ends the `"Oberon"`→`"Blink5"` name patch. If the boot linker is not among this repo's Oberon sources, find it in the Project Oberon sources and record where it came from.
