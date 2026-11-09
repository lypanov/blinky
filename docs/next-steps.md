# Next steps (to-do items 19–31)

The write-ups for `docs/todo.md` items 19–31. The rules in `docs/strategy.md` apply to every item: each one keeps the LED blinking at a rate published before the board is trusted, a failed check leaves the LED (and the screen) dark, and Oberon code is preferred to FPGA logic where it is not much slower. Both boards are built at every item. If the Nano 4K does not fit, follow the open items in `docs/bringup-ledger.md`.

## Item 19 — button gate on both boards, proved on hardware

PR #22 forced the LED off while Nano 4K button S1 was held, or while a UART "press" byte was latched. Its hardware check ran into trouble, so the first goal is to know the buttons really work. #22 is stacked on #20 and built on the Blink3 images. Re-do it on today's images instead of merging the old branch. Its pin findings still hold: on the 4K, S1 is package pin 14, active-low, 1.8 V; S2 (pin 15) stays reset.

On the Dock, use key S2 (ball T3, bank 4, 1.5 V, active-low; S1 is the reset) and the UART press. The UART press lets the Dock be tested end to end with nobody there: the host sends the byte, and the webcam and capture card must see the LED and the screen go dark, then come back in phase.

Proof: Verilator for both. On the Dock, the UART press measured on hardware. The button presses themselves need a person: leave the 4K S1 and Dock S2 checks written down as "needs a person", with exactly what to press and what to expect. Do not hold the item open waiting for them.

## Item 20 — screen check in Verilator

Tap the video module's pixel signal before the HDMI output. Write one frame to an image file at a chosen CPU cycle. Compare it with an image the host draws from what the frame should hold. Any difference fails. This is exactly reproducible, so it becomes a regression test for every screen mode (flash, square, counter) on both boards, and later screen work can be checked without a board.

Proof: the test passes on today's images and fails on a deliberately wrong expected image.

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
