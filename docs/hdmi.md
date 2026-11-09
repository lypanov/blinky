# HDMI on both boards

The screen becomes a second witness next to the LED. The Nano 4K goes first, so the design is sized for the smaller chip from the start. The Dock then adds what the 4K cannot hold. There is one capture card. It is on the 4K for steps 1–2 and on the Dock for steps 3–5. The maintainer moves the cable between them.

## Rules for every step

**One video module, with a build switch.** The video module takes a mode: `off`, `flash`, `square`, or `text`. Each mode includes the one before it. The 4K builds up to `square`. The Dock builds up to `text`. Today's images stay `off` unless a step changes them. Each board has its own pin file. The timing is 640×480 at 60 Hz (25.2 MHz pixel clock is fine). The book's 1024×768 comes later.

**Black and white only, so no TMDS encoder.** Project Oberon's display is one bit per pixel. Every mode here, and the 1024×768 desktop later, sends only black or white. So each channel needs only a few fixed 10-bit words: one for a black pixel, one for a white pixel, and the four control words for blanking and sync. Pick between them with a small mux. Do not build a general 8b/10b TMDS encoder. The constant pixel words keep DC balance as long as they are chosen as balanced pairs, the standard trick. Look up and record the exact words used.

**One Blink5 for both boards.** The screen is driven by stores to fixed I/O addresses. On a board, or in a mode, without that device, the store must be decoded and dropped. It must never fall through to HyperRAM or DDR3. So the same Blink5 runs everywhere: on the 4K the counter writes go nowhere, on the Dock they show up. Blink5's loop is the same instructions on both boards, and each board's blink formula is recomputed whenever the loop changes.

**The arm word gates the screen.** The screen stays black until the arm word is stored, exactly like the LED (bring-up ledger, item C).

**The 4K is built at every step.** Steps 3–5 are Dock steps, but each one also builds and places the 4K image in its highest mode (`square`) and records logic, CLS, and block RAM. If a Dock change pushes the 4K over, make that change conditional on the mode, so it is left out of the 4K build.

**Measuring.** The capture card is a V4L2 device. Use the webcam MCP's `measure_blink` on it if it opens the device, with an ROI over the screen or the square. Otherwise use ffmpeg on the device directly. Before any measurement, grab one frame and confirm there is a signal. If there is none, stop and say so. Do not measure the webcam instead. The screen's rate must match the published formula and the webcam's LED rate in the same run.

**When the 4K does not fit.** First try to make the video block smaller without changing the CPU. Record what each attempt saved. If it still does not fit, stop. Do not take a bring-up ledger cut in the same task. Report:
- logic, CLS, and block RAM with video `off`, at the first attempt, and at the smallest attempt
- what each shrink attempt did and what it saved
- how many CLS are still missing
- which bring-up ledger item (3, 4 or 5) would cover that, with its estimate

## Step 1 — Nano 4K: full-screen flash

Video timing and the TMDS output only, with no screen memory. The screen is white while the LED is on and black while it is off, from the same `ledState && armed` signal. The CPU does not change, so the blink formula stays.

The 4K has two PLLs, and HyperRAM uses one. Find out whether video can use the other, or share one, before writing the clocking. Record the HDMI pins from the Tang Nano 4K schematic. About 140 CLS are free on the item E place. If that is not enough, follow "When the 4K does not fit" above.

Measured, `modules` N=65536, SRAM load on bus 003:081 (`-m`, CRC Success). The flash disk was not written. The Dock was not built.

The second PLLVR takes the same 27 MHz port as the HyperRAM PLL. Its dedicated pin is 35, which schematic 3603 wires to HDMI TX2_P, and this device has no DCC. Sharing the HyperRAM PLL cannot make a 5× pixel clock: its spare outputs are 54, 27, and 18 MHz. A first bitstream divided 126 MHz by 5 for a 25.2 MHz pixel clock. The capture card showed green snow, not a picture. The pixel clock is now the 27 MHz port itself, and the serializer clock is 135 MHz (VCO 540, inside the C6/I5 window). 800×525 at 27 MHz is 64.3 Hz.

HDMI pins, schematic 3603, AC-coupled, TLVDS, placed as LVDS25, drive 3.5: clock 28/27, channel 0 30/29, channel 1 32/31, channel 2 35/34.

Fixed words, each with five ones, so repeating one holds the disparity at zero. They are the cnt=0 encodings. Black is byte 0x10, `0111110000`. White is byte 0xEF, `1011110000`. Those are the darkest and brightest bytes with that property; 0x00 and 0xFF have none. Control words: 00 `1101010100`, 01 `0010101011`, 10 `0101010100`, 11 `1010101011`. Channel 0 carries VSYNC/HSYNC. The other two carry control 00 during blanking. The clock channel is five ones then five zeros, LSB first.

The CPU is unchanged. Disk-boot N=5 still edges every 2936 bridge cycles, which is `466*5+606`. The N=65536 law is an edge every 1.131125 s, a full blink of 0.442038 Hz.

