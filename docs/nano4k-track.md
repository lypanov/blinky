# Two boards, two tracks

This is a thinking document, not a to-do list. It answers two questions. How can the Nano 4K and the Primer 20K Dock grow into different systems without the project splitting in two? And how can the 4K fit a basic Oberon in a chip that is already full?

## The short answer

The Dock becomes the **workstation**: the book's machine, with the tiled desktop, following `docs/led-ladder.md`. The 4K becomes the **embedded Oberon**: the same Kernel, file system and module loader, but no graphics. Commands are typed on the PC and run on the board through the cable that is already plugged in. One button switches between a few modes, and the HDMI output shows a small text screen if there is room.

This is not a new idea. CFB Software's "Embedded Project Oberon" is a cut-down Oberon for small FPGAs. It keeps only the Kernel, the loader, the file system and the SD card and serial drivers, and drops the GUI, display, mouse and keyboard. The 4K track is that idea, with the serial cable replaced by something the 4K actually has.

## What the two boards share

**The same instruction set.** Both CPUs must run the same compiled `.rsc` files. If the 4K's CPU drops a costly instruction (divide, for example), it has to *trap* it and finish the work in software. That way the compiler and the module files never fork. This is the one rule that keeps the two tracks one project.

**The same inner core.** `Kernel`, `FileDir`, `Files` and `Modules` are the same source on both boards. Only a few constants differ, such as the memory size, and they live in one small per-board module.

**The LED rule.** Each board has its own blink formula, worked out before the board is trusted, exactly as now.

## What differs

| | Dock (workstation) | 4K (embedded) |
|---|---|---|
| CPU | the fast, full one | a smaller, much slower one |
| Memory | DDR3, the book's 1 MB map | HyperRAM (8 MB on the chip), a smaller map |
| Disk | SD card | RAM disk, filled over the cable; an SD card on the pins later |
| Talking to it | screen, mouse, keyboard | commands from the PC over JTAG, one button, the LED |
| Screen | 1024×768 desktop | optional small HDMI text screen |

## Ideas for shrinking the 4K

These are ordered from "cheap to try" to "bold". The first few can be measured in a day each. Each one keeps the LED blinking, with a new rate computed first.

### 1. Remove the scaffolding once Proof 7 lands
Today the 4K CPU carries machinery that exists only for the bring-up: the ten-entry patch table (chainFix) and the hardware check accumulators. Once the real `Modules.Load` runs code from memory, the patch table has no job left, and the checks can become a few lines of Oberon that run at boot. This is likely the biggest easy saving, and it costs nothing in the final design.

### 2. Put the registers in block RAM
The 16 registers are built from logic cells. The chip has small block RAMs (10 of them, 2 still free) that could hold all 16 registers almost for free. A block RAM gives one read per clock, so the CPU would read its two operands over two clocks. The CPU gets slower, which we're allowed, and a large share of logic is freed. This goes further than ledger cut 3.

### 3. Shift and multiply with the unused multipliers
The chip has 16 hardware multipliers (18×18) that the design doesn't use at all. Multiplying by 2ⁿ is the same as shifting left by n, so the barrel shifter, one of the biggest pieces of the CPU, can be rebuilt on these blocks. Right shifts work the same way with the bits reversed. `MUL` then comes for free as well. This is an old FPGA trick.

