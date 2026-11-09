# HDMI on both boards

The screen becomes a second witness next to the LED. The Nano 4K goes first, so the design is sized for the smaller chip from the start. The Dock then adds what the 4K cannot hold. There is one capture card. It is on the 4K for steps 1–2 and on the Dock for steps 3–5. The maintainer moves the cable between them.

## Rules for every step

**One video module, with a build switch.** The video module takes a mode: `off`, `flash`, `square`, or `text`. Each mode includes the one before it. The 4K builds up to `square`. The Dock builds up to `text`. Today's images stay `off` unless a step changes them. Each board has its own pin file. The timing is 640×480 at 60 Hz (25.2 MHz pixel clock is fine). The book's 1024×768 comes later.

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
