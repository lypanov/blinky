# Screen and boot (to-do items 32–47)

The write-ups for `docs/todo.md` items 32–47, planned on 10 Nov 2026. The rules in `docs/strategy.md` apply to every item: each one keeps the LED blinking at a rate published before the board is trusted, a failed check leaves the LED dark, and Oberon code is preferred to FPGA logic. Both boards are built at every item. If the Nano 4K does not fit, stop and name the next open item in `docs/bringup-ledger.md`.

## The direction

The 4K should do more than blink a square. Its space is tight (CLS 2222/2304 after item 28), so the drawing moves into Oberon and the FPGA keeps only two plain things: a small status register, and a bitmap the video reads out. Text, fonts and trap messages are then Oberon code and files on the disk, with no extra FPGA.

Two screen modes, chosen by one bit:

- **Status mode.** Eight huge blocks across the screen show an 8-bit status byte. Used before Oberon is running: the ROM bootstrap shows how far the boot got. Big enough to read by eye and trivially by the capture card.
- **Bitmap mode.** A 1-bit-per-pixel picture in block RAM, drawn by Oberon. 180×120 on the 4K, shown at 4× on 720×480. 512×384 on the Dock, shown at 2× on 1024×768. Block RAM is the chip's built-in memory; one block holds 2 KB at 1 bit wide. 180×120 is 2 blocks of the 4K's 10. 512×384 is 12 of the Dock's 46.

The status blocks may show before the arm word. The LED stays the proof of a pass: it lights only after the arm word, and a failed check leaves it dark. The square and the bitmap still come on only after the arm word.

From item 39 on, the book's own modules are used (`Display`, `Fonts`, `Texts`, `Oberon`, `FileDir`) rather than code of our own. The book's `Display` has the width, height and screen address as constants, so each board gets its own constants and the rest is unchanged.

## Item 32 — the 4K at 720×480

The 4K sends 640×480 at 27 MHz with 800×525 totals, 64.3 frames a second. The capture card records it as 720×480 and stretches 640 pixels to 720, so the 20-pixel square measured 22 pixels wide with soft edges (`docs/hdmi.md`, steps 1 and 2). The Dock at 1024×768 is already captured pixel for pixel.

Change the 4K to the standard 720×480 at 60 Hz (CEA 480p: 858×525 totals at 27 MHz, 59.94 Hz). Same 27 MHz clock, so no PLL change; only the line and frame counts. Before building, list the capture card's modes (`v4l2-ctl --list-formats-ext`) and record them here.

Proof: the LED still blinks at 0.500 Hz. The capture card records 720×480, and the lit square is exactly 400 pixels, 20×20, with no pixel above luma 50 outside it. The Verilator frame check (`sim/run_frame_check.sh`) is updated to 720×480 and passes.

The capture card was listed before the build, 11 Nov 2026, `v4l2-ctl -d /dev/video0 --list-formats-ext`. It is the UGREEN 15389 on USB `usb-0000:00:0d.0-3.1.3`. Two formats, YUYV and MJPG, and both list the same sizes. 2560×1440 is 30, 20, and 10 frames a second. Every other size is 60, 50, 30, 20, and 10: 1920×1080, 1600×1200, 1360×768, 1280×1024, 1280×960, 1280×720, 1024×768, 800×600, 720×576, and 720×480. The stick was sitting at 2560×1440 MJPG.

The Nano timing is CEA 480p, counted from the start of the sync pulse, with negative sync. Horizontal 62 + 60 + 720 + 16 = 858. Vertical 6 + 30 + 480 + 9 = 525. `hs` is `hx >= 62`, `vs` is `vy >= 6`, and the active pixels are hx 122..841 and vy 36..515. 858×525 at 27 MHz is 59.94 Hz. The pixel clock is still the 27 MHz port, and the video PLL is still 135 MHz. The 32×24 grid of 20×20 blocks stays at the top left, hx 122..761 and vy 36..515. The 80 columns past it stay black. The square is still block (15, 11), pixels (300, 220). The Dock timing branch is unchanged, so that bitstream was not rebuilt.

Verilator, `sim/run_video.sh`. Two frames, 720×480, black then white. The square is the 20×20 block at (15, 11), and every other active pixel stays black. `sim/run_frame_check.sh` passes. The Nano frame starts at CPU cycle 225225. Flash off is black. Flash on is 345600 white pixels. Square on is 400. Blank is black. The Dock pictures are unchanged: the frame still starts at CPU cycle 404343, and the square is still 400. A wrong picture still differs.

