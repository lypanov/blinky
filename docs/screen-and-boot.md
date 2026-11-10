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

## Item 33 — the status register

A 9-bit register at one new I/O address below the book's window (next free word under −80; record the choice). Bits 0–7 are the status byte. Bit 8 picks the screen mode: 0 for status, 1 for the bitmap (item 36). Until item 36, bit 8 = 1 shows today's square picture. The video shows the status byte as 8 blocks across the middle of the screen, bit 7 on the left; a set bit is a white block. The register resets to 0 (status mode, all dark).

Nine flip-flops and a compare on the pixel counter: the smallest screen hardware possible. Record the 4K CLS cost.

Proof: the bootstrap writes a known byte, `0xA5`, as its first store. The capture card reads `10100101` in the blocks. Then the boot continues, Blink sets bit 8, and the square blinks at 0.500 Hz with the LED. A Verilator frame check of the status picture against a host-drawn picture.

## Item 34 — boot stage codes

The bootstrap writes a numbered code into the status byte as each stage before Oberon passes. On the 4K: started, NOR read, disk magic, version and build, checksum, core copied, init stream copied, jumping to the inner core. On the Dock: the same, with DDR3 trained and UART receive in place of the NOR read. The inner core writes one more code just before `Modules.Load("Blink5")`. Publish the code table in this file before building.

Proof: a capture card recording of a good boot shows the codes in order, ending in bitmap/square mode with the LED at 0.500 Hz. A disk with the build byte flipped stops at the build code, and a disk with one payload byte flipped stops at the checksum code. In both the LED stays dark, and the recording names the stage. Verilator checks the same final code for each case.

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
