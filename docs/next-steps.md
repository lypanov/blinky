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

The book's resolution, at 60 Hz (65 MHz pixel clock). Same black-and-white fixed TMDS words, same small screen memory and text area as now, scaled or placed on the larger screen. Check first that the capture card accepts 1024×768. The 4K stays at 640×480. Item 20's check gets a 1024×768 expected image.

## Item 22 — Dock boots like the 4K

Today the Dock still runs its inner core straight from on-chip ROM, and its "disk" is inside that ROM. Make it boot the way the 4K does: the same `disk.bin` from `tools/build_disk_image.py`, the same header and checksum checks, the core copied into DDR3 and every instruction fetched from there.

Only the way the disk arrives differs. The 4K's is written once to flash with openFPGALoader. The Dock never writes flash: after the SRAM load, the host sends `disk.bin` over the Dock's UART, and the bootstrap writes it into DDR3. DDR3 training stays in ROM, as now.

The blink loop already runs from external memory, so its period should not change. Compute it before the board is trusted. A disk with the wrong build number, or one byte flipped, must stay dark.

## Item 23 — retire the old step images

Once neither board runs code from ROM, remove from the CPU the code paths that only existed for past bring-up steps: the 0x10/0x50 LED snoop, the patch table (chainFix), the single fetch at 0x1F00, the zero-store check mask, the ROM address translation, and any image that needs them. Keep the simulations and tests that still prove something on the current images, and drop the ones that only proved a retired image. This is also bring-up ledger item 11: record what each board frees.

## Item 24 — move the bootstrap flash ports off −64 and −60

The 4K bootstrap reads its flash through I/O addresses −64 and −60. In the book those are the millisecond timer (−64) and the switches and LEDs (−60), which items 25 and 26 need. Move the flash ports to addresses the book does not use, and write the full I/O map (the book's addresses, the video ports, the arm word, the flash ports) into this section, so later items don't collide.

## Item 25 — the millisecond timer

A counter at −64 that goes up by one every millisecond, as in the book. `Kernel.Time` reads it. Blink waits on `Kernel.Time` instead of counting loop turns, so the blink rate is set in milliseconds and no longer depends on the CPU's speed. Both boards should then blink at the same published rate. This is a strong whole-system proof: the clock, the counter, the Kernel, and Blink all have to agree. About 20–30 CLS on the 4K.

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