4K place, `modules_n1000`, square. Against the item 31 place this uses 14 more LUT (the ALU stays 354) and 50 more CLS. Registers stay 2026. Block RAM stays 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). Logic 4081/4608 (89%; 3727 LUT, 354 ALU), CLS 2234/2304 (97%, 70 free). DSP 2/8, one `MULT36X36`, site `DSP_R19[1]` (R19C11). The instruction ROM is `BSRAM_R10[2]`. The screen bitmap is `BSRAM_R10[9]`. Setup and hold violated endpoints 0. Worst setup slack +0.688 ns. Worst hold slack +0.017 ns, `armed_s1` to `armed_s1_s0`. `cpu_clk` Fmax is 15.231 MHz against 13.500. The HyperRAM `clkdiv` Fmax is 55.144 MHz against 27.000. The bitstream is `gowin/impl/pnr/modules_n1000.fs`, 1772222 bytes, sha256 `b1a1de54dab2022941ff92933ad15b401ff4869341404dedce049c1321a5fa1c`.

The Nano is USB port `3-3.3`, bus 003 device 012, idcode `0x100981b`, GW1NSR-4C. Two SRAM loads, each `openFPGALoader -m`, each `write to ram`, Load SRAM 100%, CRC check Success. `ftdi_sio` held both interfaces of `3-3.3`. The reset was not busy, so the driver stayed bound and VBUS stayed on. The NOR was not rewritten. Nothing was written to flash.

The lit core of the Nano LED is x 147..155, y 234..253. The item 31 box `145,228` 16×16 covers the top of that core and misses the lower rows. The box used here is `145,232` 14×24. Webcam `/dev/video2`. The reload is inside the clip, so the opening edges are the previous image. After the boot goes dark, the first two rise-to-rise intervals are 2.00117 s and 2.00117 s, 0.49971 Hz. Against 0.500 Hz each is 0.058% slow. From the third rise the median interval is 1.00058 s, 0.99942 Hz, fourteen intervals: thirteen of that median and one of 1.03394 s, which is one camera frame. Against 1.000 Hz the median is 0.058% slow. That is the item 31 half-write, still in force. The 1000 ms pair on the disk is still `E8 03 00 00 18 FC FF FF`. Clip: `/home/lypanov/fpga/blink-measure/cea-480p-nano-reload/clip.mkv`, 721 frames, 29.983 fps.

Done. The capture card is on the Nano. 11 Nov 2026, `/dev/video0`, YUYV, 720×480, 60 frames a second, 240 frames, `/home/lypanov/fpga/blink-measure/cea-480p-nano-screen/cap.rgb`. Five opening frames are full-frame noise and are discarded. Of the rest, 157 are black and 78 are lit. Each lit frame has exactly 400 pixels above luma 50. They are x=300..319, y=220..239, a 20×20 box, and every one of those pixels has luma 255. The one-pixel ring around the box has luma 0. No pixel above luma 50 sits outside the box. There are no digits. Complete on and off runs are 30 frames, 0.500 s, with one off run of 31 frames. That is the 1 Hz phase already in force after the third rise. The 0.500 Hz proof remains the two 2.00117 s LED intervals above.

The Dock file is the item 31 image, `gowin/primer20k/impl/pnr/ddr3modules_n1000.fs`, 7261998 bytes, sha256 `328d3a13e8f08b611185e34563b039952f765a57237e63990cd41b1e021ffeab`. The UART disk is that same image, `disk-hw-1000.bin`, 47124 bytes, sha256 `511e2b96a00ad3489abd1f7260fa7d1b4ae7a01cfba9dfd140251d0a9c71e168`. The Dock is USB port `3-3.1.1`, bus 003 device 013. Three SRAM loads, each `openFPGALoader -m`, each `write to ram` and Load SRAM 100%. Each trained at `C.0440`, lanes `000C` `000A`, E0 `A55A`, G `A55A`, F `AB`, and the mask became `FFFFFFFFFF` after the disk. Nothing was written to the Dock flash. The HDMI cable stayed on the Nano. One other SRAM load trained and then stayed at PC `0000` with an empty mask. It was loaded again, and it is not one of the three.

The blinking LED moved. The item 31 box `248,32` 18×16 sits above the core. The box used here is `250,44` 16×26. Webcam `/dev/video2`. This image is still the 1000 ms pair, and it still halves the delay after the third rise, so the first two intervals are 2 s and every later interval is 1 s.

The first load, `/home/lypanov/fpga/blink-measure/cea-480p-dock/load3/clip.mkv`, 30.011 fps. The first two rise-to-rise intervals are 1.99924 s and 1.99924 s. Against 2.000 s each is 0.038% short. From the third rise the edge rate is 0.998302 Hz, period 1.001701 s, median 0.999618 s, duty 0.5174, 33 rising edges, confidence 0.9972, FFT 1.013296 Hz, SNR 859. Against 1.000 Hz the edge rate is 0.170% slow, and the median interval is 0.038% short of 1 s.