Place: logic 3730/4608 (81%; 3413 LUT, 317 ALU), registers 1921/3612, CLS 2164/2304 (94%, 140 free), block RAM 3/10. The 1-port place was 3648 logic and 2121 CLS (183 free), with the same 3 block RAM. Video used 43 CLS. Both PLLVR are used. Setup TNS is 0. `cpu_clk` Fmax is 16.963 MHz against 13.500. The worst setup slack is +2.744 ns.

Verilator, two frames: every active pixel black, then white. The screen follows `ledState && armed`, so it stays black until the arm word is stored.

Capture card UGREEN 15389, `/dev/video0`, not the webcam. A frame before the measurement was a locked picture. Across the clip the field is black (3,3,3) or white (209,209,209). On a white frame, 300 of 345600 pixels (0.087%) are below 180, a border from the stick's scale to 720×480. The stock blink analyzer measures red minus green, which is zero on both of these fields, so the screen rate is the luma of that same clip. Full-frame luma: 0.427215 Hz, period 2.340741 s, 21 edges, duty 0.510, FFT 0.416 Hz, SNR 903, confidence 0.9979, 721 frames at 30 fps. Same run, webcam `/dev/video2`, box `290,190` 50×50: 0.426458 Hz, period 2.344895 s, 21 edges, duty 0.497, FFT 0.416 Hz, confidence 0.9977. The two rates differ by 0.18%. Against 0.442038 Hz the screen is 3.35% slow, the same side as the 1-port LED clip (0.427067 Hz). The LED was not dark. Clips: `/home/lypanov/fpga/blink-measure/hdmi-flash-screen-fcf0/clip.mkv` and `/home/lypanov/fpga/blink-measure/hdmi-flash-led-fcf0/clip.mkv`.

## Step 2 — Nano 4K: the square

`square` mode adds a tiny screen memory: 32×24 big blocks of 20×20 pixels, one bit each, in one block RAM (the 4K has 7 free since item E). The CPU writes it through one I/O address. Blink5 sets one block when the LED goes on and clears it when it goes off. Blink5's loop gains a store, so recompute its formula before loading the board.

Proof: the square blinks at the formula rate, and every pixel outside it stays black in every captured frame.

Measured, `modules` N=65536, square mode. The disk was written to the external NOR at 0x200000 and read back matching. SRAM load on bus 003:081 (`-m`, CRC Success). The Dock was not built. No bitstream was written to flash. The 256 bytes at 0x1FFF00 were the same before and after the write.

Blink5 stores `MMT.light` at -80 (`0FFFFFFB0H`) after each toggle. Bit 0 is the pixel. The video block writes only block (15, 11), linear address 367, and leaves the other 767 bits at zero. The store is taken whether or not the arm word is in place. The pixel is shown only while armed, the same gate as the LED. Every image decodes a store to -80, and that store does not become a HyperRAM write. Disk-boot counted the screen pulse and did not see that address on the memory bus.

The screen memory is one SDPB, one bit wide. The write port is on `cpu_clk` and the read port is on the pixel clock. Square uses the flash timing and the same fixed TMDS words. It does not paint from the LED wire. The picture is that one block on black.

Disk-boot periods: N=5 is 3110, N=6 is 3576, N=8 is 4508. That is `466*N+780`. The skip term is still 466. The store added 174 cycles on the toggle. N=65536 is an edge every 30,540,556 cycles, 1.131132 s, a full blink of 0.442035 Hz. The delay word is `60000001H`. The disk is 17928 bytes, checksum `6bae42b7`, arm word `cab24f52`.

Place: logic 3779/4608 (82%; 3457 LUT, 322 ALU), registers 1944/3612, CLS 2161/2304 (94%, 143 free), block RAM 4/10. The flash place was 3730 logic, 2164 CLS, and 3 block RAM. The extra block is the screen SDPB. Setup TNS is 0. The worst setup slack is +3.405 ns. `cpu_clk` Fmax is 14.753 MHz against 13.500.

Verilator: the flash frames are still black, then white. The square frames stay black while unarmed, stay black when the bit is clear even with the LED wire on, then light exactly the 20×20 block at (15, 11), and go black again when the bit clears.

Capture card UGREEN 15389, `/dev/video0`, not the webcam. The frame grabbed before the measurement was green snow: the card had not locked. The next frame was a locked picture. A lit frame has exactly 440 pixels above luma 80, at x=338..359 and y=220..239, about (205,205,205) on a field of (3,3,3). That box is the 20×20 block after the stick scales 640 to 720. In all 962 frames of the clip, no pixel above luma 80 sits more than 8 pixels outside that box. The pixels that reach luma 50 are on the edge of the block.

