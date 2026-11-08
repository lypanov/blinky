# From the blinking LED to the Oberon desktop

A plan in small steps. Every step keeps the real LED blinking, and the rate is worked out before the board is trusted. When a check fails, the LED stays dark.

## Where the project is today (main, 7 Nov 2026)

The CPU can now load a program from a "file" and run it, though not yet through the real Oberon code. Six of the seven proofs in `docs/modules-mod-plan.md` are done on both boards: the 32 KB stack area, division, the error trap, the real compiled module checker, running a placed program from external memory, and reading one sector of a pretend disk. Next is Proof 7: the real `Modules.Load("Blink5")`.

The Nano 4K is full: 99% of its slices are used, and it is already a little too slow at its worst-case temperature. The Primer 20K Dock has plenty of room, and its HDMI port was checked on 3 Nov with the NESTang demo.

## What the LED says

- **Steady blink at the predicted rate:** everything up to this step works, end to end.
- **Dark:** a check failed. This stays as it is.
- **New: a few quick flashes, then the steady blink.** During boot, the LED gives one short flash per stage it passes, such as "memory ok" or "card read". When something goes wrong you can see how far it got, not just that it failed. The steady blink still means success.

## Part 1: Loading for real

### Step 1: The real Modules.Load
This is Proof 7, already planned. The real Oberon loader finds Blink5, links it and runs it. **Big jump:** from programs glued together on the PC to the system linking its own programs.

### Step 2: Two blinkers, chosen by name
Put two modules on the pretend disk, BlinkFast and BlinkSlow, and load one of them by name. The rate you see tells you which file was actually loaded. **Big jump:** the program running is the one you asked for, not just the only one there.

### Step 3: The blink rate lives in a file
The blinker reads its delay from a small file. Change the file on the PC, rebuild only the disk image, and the rate changes. **Big jump:** real files, not just modules.

## Part 2: The screen joins the LED (start early)

### Step 4: The capture card becomes a second meter
Extend the webcam tool with a new `measure_screen` that reads the HDMI capture card and reports how often the screen changes brightness. Test it first with the NESTang demo. **Big jump:** a second, exact witness. The capture card counts whole frames, so its timing is more precise than the webcam's.

### Step 5: The Dock's screen flashes with the LED
Add only the part that produces the video signal (sync and timing), with no picture memory. When the CPU turns the LED on, the screen goes white; when it turns the LED off, the screen goes black. The capture card has to report the same rate as the webcam. Aim for the book's 1024×768. If that is hard at first, start at 640×480. **Big jump:** working video timing on the board that will run the desktop.

### Step 6: The 4K's screen flashes too
This is the same idea, but the 4K needs room first. Either take ledger cut 3 or 4 (the smaller register file or the slower shifter), or make a separate 4K "video" build without the parts it doesn't need yet. The LED rate after the cut has to be recomputed before the board is trusted. **Big jump:** both boards have two physical witnesses.

### Step 7: A lamp on the screen
Add a tiny picture memory, for example 32×24 big blocks that fit in on-chip memory. The CPU draws a square that turns on and off with the LED. Everything else on the screen stays still. **Big jump:** the CPU draws, instead of switching the whole screen.

### Step 8: Words on the screen
Add a built-in font and show "BLINK" with a counter that goes up by one each time the LED lights. Read the counter in a capture frame and compare it with the time. **Big jump:** text, which is the beginning of the 4K's text screen.

## Part 3: A real boot

### Step 9: Everything runs from main memory
Today the CPU reads its instructions from on-chip ROM, plus one placed body from external memory. Move all running code into the Dock's DDR3, the way the book does. It will run slower; compute the new rate first. Only the DDR3 training stays in ROM. **Big jump:** the book's memory model, where code is just data in memory.

### Step 10: Read one sector from the SD card
Add a real card reader. The blink delay is stored on the card. Pull the card out and the LED gives its boot flashes, then goes dark. **Big jump:** a real disk.

### Step 11: Boot the inner core from the card
The book's small boot loader reads the inner core (Kernel, FileDir, Files and Modules) from the card, then loads the blinker by name. **Big jump:** the book's boot path, end to end. From here on, a change to a blinker needs only a new card image, not a new bitstream.

### Step 12: Memory that cleans itself up
The blinker allocates a little memory each blink, and the garbage collector frees it. A counter on the screen shows the memory used, and it must stay flat. **Big jump:** Oberon's automatic memory management.

## Part 4: The real screen on the Dock

### Step 13: A strip of the real screen from DDR3
Read only a band of lines from DDR3, with the lamp square inside it. Showing the screen takes memory time away from the CPU, so compute the new LED rate first. **Big jump:** the screen and the CPU share memory, the hardest timing problem in the whole plan, tackled in a small piece.

### Step 14: The full 1024×768 black-and-white screen
Expand the band to the full screen. At 1 bit per pixel the screen is 96 KB, the same size as in the book. **Big jump:** the book's display.

### Step 15: Oberon's own drawing code
The real Display module draws the lamp. **Big jump:** Oberon draws its own pixels.

## Part 5: The desktop

### Step 16: The blink becomes an Oberon task
Start the real Oberon main loop and make the blinker a background task, which is how the book runs things in the background. If the loop stops, the LED stops. **Big jump:** the LED now proves that the whole desktop loop is running, not just one program.

### Step 17: Input
Start with a board button standing in for a mouse click: press it and the blink speeds up. Later, add a real mouse and keyboard. That is a hardware choice still to be made: PS/2 like the book, or a USB adapter. **Big jump:** you can interact with it.

### Step 18: Tiled viewers, and a Blinker viewer
Show the two tracks of viewers. One small viewer contains a lamp that flashes in time with the real LED, plus text you can click: `Blinker.Faster`, `Blinker.Slower`. A middle click changes the rate of both lamps at once. **Big jump:** the Oberon desktop you remember, and the LED and the screen showing one system.

### Step 19: Edit.Open
Open a text, edit it and save it to the card. The Blinker viewer keeps flashing the whole time. **Big jump:** you can actually use the system.

## Along the way

- **Language features as they are needed.** Each new module will need parts of Oberon the CPU can't run yet, such as bytes, multiply, and later floating point. Each one gets its own small step before the module that needs it. For example, compute the blink delay with a real number, so a wrong answer shows up as a wrong rate.
- **Tests.** Simulation first, then the board, as now. Each step adds a simulator test that predicts the same rate the webcam or capture card has to measure.

## The 4K (later, just noting it)

The 4K has room for steps 4–8 at most, and only after an area cut. Its natural goal is a little toy: HDMI out, and one button that cycles through modes, such as a flashing screen, the lamp, and the text counter. It can't follow the Dock into DDR3, the card and the desktop. How the 4K should interpret the final system is a separate question for later.

## How this file relates to the others

`docs/modules-mod-plan.md` stops at Proof 7 (Step 1 here). This file continues from there. `docs/todo.md` is not changed yet; it will point into this ladder one step at a time once the order is agreed.