The second load, `/home/lypanov/fpga/blink-measure/cea-480p-dock/load5/clip.mkv`, 30.004 fps. The intervals are 1.99970 s and 1.99970 s. Against 2.000 s each is 0.015% short. From the third rise the edge rate is 0.998484 Hz, period 1.001518 s, median 0.999852 s, duty 0.5240, 21 rising edges, confidence 0.9975, FFT 1.020244 Hz, SNR 776. Against 1.000 Hz the edge rate is 0.152% slow, and the median interval is 0.015% short of 1 s.

The third load, `/home/lypanov/fpga/blink-measure/cea-480p-dock/load6/clip.mkv`, 30.004 fps. The intervals are 1.99976 s and 1.99976 s. Against 2.000 s each is 0.012% short. From the third rise the edge rate is 0.998369 Hz, period 1.001634 s, median 0.999880 s, duty 0.5144, 20 rising edges, confidence 0.9974, FFT 1.006511 Hz, SNR 946.6. Against 1.000 Hz the edge rate is 0.163% slow, and the median interval is 0.012% short of 1 s.

The maintainer confirmed the Nano S1 pause by hand. The Dock button was not tested.

## Item 33 — the status register

A 9-bit register at one new I/O address below the book's window (next free word under −80; record the choice). Bits 0–7 are the status byte. Bit 8 picks the screen mode: 0 for status, 1 for the bitmap (item 36). Until item 36, bit 8 = 1 shows today's square picture. The video shows the status byte as 8 blocks across the middle of the screen, bit 7 on the left; a set bit is a white block. The register resets to 0 (status mode, all dark).

Nine flip-flops and a compare on the pixel counter: the smallest screen hardware possible. Record the 4K CLS cost.

Proof: the bootstrap writes a known byte, `0xA5`, as its first store. The capture card reads `10100101` in the blocks. Then the boot continues, Blink sets bit 8, and the square blinks at 0.500 Hz with the LED. A Verilator frame check of the status picture against a host-drawn picture.

The address is −84, `0xFFFFFFAC`. −80 is the screen block. −76 is the reserved blink count, above −80, so it is not the next free word under −80. The store is a word store of bits 8–0. A byte store is not decoded. There is no load path. Reset is 0.

The nine flops sit on the CPU clock. The Dock pixel clock is not an integer multiple of the CPU clock, so the pixel clock samples them. The picture is eight 80×160 blocks, one per bit, bit 7 on the left. On the Nano they are the middle band of the 720×480 frame: x 0..639 grouped by fours of the 20-pixel columns, y 160..319. The same active coordinates are the top-left of the Dock's 1024×768. `0xA5` is `10100101`, white black white black black white black white. Until item 36, bit 8 selects today's square, still 20×20 at x 300..319, y 220..239, and still gated by the arm word. Blink stores `0x1A5` once, after the arm prologue, so the status byte stays `0xA5` and the mode bit sets.

`BootLoad` is 378 words of the 512-word ROM. Its first store is `SYSTEM.PUT(-84, 0A5H)`, before the stack and the check, on both the NOR bootstrap and the Dock bootstrap. Blink5's body stores `0x1A5` before `Files.Old`. The rate pair on the disk is still `E8 03 00 00 18 FC FF FF`. The first two rise-to-rise intervals are 2 s. The third rise halves the delay, so later edges are 1 Hz.

Verilator, `tools/run_verilator_sim.sh`, exit 0. The NOR disk boot and the UART disk boot both see the first status word `0x0A5` before any memory store, and a blink that is not a halt sets bit 8. The frame check matches the host-drawn status picture on both timings: 51200 white pixels. A wrong byte differs. With `0x1A5` the square is the same 400 pixels as item 32, and the Dock digits still match.

4K place, `modules_n1000`, square. Against item 32 this uses 120 more LUT (the ALU stays 354) and 16 more CLS. Registers 2045, which is item 32's 2026 plus the nine flops, their nine pixel-clock samples, and the grid window. Logic 4201/4608 (92%; 3847 LUT, 354 ALU), CLS 2250/2304 (98%, 54 free). Block RAM stays 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). DSP 2/8, one `MULT36X36`, site `DSP_R19[1]` (R19C11). The instruction ROM is `BSRAM_R10[5]`. The screen bitmap is `BSRAM_R10[9]`. The same-edge hold from the CPU clock into the pixel sample was −0.757 ns. That check is not the requirement: the word changes and then sits, and the pixel clock samples it on a later edge. `gowin/blinky.sdc` gives that path a hold multicycle of 1. After that, setup and hold violated endpoints are 0. Worst setup slack +0.920 ns. Worst hold slack +0.408 ns. `cpu_clk` Fmax is 13.669 MHz against 13.500. The HyperRAM `clkdiv` Fmax is 70.940 MHz against 27.000. The bitstream is `gowin/impl/pnr/modules_n1000.fs`, 1772222 bytes, sha256 `076838d37aefff8fdb58a0694017f7e12b9b7ec437d0194901a4c05bdbf65831`.

