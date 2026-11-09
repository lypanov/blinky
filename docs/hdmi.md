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

## Step 3 — Dock: full-screen flash

The same as step 1, on the Dock's HDMI pins (`docs/primer20k/board-notes.md`, "HDMI / DVI-TX"). The NESTang demo already proved this port and the capture path on 3 Nov. Also build the 4K at `square` and record its size.

## Step 4 — Dock: the square

The same as step 2, on the Dock. Same Blink5. Also build the 4K at `square` and record its size.

## Step 5 — Dock: the counter

`text` mode adds a built-in 8×8 font and a small text area (for example 40×15 characters), also written by the CPU through I/O addresses. Blink5 counts its blinks and writes the count in decimal after each blink. On the 4K those stores are dropped. Recompute the loop formula for both boards, because the decimal conversion runs on both.

Proof:
- the host draws the expected frame with the same font, and the captured frame must match it
- the number goes up by exactly one per blink
- the rate matches the new formula

Also build the 4K at `square` and record its size. If the counter code pushes the 4K over, follow the "4K is built at every step" rule.
