# Strategy

What this project is for, how it is brought up, and how plans are written. Read this once per session, before `docs/todo.md`.

## The goal

Bring up Project Oberon, revised edition 2013, on Wirth and Reed's RISC5 processor (not RISC-V, not PC Native Oberon, not A2), on two Gowin FPGA boards. The end of the road is the book's machine: 1024×768 black-and-white screen, tiled viewers, commands run by a middle click. The very long-term end point is an all-in-one computer: the Dock paired with a microcontroller on the PMOD connectors for keyboard and mouse.

The maintainer used Oberon at university about 20 years ago, mostly in the PC emulator, and loved it, but does not know its internals. That is why plans are written in plain language (see "How plans are written").

## Two boards, two roles

**Tang Primer 20K Dock** (GW2A-18, DDR3) is the workstation. It grows toward the book's memory map and, later, the tiled desktop. It has a UART, so it can be tested end to end with nobody there.

**Tang Nano 4K** (GW1NSR-4C, HyperRAM) is the secondary system. It runs the same Oberon, with no DDR3 and no desktop: today a blinking LED and a blinking square on HDMI, a flash disk, and later the timer, its button, and the Oberon-side steps. It has no working UART and no usable JTAG data path. Its only inputs are its two buttons, and button tests need a person, so they never gate overnight work. Nobody solders anything onto the 4K. It is nearly full, so every feature is checked against it, and the bring-up ledger is its space list.

Both boards run the same compiled `.rsc` modules and the same Blink. Where a board lacks a piece of hardware, its I/O stores are dropped (never passed to memory) and the same code runs anyway. A feature the 4K cannot hold is a build switch, not a second design.

## The LED is the proof

The flashing LED is the physical proof that the whole system works end to end: clock, CPU, memory, loader, Oberon code. It must stay at every step.

- Every step publishes its blink rate, from a formula, before the board is trusted. The webcam (and, for the screen, the HDMI capture card) has to measure that rate.
- A failed check leaves the LED dark. The LED, and the square or bitmap on the screen, only come on after Blink stores the arm word computed from its self-checks, so a skipped check can never look like a pass. The status blocks (`docs/screen-and-boot.md`) may show before the arm word: they report how far the boot got, and they are never a pass.
- Every step adds one capability and keeps the blink. No step replaces the blink with a silent boot.
- Everything comes back to Blink: new features are proved by Blink using them (a timer paces the blink, a file holds its rate, the screen shows its counter, an Oberon task drives it).

## How the work is shaped

- **Small steps with proof points.** One slice of the system at a time, each with a measured result. Prefer the smallest visible version first: flash the whole screen before a square, a square before text, text before a frame buffer.
- **Oberon before FPGA.** Where it is not much slower, do it in Oberon code rather than in hardware. Keep the CPU and the FPGA design minimal.
- **Simulation first, then the 4K, then the Dock.** The prove-ladder skill has the details.
- **Space problems on the 4K:** shrink first. If that is not enough, the bring-up ledger lists the next cuts, lowest open number first.

## Loading the boards

Bitstreams are SRAM-loaded only. The one flash exception is the Nano 4K's disk data file, inside `0x200000`–`0x3FFFFF`. `AGENTS.md`, "Loading boards", has the exact rule.

## Where things are

- `docs/todo.md`: the work queue. One item at a time, from `Next:`. It is an index; each item points to its write-up. Finished items stay in place, marked "Done.".
- `docs/next-steps.md`: write-ups for to-do items 19–31.
- `docs/screen-and-boot.md`: write-ups for to-do items 32–47: the status register, the bitmap, the book's `Display`, `Fonts` and `Texts`, traps, and the main loop.
- `docs/monorepo-layout.md`: the write-up for to-do item 48.
- `docs/ddr3-training.md`: the write-up for to-do item 49.
- `docs/bringup-ledger.md`: the Nano 4K space list, one numbered list, and the record of how the 4K got its room.
- `docs/led-ladder.md`: the long-range map from the blink to the Oberon desktop, including the far-future items.
- `docs/hdmi.md`, `docs/modules-mod-plan.md`: finished plans, kept for their measured results.
- `.cursor/skills/work-todo` and `.cursor/skills/prove-ladder`: how an agent takes an item and proves it.

## How plans are written

- Plain language. A clear header and a short paragraph per step. Explain any hardware or Oberon term the first time it appears.
- Every step says what it adds, what the big jump is, and how the LED (or the screen) proves it.
- Steps are small enough that the blink either stays at its rate or the new rate is computed before the board is trusted.
- When suggesting next steps, give a short list first. Detail comes when asked.