The disk is 47124 bytes, checksum `1f5171c5`, arm word `be4d7c20`, sha256 `7692c7a32e8498db9165b9c19783a86fa8a7b3f167e39583be6104ac67c5be57`. The NOR write was the data file only, at `0x200000`, bus 003 device 012. JEDEC `856016`. The read-back matches. The 256 bytes at `0x1FFF00` are unchanged. `ftdi_sio` held both interfaces of `3-3.3`. The write and the SRAM load did not find the reset busy, so the driver stayed bound and VBUS stayed on. SRAM load `openFPGALoader -m`, `write to ram`, Load SRAM 100%, CRC check Success. Idcode `0x100981b`. Nothing was written outside `0x200000`–`0x3FFFFF`.

The capture card stayed on the Nano. 11 Nov 2026, `/dev/video0`, YUYV, 720×480, 60 frames a second, 1920 frames, `/home/lypanov/fpga/blink-measure/status-reg-9281/cap.rgb`. After the load, 26 frames are the status picture. Each has exactly 51200 pixels of luma 255, and they are the eight blocks above: row centers at y=200 read 255, 0, 255, 0, 0, 255, 0, 255. The rest of each of those frames is luma 0 except 800 pixels at luma 2. Then 63 dark frames, bit 8 set and the square still off. Then the square. Each lit square frame has exactly 400 pixels of luma 255 at x=300..319, y=220..239, and the one-pixel ring is luma 0. The first two on runs and the first two off runs are 60 frames, 1.000 s, so the rise-to-rise is 2.000 s. Later complete runs are 30 frames, 0.500 s.

The old Nano LED box `145,232` 14×24 no longer covers the lamp. The lit core is x 141..159, y 199..207. The measured box is `136,194` 27×16. Webcam `/dev/video2`, 29.996 fps, `/home/lypanov/fpga/blink-measure/status-reg-9281/led/clip.mkv`. The reload is inside the clip. After the boot goes dark, the first two rise-to-rise intervals are 2.00027 s and 2.00027 s, 0.49993 Hz. Against 0.500 Hz each is 0.013% slow. From the third rise the median interval is 1.00013 s, 0.99987 Hz, six intervals: five of that median and one of 1.03347 s, which is one camera frame. Against 1.000 Hz the median is 0.013% slow.

Dock place, `ddr3modules_n1000`, text, `place_option` 0, `route_option` 1. Logic 5779/20736 (28%; 5257 LUT, 522 ALU), CLS 4091/10368 (40%), registers 2988. BSRAM 2/46. The instruction ROM stays `BSRAM_R46[4]`. The multiplier stays `DSP_R19[1]`. Setup and hold violated endpoints 0. Worst setup slack +0.639 ns. Worst hold slack +0.263 ns. `pclk` Fmax is 103.122 MHz against 96.749. `cpu_clk` Fmax is 33.283 MHz against 24.187. The pixel clock Fmax is 99.025 MHz against 64.800. `route_option` 2 on this netlist does not train: PC `0080`, E0 `FFFF`, G `0000`, F `48`. Those loads are not counted. The bitstream that trained is `gowin/primer20k/impl/pnr/ddr3modules_n1000.fs`, 7261998 bytes, sha256 `1f8bcaa7d26c73e3c265cbcd0e93a90f272614eec235955889b3ae529530a2f6`. The sector-word flops `secWordR` are in the same group as `spi`, `body`, and `secAddr`, `R[2:22]C[20:40]`.

The HDMI cable stayed on the Nano. The Dock proof is the LED. Three SRAM loads of that file, each `openFPGALoader -m`, each `write to ram`, Load SRAM 100%. The Dock is USB port `3-3.1.1`, bus 003 device 013. Each trained at `C.0440`, lanes `000C` `000A`, E0 `A55A`, G `A55A`, F `A8`, and the mask became `FFFFFFFFFF` after the disk. The UART open detaches interface B. It was still detached at the end; rebinding needs root. Interface A stayed on `ftdi_sio`. Nothing was written to the Dock flash. The lit core moved. The box used here is `244,34` 19×26, webcam `/dev/video2`.

