# Item 49: DDR3 training that survives a rebuild

Dock only. The Nano 4K has no DDR3 and is not touched. This item comes after item 48, so the files named here will be under `primer20k/` by then; the names below are today's paths.

## Why

DDR3 memory has to be "trained" every time the Dock starts: the controller tries a range of small signal delays and keeps the one where a test word reads back correctly. On this design that often fails. `tools/load_dock.py` reloads the bitstream up to 16 times to get one start that trains, and sometimes 16 is not enough.

Two different things go wrong, and the write-ups for items 19 to 46 record both:

- **A rebuild breaks it.** Every build, the Gowin tool decides again where each piece of logic sits on the chip (placement) and how the wires run between them (routing). The DDR3 pins never move, but the registers that feed them do, and unrelated logic lands beside them. The delays shift by a fraction of a nanosecond and the trainer's window is missed. `gowin/primer20k/ddr3.cst` already holds about twenty hand-made placement rules, each added after one such failure.
- **The same bitstream is not reliable.** One file trains on one load and fails on the next (`docs/next-steps.md`, item 29). Placement cannot explain that; the trainer has too little margin.

This item fixes both, with numbers, so later work (the memory block with several ports, the full screen in DDR3) starts from a DDR3 that just works.

## What does not change

- The controller stays nand2mario's Verilog file, `gowin/primer20k/ddr3/ddr3_controller.v`. The Chisel bridge stays Chisel. Nothing has to be rewritten in another language.
- No new memory ports, no screen in DDR3. Those are later items.
- Blink, the arm word and the published blink rate stay as they are, except in stage 5, which says so.

## Stage 1: a training meter

Add a mode to `tools/load_dock.py` (or a small script beside it) that SRAM-loads one bitstream 20 times in a row and writes down, for each load, whether it trained and the delay values the trainer chose. It reads the boot line the Dock already sends over the UART: `C.` means trained, `..0080` with `F 4B` means it did not. No disk is sent and nothing on the board changes.

Proof: the meter's table for the current good image, recorded here as "trained N of 20". On the loads that train, the image is unchanged, so Blink is at its published rate.

## Stage 2: two canary builds

A canary is a build that differs from the good one only by something that should not matter. Make two:

1. The good netlist plus a 32-bit counter that drives nothing but one kept wire.
2. The good netlist built with `VIDEO_MODE=square`, which `docs/screen-and-boot.md` records as "does not train on this floorplan".

Run the meter on both. These three tables (good, canary 1, canary 2) are the "before" numbers.

Proof: the three tables, recorded here. No pass mark yet.

## Stage 3: fence the DDR3 logic

Give the DDR3 logic one fixed area of the chip and keep everything else out of it.

- Put every register and lookup table under `u_ddr3` (the controller, including its trainer) and the bridge's fast-clock side in one placement group with one region next to the DDR3 pins. The region is taken from the place that trains today (rows 38 to 56 hold the data, mask and enable registers).
- Mark that region so no other logic may be placed in it. The Gowin constraints guide names the keyword; see "To check".
- Where a group is not enough, pin single registers to the exact sites of the trained place. The tool can write out the positions of a finished place so they do not have to be typed by hand; see "To check".
- Then remove the hand-made rules that only kept other logic away (`gate_grp`, `spi_grp`, the instruction ROM, multiplier and bitmap pins), one at a time, running the meter after each. A rule stays if removing it lowers the number.

Routing cannot be frozen the same way in this tool as far as is known, so delays will still move a little between builds. Stage 4 is there for what is left.

Proof: the meter on all three builds. Target: each trains at least 19 of 20 first loads, and the two canaries are no worse than the good build. The good build then blinks at its published rate on three SRAM loads.

## Stage 4: retrain inside the chip, not by reloading

Today a failed training means the host reloads the whole bitstream. Change the start-up logic in `gowin/primer20k/blinky_top_ddr3.v` (the `cold_run` retry, which gives up after a few tries) so that it resets the memory and trains again, as often as needed, without a reload. Each retry takes a fraction of a second. The status blocks show "training, try N". The CPU stays in reset until training passes, as now.

Simulation first: `sim/run_ddr3_phy.sh` with a forced failure on the first two tries.

Proof: with the reload retries in `tools/load_dock.py` set to 1, 20 of 20 loads reach Blink at the published rate. The meter also records how many internal tries each load needed.

## Stage 5: more margin (only if stage 3 misses its target)

The timing report has shown the trainer's own path with no spare time (slack of −0.018 ns in `docs/modules-mod-plan.md`). Two options, cheapest first:

1. Ask the tool for more than is needed: constrain the fast clock in `ddr3.sdc` a few percent above its real 96.75 MHz, so the real clock has room.
2. Run the memory slower. DDR3 cannot go below about 300 MHz, so the memory clock can drop from 387 MHz to about 306 MHz and the CPU from 24.2 MHz to about 19.1 MHz. This changes the blink rate; publish the new rate from the formula before the board is trusted.

Proof: the meter on all three builds meets the stage 3 target.

## Done when

- First-load training is at least 19 of 20 on the good build and both canaries.
- With in-chip retraining, 20 of 20 loads reach Blink with one SRAM load each.
- The numbers before and after are in this file.
- `tools/load_dock.py` keeps its reload retries as a fallback, with the default lowered to 3.

## To check before starting

- The exact Gowin constraint syntax for keeping other logic out of a region (an "exclusive" group location), in the Gowin physical constraints guide.
- Whether the Gowin tool can export the positions of a finished place as constraints (the "post-place file" option), and the option's name.
- Whether the trainer can be restarted cleanly without reloading: the controller's reset input and the PLL reset.