The stock analyzer measures red minus green, which is zero on both of these fields, so the square rate is the count of those white pixels. The first white stretch is 24 frames, while the card was locking. After that the halves are 35 frames, sometimes 36. Twelve rising edges span 773 frames. At 30 fps that is 0.4269 Hz, period 2.342 s. Same run, webcam `/dev/video2`, box `290,190` 50×50: 0.426841 Hz, period 2.342790 s, 24 edges, duty 0.497, FFT 0.428 Hz, SNR 79.5, confidence 0.9978. The two rates differ by under 0.02%. Against 0.442035 Hz the square is 3.42% slow, the same side as the flash measurement. The LED was not dark. Clips: `/home/lypanov/fpga/blink-measure/hdmi-square-screen-fcf0/clip.mkv` and `/home/lypanov/fpga/blink-measure/hdmi-square-led-fcf0/clip.mkv`.

## Step 3 — Dock: full-screen flash

The same as step 1, on the Dock's HDMI pins (`docs/primer20k/board-notes.md`, "HDMI / DVI-TX"). The screen is white while the LED is on and black while it is off, from `cpu_led`, which is already `ledState && armed`. Square is the next step. The DDR3 PLL is unchanged.

Measured, `ddr3modules` N=65536, SRAM load on bus 003:078 (`-m` only). Idcode `0x81b`, GW2A-18. Bus 003:081 is the Nano and stayed on the square image. Nothing was written to flash.

Pins, from the Dock schematic and the NESTang v0.4 constraints: clock G16/H15, channel 0 H14/H16, channel 1 J15/K16, channel 2 K14/K15. Bank 0 is 3.3 V, so the pairs are LVCMOS33D, drive 8, no pull. `TLVDS_OBUF` rejects that IO type. The serializer drives the positive port, and both balls of the pair are constrained on that port. The negative port is tied off.

Gowin replaces the pin file when a second cst is added. Flash mode writes one file from `ddr3.cst` plus the HDMI constraints and adds only that file. The placed report names `ddr3_hdmi.cst`. Clock is H11, the blink pin is L14, and the DDR3 balls stay SSTL15.

The pixel clock is the 27 MHz port. The serializer is a second rPLL at 135 MHz (FBDIV 4, ODIV 4, VCO 540). The DDR3 rPLL stays at 387 MHz out and 96.75 MHz for `pclk`. Two rPLLs of four.

The blink count is the 1-port bridge law. The store added 174 cycles, so the edge is `466*N+780`. At the Dock CPU clock, 24.1875 MHz, those 174 cycles are 7 µs. N=65536 is an edge every 1.26266 s, a full blink of 0.39598 Hz. The delay word is `60000001H`. The older `576*N+788` count is the 2-port image, in controller clocks. The stand-in does not finish this image's clear loop, and the PHY run is reserved for a DDR3 failure, so that constant was left as published.

Place: logic 5141/20736 (25%; 4661 LUT, 480 ALU), registers 2334/16173, CLS 3588/10368 (35%), block RAM 8/46, OSER10 4, rPLL 2/4. Setup TNS is 0. The worst setup slack is +1.251 ns. `pclk` Fmax is 110.070 MHz against 96.749. `cpu_clk` Fmax is 26.587 MHz against 24.187.

The 4K square place, rebuilt and left unloaded: logic 3779/4608 (82%; 3457 LUT, 322 ALU), CLS 2161/2304 (94%, 143 free), block RAM 4/10. Same counts as step 2. Setup violations 0.

The first SRAM load stayed in DDR3 training. UART on FTDI channel B, 115200 8N1: `F` was `4B`, PC `0080`, and L14 stayed dark. The load that was measured trained. `F` is `AB`, the mask is `FFFFFFFFFF`, and the PC walks the delay loop (`2214` through `2238`).

Capture card UGREEN 15389, `/dev/video0`. Before that load the card showed the Nano's square on green noise, then a flat black field while training held. After it, the field is black (3,3,3) or white (209,209,209) across the whole frame. Six rising edges give five periods, each 151 or 152 frames at 60 fps. The mean period is 2.523 s, 0.3963 Hz. Same run, webcam `/dev/video2`, the Dock LED near (320, 52): eleven halves, ten of 19 frames and one of 18, at 15 fps. The mean half is 1.261 s, 0.3965 Hz. The two rates differ by under 0.1%. Against 0.39598 Hz the screen is 0.08% off. The Nano LED in the same frame, near (206, 192), keeps its own half of about 1.17 s. Clips: `/home/lypanov/fpga/blink-measure/hdmi-dock-flash-screen-fcf0/clip.mkv` and `/home/lypanov/fpga/blink-measure/hdmi-dock-flash-led-fcf0/clip.mkv`.

## Step 4 — Dock: the square

The same as step 2, on the Dock. Same Blink5. Also build the 4K at `square` and record its size.

## Step 5 — Dock: the counter

`text` mode adds a built-in 8×8 font and a small text area (for example 40×15 characters), also written by the CPU through I/O addresses. Blink5 counts its blinks and writes the count in decimal after each blink. On the 4K those stores are dropped. Recompute the loop formula for both boards, because the decimal conversion runs on both.

Proof:
- the host draws the expected frame with the same font, and the captured frame must match it
- the number goes up by exactly one per blink
- the rate matches the new formula

Also build the 4K at `square` and record its size. If the counter code pushes the 4K over, follow the "4K is built at every step" rule.