The first load, `/home/lypanov/fpga/blink-measure/status-reg-9281/dock-r1/led/clip.mkv`, 29.994 fps. The intervals are 2.00040 s and 2.00040 s, then twenty of 1.00020 s. Against 2.000 s each is 0.020% long. Against 1.000 Hz that later interval is 0.020% slow. The second load, `dock2/led/clip.mkv`, 29.997 fps. The intervals are 2.00021 s and 2.00021 s. Against 2.000 s each is 0.010% long. From the third rise, twenty intervals: nineteen of 1.00011 s and one of 1.03344 s, one camera frame. The third load, `dock3/led/clip.mkv`, 29.990 fps. The intervals are 2.00064 s and 2.00064 s, then twenty of 1.00032 s. Against 2.000 s each is 0.032% long. Against 1.000 Hz that median is 0.032% slow.

Done. The Dock button was not tested. Nano S1 was already confirmed and was not repeated.

## Item 34 — boot stage codes

The bootstrap writes a numbered code into the status byte as each stage before Oberon passes. On the 4K: started, NOR read, disk magic, version and build, checksum, core copied, init stream copied, jumping to the inner core. On the Dock: the same, with DDR3 trained and UART receive in place of the NOR read. The inner core writes one more code just before `Modules.Load("Blink5")`. Publish the code table in this file before building.

Proof: a capture card recording of a good boot shows the codes in order, ending in bitmap/square mode with the LED at 0.500 Hz. A disk with the build byte flipped stops at the build code, and a disk with one payload byte flipped stops at the checksum code. In both the LED stays dark, and the recording names the stage. Verilator checks the same final code for each case.

The code is one byte at −84, bit 7 on the left. Bit 8 stays clear until Blink stores the inner-core code with the mode bit set (`0x10B`), which is the square. A failed stage leaves its code up and branches to the halt word. The build byte is header offset 8, flipped by XOR 1 (`0xE1` becomes `0xE0`). The payload byte is file offset 40, also XOR 1.

`BootLoad` writes the code, then does the work. The 4K then waits 300000 iterations, so a stage that is only a compare still fills a capture frame. The started code waits three times, about three seconds. One second is what the capture card spends locking onto the new picture, and a single wait never reached the recording. The Dock skips that wait. Its receiver holds eight words, and the host is already sending.

The core stage is `LoadFromDisk`: the linked image copied to address 0. The init stage is the stores after that copy. The image already contains its variables, so there is no pair list. The stores are the checksum at 8, `MemLim` at 12, the stack origin at 24, and the heap sentinel at `MemLim`. The jump stage is the branch to address 0. Oberon then stores 11 and calls `Modules.Load("Blink5")`.

| Code | Bits, bit 7 on the left | 4K | Dock |
|---:|---|---|---|
| 1 | 00000001 | started | started |
| 2 | 00000010 | NOR read | |
| 3 | 00000011 | | DDR3 trained |
| 4 | 00000100 | | UART receive |
| 5 | 00000101 | disk magic | disk magic |
| 6 | 00000110 | version and build | version and build |
| 7 | 00000111 | checksum | checksum |
| 8 | 00001000 | core copied | core copied |
| 9 | 00001001 | init stream copied | init stream copied |
| 10 | 00001010 | jumping to the inner core | jumping to the inner core |
| 11 | 00001011 | before `Modules.Load("Blink5")` | before `Modules.Load("Blink5")` |

A good boot's final store is `0x10B`. A flipped build byte stops at 6. A flipped payload byte stops at 7.

`tools/run_verilator_sim.sh` exits 0. The NOR sequence is 1, 2, 5, 6, 7, 8, 9, 10, 11, then `0x10B`. Code 1 is stored at bridge cycle 10 and code 2 at cycle 81000566, three holds, 3.000 s at 27 MHz. The final word is at cycle 305599056. A flipped build byte halts at cycle 158407556 with final word `0x06` and the LED dark. A flipped payload byte halts at cycle 200600214 with final word `0x07` and the LED dark. The UART image does not hold. It reaches `0x10B`, and the same two disks halt at cycles 7268 and 15080444 with words `0x06` and `0x07`, LED dark. `BootLoad` is 430 of 512 words.

4K place, `modules_n1000`, square. Logic 4129/4608 (90%; 3775 LUT, 354 ALU), registers 2045, CLS 2230/2304 (97%, 74 free). Block RAM 4/10 (2 SDPB, 1 SDPX9B, 1 pROM). The instruction ROM is `BSRAM_R10[4]`. The screen bitmap is `BSRAM_R10[9]`. DSP 2/8, one `MULT36X36`, site `DSP_R19[1]` (R19C11). Setup and hold violated endpoints 0. Worst setup slack +2.285 ns. Worst hold slack +0.232 ns. `cpu_clk` Fmax is 14.236 MHz against 13.500. The HyperRAM `clkdiv` Fmax is 67.349 MHz against 27.000. The bitstream is `gowin/impl/pnr/modules_n1000.fs`, 1772222 bytes, sha256 `096ed6fcb9a7e15f7d7f7abceb45bf2a0191186c784389adeb55b6fbb9f21191`. CLS fits. Ledger item 9 was not taken.