### 4. Trap the rare instructions and finish them in software
Divide (and maybe the shifts, if idea 3 doesn't pan out) stop being hardware. The CPU jumps to a small Oberon routine that does the work. The `.rsc` files stay identical; they just run slower on the 4K. The book's machine traps in the same way for `NEW` and `ASSERT` already, so it fits the design.

### 5. Run the clock slower
The 4K misses 27 MHz at its worst-case temperature today. Halving the clock fixes that, and with relaxed timing the tools can usually pack the design tighter. Slower is fine for this board.

### 6. A one-bit-at-a-time CPU
The most radical option is a new RISC5 core that works through each 32-bit value one bit per clock. SERV, the best-known core of this kind, is a full 32-bit RISC-V in roughly 125–240 LUTs. A RISC5 in the same style would leave almost all of the 4K free for HDMI and I/O. Each instruction would take roughly 32–70 clocks, so expect well under 1 million instructions per second. That's enough for a command line, and the timing is very regular, so the blink formula would be easy to predict. This is a separate project, so it's worth doing only if ideas 1–5 aren't enough.

### 7. Measure Wirth's own RISC5 on the 4K first
Before designing anything, synthesise the book's original `RISC5.v` for the GW1NSR-4C and look at the size (no board needed). That gives a reference point: if the book's own CPU fits with room to spare, the pipelined Chisel CPU may simply be the wrong shape for this chip.

### 8. The wild one: let the Cortex-M3 be the CPU
The 4K chip has an ARM Cortex-M3 built in (up to 80 MHz, with hardware divide) that uses none of the FPGA logic. It could run a RISC5 emulator, like the PC emulator you used years ago, and the fabric would be left almost empty for HDMI and the LED. It would probably be *faster* than a soft CPU on this chip. Two catches. The M3 boots from on-chip flash, which breaks the "SRAM load only, never flash" rule. And it isn't yet confirmed how easily it can reach the HyperRAM. It's listed so it gets a conscious no rather than none at all.

## Talking to the 4K without a UART

### The JTAG cable is the serial port
The USB cable is already a JTAG link (the BL702 chip on the board), and that's how bitstreams get loaded. Gowin chips have a hidden JTAG block, `GW_JTAG`, that lets your own logic join that same chain. Other people have used it on the GW1NR-9 and the Tang Nano 20K to reach their designs from a PC. With it the PC can read and write a mailbox in the design, which is all a terminal needs.

That gives Oberon a "serial port" with no extra wires. Write a small Oberon module with the same interface as the book's `RS232`. Then the rest of the system, including `PCLink1` (the book's tool for moving files to and from the PC), works unchanged on top of it.

**To check first:** that `GW_JTAG` exists on the GW1NSR-4C, and which host tool can drive it through the BL702. That's step 1 below.

### The buttons and the LED
One button is reset. The other (KEY_1, pin 14, currently commented out in `tang-nano-4k.cst`) becomes the mode button. Each press moves to the next mode, and the LED flashes the mode number before going back to its steady blink. So even without a screen you can see which mode you're in.

### HDMI, if it fits
A small text screen (say 40×15 characters) needs a font and a few hundred bytes for the text. HDMI timing first, a flashing screen first (as in the LED ladder), text later. If the 4K can't fit it beside the CPU, the JTAG terminal is the screen.

### A disk
There's no SD slot. Two options:
- A **RAM disk** in HyperRAM, filled from the PC over JTAG after each SRAM load. It's lost at power-off, but no hardware changes.
- A **microSD breakout** wired to spare header pins. The project already has an SPI sector reader (`SpiSector.scala`), so this is the book's disk, just on loose wires.

## What Oberon changes this needs

- A `JtagLink` module (or a replacement `RS232`) with the book's `Send`/`Rec` interface.
- A trap handler that does divide (and anything else idea 4 drops) in software.
- A per-board module of constants: memory limit, stack origin, disk size.
- A small command loop instead of `Oberon.Loop`: read a command name from the link, then `Modules.Load` and call it. This is roughly what Embedded Project Oberon does.
- `System` commands that print to the link instead of to a viewer.

None of this touches the compiler or `Modules.Mod`.

## A first 4K ladder (each step blinks)

1. **JTAG hello.** The PC writes a number over JTAG and the LED rate changes to match it. This proves the channel before anything depends on it.
2. **Mode button.** The button cycles three blink rates, and the LED flashes the mode number between them.
3. **Size check.** Synthesise Wirth's `RISC5.v` (idea 7) and the current CPU with chainFix off (idea 1), and record both sizes.
4. **Registers in block RAM** (idea 2). Compute the new rate, then measure it.
5. **Shifts on the multipliers** (idea 3), or trapped (idea 4).
6. **Command line.** Type `Blinker.Faster` on the PC, and the 4K loads the module from its RAM disk and the LED speeds up.
7. **HDMI flash**, the same as step 5 of the LED ladder, now that there's room.
8. **Text on HDMI**, showing the last command and a blink counter.

After step 6 the 4K is recognisably an Oberon system: modules loaded by name, a file system, and commands, just without the desktop.

## Open questions

- Does `GW_JTAG` exist on the GW1NSR-4C, and how fast can the BL702 move data through it?
- Is the bit-serial CPU (idea 6) worth it, or do ideas 1–5 free enough?
- Is HDMI text worth its block RAM on the 4K, or is the PC terminal enough?
- Should the M3 (idea 8) get a quick experiment despite the flash rule, just to know?