The disk is 47124 bytes, checksum `e7bdfa06`, arm word `46a1f7e3`, sha256 `a68cd634669e6ed3efc64fdc1e6f9445a74a81ee299ad924efe0e239068dfcfa`. The rate bytes at `0xA974` are `e8 03 00 00 18 fc ff ff`, 1000 ms and its negation. The NOR write was the data file only, at `0x200000`, bus 003 device 012. JEDEC `856016`. The read-back matches. The 256 bytes at `0x1FFF00` are unchanged. SRAM load `openFPGALoader -m`, Load SRAM 100%, CRC check Success. Idcode `0x100981b`. Nothing was written outside `0x200000`–`0x3FFFFF`.

A single one-second hold of code 1 never reached the capture. Two recordings of that image are black until code 2. The started code is therefore held three times. The recording of that image is `/home/lypanov/fpga/blink-measure/boot-stage-6fe7/good3/hdmi.yuyv`, 11 Nov 2026, `/dev/video0`, YUYV, 720×480, 60 frames a second, 1920 frames. After the load the codes are 1, 2, 5, 6, 7, 8, 9, 10, 11, then the square. Code 1 is 118 frames (1.967 s) and is only the rightmost block, x 560..639, y 160..319, exactly 12800 pixels above luma 180. Each later lit block is the same 12800. The runs are 59, 58, 59, 96, 89, 60, 72, and 18 frames: 0.983 s, 0.967 s, 0.983 s, 1.600 s, 1.483 s, 1.000 s, 1.200 s, and 0.300 s. The square is exactly 400 pixels at x 300..319, y 220..239. Its first two rise-to-rise intervals are 120 frames, 2.000 s, and the third is 60 frames, 1.000 s.

The lit core on `/dev/video2` is x 145..155, y 197..205, 961 frames at 30 frames a second, `good3/led.mkv`. The first two rise-to-rise intervals are 60 frames, 2.000 s, and the third is 30 frames, 1.000 s. That is 0.500 Hz, then 1.000 Hz.

The build-byte disk differs from the good file in one byte, offset 8, `E1` to `E0`. The write used the same window and the same guard. The read-back matches, and the 256 bytes at `0x1FFF00` are unchanged. The recording `bad-build/hdmi.yuyv` shows 1, 2, 5, then 6 held for the remaining 13.450 s. A frame of that hold has exactly two lit blocks, the `00000110` pair, 12800 pixels each, and the square is dark. The webcam `bad-build/led.mkv` has no rise. The red mean in the same box stays at most 11.5; the good clip's lit mean is about 130.

The payload-byte disk differs in one byte, offset 40, `00` to `01`. Same window, same guard, read-back matches. `bad-byte/hdmi.yuyv` shows 1, 2, 5, 6, then 7 held for the remaining 10.467 s. A late frame is the `00000111` triple. `bad-byte/led.mkv` has no rise, and the same box stays at most 11.5. The good disk was written back afterwards. The read-back matches, the guard is unchanged, and a final SRAM load of the good bitstream reports CRC check Success.

Dock place, `ddr3modules_n1000`, text, `place_option` 0, `route_option` 1. Logic 5852/20736 (29%; 5330 LUT, 522 ALU), CLS 4104/10368 (40%), registers 2988. BSRAM 2/46 (1 SDPB, 1 pROM). The instruction ROM stays `BSRAM_R46[4]`. The multiplier stays `DSP_R19[1]` (R19C11). The screen bitmap is `PLACE_BSRAM_R10[11]`. Setup and hold violated endpoints 0. Worst setup slack +1.066 ns. Worst hold slack +0.274 ns. `pclk` Fmax is 107.869 MHz against 96.749. `cpu_clk` Fmax is 32.283 MHz against 24.187. The pixel clock Fmax is 110.085 MHz against 64.800.

The image that trains has no registers on rows 48 or 49. An unconstrained place of this netlist put `dq_out`, `dq_oen`, `dqs_oen`, `dm_out_1`, and `dm_out_7` there, and the eye never saw the test byte. Those flops are now grouped onto the trained rows: 38, 39, 40, and 43 for the data and masks, 45 and 47 for the output enables, columns 33–41, and `dm_out_3` at R54C32 beside `dqs_hold` at R54C28. One box packs every member onto its minimum row and column, so each group is a single row. The PC is grouped onto rows 38 and 40–44, columns 20–30, and it packed at column 20. Left free, this netlist puts the PC on rows 23–29. The millisecond counter is grouped onto row 8, columns 20–30, and it packed at columns 20–22. `secWordR_0` is at R2C35 and `btnLoad` is at R5C9. `got_s4` is at R4C16. `got_s0` stayed at R45C24. Rows 48 and 49 are empty.

Earlier places of this netlist are not counted. `route_option` 2 stays at PC `0080` with E0 `FFFF`, G `0000`, and F `4B`, lanes `000A` `000C`. `place_option` 1 ends at F `10` with E0 `0000`. `place_option` 2 ends at F `09` with E0 `0000`. Packing every write flop onto row 38 left the PC at `0004`. Packing the PC onto one row collapsed the eye. The item 33 bitstream, sha256 `1f8bcaa7d26c73e3c265cbcd0e93a90f272614eec235955889b3ae529530a2f6`, still trains on the same port. It was loaded again after those places: `C.0440`, lanes `000C` `000A`, E0 `A55A`, G `A55A`, F `A8`. No disk was sent then.

The bitstream in the tree is `gowin/primer20k/impl/pnr/ddr3modules_n1000.fs`, 7261998 bytes, sha256 `c382b0f6a7b20875fa416aad9be74f4b3f495b688f87c52fde5013f4abab0f6b`. The same bytes are at `/home/lypanov/fpga/blink-measure/boot-stage-6fe7/dock-led/ddr3modules_n1000.fs`. A place of this netlist from the committed floorplan, `place_option` 0 and `route_option` 1, reproduces every configuration line and checksum `0xDE3F`. The header line is the place time `Wed Nov 11 13:31:04 2026`, so that sha256 is this file. `tools/gowin_build.sh` defaults this image to `route_option` 1. The disk is the same one as the Nano proof: 47124 bytes, checksum `e7bdfa06`, arm word `46a1f7e3`, sha256 `a68cd634669e6ed3efc64fdc1e6f9445a74a81ee299ad924efe0e239068dfcfa`.

Three SRAM loads of the trained file, each `openFPGALoader -m` on bus 003 device 013, each `write to ram`, Load SRAM 100%. Each waited at `C.0440` with lanes `000C` `000A`, G `A55A`, F `A8`, C0 `0B`, C1 `13`, BO `14`. The first load's E0 was `A55A`. The second and third loads' E0 was `A5AA` on every line of that image, while G stayed `A55A`. After the disk the mask was `FFFFFFFFFF` and the PC entered the core on all three. Nothing was written to the Dock flash. The HDMI cable stayed on the Nano.

The LED clip is a fourth SRAM load of the same file, taken while the camera ran. That load waited at `C.0440` with the same lanes, E0 `A5AA`, G `A55A`, F `A8`, and the mask became `FFFFFFFFFF`. The lit core is x 244..261, y 35..55. The box is `244,35` 18×21. Webcam `/dev/video2`, 1200 frames, 29.975 fps, `/home/lypanov/fpga/blink-measure/boot-stage-6fe7/dock-led/clip.mkv`. The reload is inside the clip. After the boot goes dark, the first two rise-to-rise intervals are 2.00167 s and 2.00167 s, 0.49958 Hz. Against 2.000 s each is 0.083% long, and against 0.500 Hz each is 0.083% slow. From the third rise, eight intervals: seven of 1.00083 s and one of 1.03420 s, which is one camera frame. Against 1.000 Hz the median is 0.083% slow.

This item is not marked done. Interface B (`3-3.1.1:1.1`) is on `ftdi_sio`. Interface A stayed bound.

## Item 35 — the trap code in the status blocks

The trap entry at `MT[0]` (item 4) gets a handler that switches to status mode and writes a trap byte: the high bit set, then the trap number. No text yet. This is the fall-back for everything that follows, and the debugging aid for items 36–47.

Proof: a deliberately broken Blink indexes an array out of range. The capture card reads the index trap's code. The LED stays dark: the arm word is never stored. The good Blink is unchanged and blinks at 0.500 Hz.

## Item 36 — the bitmap in block RAM

The bitmap replaces the 32×24 grid. 180×120 on the 4K (2 block RAMs, 4× pixels), 512×384 on the Dock (12 block RAMs, 2× pixels). The CPU writes it as ordinary words at a fixed address. Bit 8 of the status register shows it. Blink draws its 20×20-screen-pixel square by hand with plain stores (5×5 bitmap pixels on the 4K, 10×10 on the Dock) at the same place as today.

Proof: the square blinks with the LED at 0.500 Hz. The capture card finds exactly the predicted lit box and nothing else. Verilator frame check against a host-drawn picture. Record 4K CLS and block RAM; if the write port does not fit, stop and name the ledger item.

## Item 37 — more heap

`MemLim` is a number the linker writes at address 12. Item 28 set it low on purpose. First measure how far the CPU's address path reaches into the HyperRAM (4K) and the DDR3 (Dock); record it. Then raise `MemLim` to the room the later items need (at least 64 KB of heap), with the bitmap address outside it.

Proof: Blink allocates and keeps a list of records filling the published size, checks every one, and the arm word depends on the count. A limit one block short leaves the LED dark at the predicted blink. The collector still runs.

## Item 38 — floating point

The book's `FAD`, `FSB`, `FML` and `FDV` instructions. Neither chip has a floating-point block; there are only the 18×18 multipliers. On both boards the CPU recognises the four instructions and traps to an Oberon routine that does the arithmetic in software. The Dock may get the book's hardware unit later; not in this item. The same `.rsc` runs on both boards.

Proof: Blink computes its wait as a `REAL` (for example `FLOOR(0.5 * 2000.0)`), and the arm word includes checks of all four operations against known results. A wrong result is a wrong rate or a dark LED. Published rate 0.500 Hz.

## Item 39 — the book's `Display`

The book's `Display` module, with this board's width, height and bitmap address as its constants. Blink draws the square with `Display.ReplConst` instead of its own stores.

Proof: the same square, the same lit box on the capture card, the same frame check, 0.500 Hz.

## Item 40 — the book's `Fonts`

`Fonts` loads a `.Fnt` file from the disk. The 4K uses a 4×6 font (3×5 letters; for example the public-domain Tom Thumb, converted to the book's format by a host script). The Dock uses the book's `Oberon10.Scn.Fnt`. Both files are on the same disk. Blink draws one fixed character with `Display.CopyPattern` beside the square.

Proof: the character's pixels match the host-drawn glyph exactly on the capture card. A disk with a damaged font file traps (item 35's code), with the LED dark.

## Item 41 — the book's `Texts`

Blink writes its count with `Texts.WriteInt` into a text and draws the line with the font. The Dock's hardware digit converter and glyph lookup retire. Needs item 38: `Texts` contains floating-point instructions.

Proof: the capture card reads the count on every on-edge, one higher each time, compared exactly against the host-drawn text. The LED stays at 0.500 Hz. Record the Dock logic freed by retiring the digit hardware.

## Item 42 — commands by name

The book's `Oberon.Call` and `Modules.ThisCommand`. The inner core starts Blink by the command string `Blink.Run` rather than by a fixed load, which also removes the `"Oberon"`→`"Blink5"` name patch if item 31 has not already.

Proof: the good string blinks at 0.500 Hz. A misspelt command name shows a known code in the status blocks and leaves the LED dark.

## Item 43 — the trap line on screen

The trap handler prints the book's one-line trap message on the bitmap with `Texts`: the trap number, the module and the position. If the screen and font are not ready yet, it falls back to item 35's status code.

Proof: two broken Blinks. One traps after the font is loaded: the capture card reads the exact line. One traps before: the status blocks show the code. The LED is dark in both.

## Item 44 — the book's file system

The disk becomes the book's layout: `FileDir`'s directory on 1 KB sectors, built on the host (Norebo, or a host script; record which). Our own disk format stays only for the bootstrap's header and checks, as in item 31.

Proof: Blink opens `Blink.Rate` through `FileDir` and blinks at that file's rate. Two disks with two rates blink at their two published rates. A disk with a damaged directory traps with a known code.

## Item 45 — the `Input` stand-in

The main loop polls the keyboard and mouse at −40 and −36. Nothing is wired there, so those two addresses read "no key, mouse still". On the Dock the UART can feed them later.

Proof: Blink reads both addresses through the book's `Input` module and the arm word depends on the "nothing" answer. An image where −40 reads ones leaves the LED dark.

## Item 46 — the main loop with Blink as a task

The book's `Oberon` module and its `Loop`. Blink becomes a background task installed with `Oberon.Install`, paced by its time-out. If the loop stops, the LED stops. On the 4K this headless Oberon is the goal.

Proof: the LED and the square blink at 0.500 Hz from the task. The status line or the screen shows the loop's count of turns rising. A task that never returns stops the blink at the predicted moment.

## Item 47 — the watchdog

A counter that must be reset by the main loop. If the loop stops for longer than a published time, the screen switches to status mode with a "hung" code. Hardware cost: one counter and a compare; record the 4K cost.

Proof: the stuck task from item 46 shows the hung code within the published time, with the LED stopped. The good image never shows it over a ten-minute run.

## Later

- The Dock's full 1024×768 screen from DDR3 (`docs/led-ladder.md`, steps 13–14).
- The book's hardware floating-point unit on the Dock.
- `Viewers` and the tiled desktop (`docs/led-ladder.md`, part 5).
