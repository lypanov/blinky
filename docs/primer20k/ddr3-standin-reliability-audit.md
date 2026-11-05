# DDR3 stand-in reliability audit

The Dock stays on the accepted fetch image. This note does not load a
bitstream and does not start step 6. Step 5 remains with the stand-in
agent until a bitstream and this model agree. The audit is what has
to change before a later Modules.Load step can trust `stand-in matches`.

The commits are read together with the sim agent's transcript
(`bc-5a35e67c-7a90-564d-ac3b-59f0c2650296`, 2341 records). The dump
ends on the decision to fit the P/D miss and load one code further
back. Commit `89fd0ae` is that load's result, written after the last
line of the dump.

## The pattern

The stand-in is a column-shift of the programmed step against a center
chosen after a UART. `sim/run_ddr3_standin.sh` then asserts that story
and prints `stand-in matches`. Three times that sentence described a
program the Dock was not running, or a program that had not been loaded.

| When | Dock | What the green run actually was |
|---|---|---|
| Reader, both lanes 10 (`0febb62`, `36d8ed0`) | `AAAAAAAA` / mask `F0` at steps `000A` `000A` | Center renamed to 9. The bitstream still programmed 10. Lanes at 9 were the pass in the script. |
| Reader forced to step 9 (`b9201f3`, `cb6c991`) | `AFF0B9CF` / mask `50` | Whole-column offset 0. The model has no pins that disagree inside one step. |
| Warm sweep (`351112b`) | `54F854F7`, `AFF7AFF7`, `0C0D0D9D`, and the same step 10 twice with two sums | Left unnamed. The array on the board kept the previous trial. This part of the record is honest. |
| Cold step 10, first place (`f02ba4b`) | `DFAADFAA` / R9 `20532036` | `+ddr3_pin_even=20FF +ddr3_odd_clear=2`. While that mask is set, the step plusargs are ignored. |
| Cold step 10, the place that passed (`09fd686`) | mask `FFFFFFFFFF`, R5 `00000000`, R9 `FFFFFFE1`, steps `000A` `000A` | Default center 10, both lanes 10, written down before the load. This is the one prediction that matched. |
| Fetch, both lanes 10, then both lanes 9 (`878b767`, `05a8c61`) | `AAAAAAAA` both times, steps `000A` then `0009` | `+ddr3_place_fetch` set the center to 9, so lanes at 10 are offset +1 and lanes at 9 are the script's pass. The Dock at 9 was the same alias. Forcing offset +1 and ignoring the lane numbers came later, at `0cd9710`. |
| Fetch pass image (`0cd9710`) | steps `0007` `000B`, R5 `00000000`, full mask, blink | `+ddr3_fetch_eye` with the lanes left at 10. In that Verilog the flag does not set a center. It only skips the place-fetch override. Center stays 10, so the green run is the ALU eye. `+ddr3_wlevel_eye` hardcoded offsets −1 and 0 and did not read the lane plusargs. |
| Same image, flag fixed (`4dfd5d8`) | same UART, no reload | `+ddr3_fetch_eye` now sets centers 11 and 7, and the pass case passes both lane numbers. That matches the program already on the Dock. The model still has no write-level input. |
| P/D chain, backoff 1 and 3 (`df7b130`) | steps `0007` `000B`, R5 `AAAAAAAA`, R9 `55555536`, mask `F0`, hold `0x1394` | `+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7` is a pass. `+ddr3_place_fetch` at those lanes is R5 `FFAAFFAA`. |
| P/D chain, backoff 2 and 4 (`89fd0ae`) | still `AAAAAAAA` / mask `F0`, steps `0006` `000B`. Lane 0's edge moved `000C` → `000D`, so the extra backoff left lane 0 at `000B`. Lane 1 moved 7 → 6 and stayed the alias. | `+ddr3_pd_eye` forces offset +1 when lane 0 is 11 and lane 1 is 6 or 7. The flag has no offset 0. The script's blink witness is default lanes 10 and 10, which that note calls not a Dock pair. |
| Fetch bitstream loaded back, this calibration (UART read, no load from this audit) | delay-loop PC, mask `FFFFFFFFFF`, R5 `00000000`, R9 `FFFFFFE1`, steps `0007` `000C` | `+ddr3_fetch_eye +ddr3_lane0=12 +ddr3_lane1=7` is center 11/7, lane 0 offset +1, hold `0x1394`, R5 `FFAAFFAA`, mask `F0`, 0 edges. The centers fitted at `4dfd5d8` miss the image they were fitted to, one calibration later. |

The controller already says this. `wstep_run` is the write-level edge
minus `WLEVEL_BACKOFF` (`gowin/primer20k/ddr3/ddr3_controller.v`). The
comment on those parameters says the stand-in does not read the edge.
The first P/D build subtracted 1 and 3 and printed `0007` `000B`, the
fetch pass's steps, and the column was the alias. A model whose only
alignment input is the programmed step has to print one R5 for that
pair. The board printed two.

The same fetch bitstream, loaded back after those trials, calibrated
lane 0's edge to `000D` and printed `0007` `000C` while the column
stayed the pass. On that place the eye moved with the edge. The
stand-in still has the old centers, so it calls lane 0 at 12 a miss.

## Root causes, in order

1. **Alignment is place skew plus a DLL tap. The stand-in stores only a
   tap, and it stores the tap as a programmed step.** The fetch pass and
   the P/D miss used the same backoff, the same printed steps, and
   different data. Fitting a new center after each UART describes the
   last place. It does not name the next one. `TNS 0` does not keep the
   DQ/DQS route.

2. **`stand-in matches` checks the story in the script, not the bitstream.**
   At `0cd9710` the pass invocations are `+ddr3_fetch_eye` with no lane
   plusargs. Default lanes are 10 and 10, default center is 10, offset
   is 0. The Dock program was 11 and 7. The flag was present in the
   command line and absent from the center assignment. `4dfd5d8` fixed
   that flag. The script structure is unchanged: whoever edits the
   expected R5 also edits the plusargs, and the script goes green.

3. **Each miss becomes a new plusarg instead of a missing input.**
   `+ddr3_center`, `+ddr3_place_fetch` (codes 9 and 10 forced to offset
   +1), `+ddr3_fetch_eye` (centers 11 and 7), `+ddr3_fetch_split` (DQ1
   and DQ13 fixed), `+ddr3_pin_even` / `+ddr3_odd_clear` (one cold UART;
   the step model is switched off while the mask is set). `89fd0ae`
   adds `+ddr3_pd_eye`, which forces offset +1 for lane 0 at 11 and
   for lane 1 at 6 or 7, and has no offset 0. That records the plateau.
   It does not say which step would be the column. The script still
   ends in `stand-in matches`, and the blink numbers in that section
   are default lanes 10 and 10.

4. **Whole-column shift cannot be the pin model, and the pin model
   cannot be the column model.** The step-9 split `AFF0B9CF` and the
   warm sweep were correctly left without a plusarg. The cold
   `DFAADFAA` line was then given a mask that ignores the step. Both
   results satisfy the same script. A later reader can be green for a
   reason that does not apply to the image about to be loaded, which is
   what the step-3 note had to spell out when the passing place was no
   longer the pin-mask place.

5. **Warm array contamination was real and is not the remaining bug.**
   The sweep kept bytes, so one step printed two sums. The stand-in
   starts empty on every process. Dropping that table as a target was
   right. The P/D miss is a cold hold at `0x1394` with a stable
   `AAAAAAAA` line. Cold versus warm does not explain it.

## What the transcript shows

The published sentence and the reasoning next to it disagree at the
false green, and they agree on the later refit.

- After the warm sweep they wrote that a plusarg hardcoding the target
  sum would be dishonest, and that the stand-in cannot grow a new
  offset rule for those sums without inventing a PHY. Modules was told
  to stop sweeping steps 6..16. The cold `DFAADFAA` line was then given
  a mask chosen to hit that one UART: "a single center-9 offset cannot
  explain the result", so `+ddr3_pin_even=20FF` plus a DQ1 clear. That
  is the fitted plusarg the sweep note had just refused, aimed at one
  line instead of the table.
- In the same stretch they wrote that the stand-in cannot derive the
  eye from the command port, and that center is a plusarg rather than
  a property of the bitstream. The next published prediction was still
  a center: `+ddr3_place_fetch` sets this route's center to 9, and both
  lanes at 9 are the pass. The Dock at step 9 printed `AAAAAAAA`.
- The `0cd9710` report says `stand-in matches`, and `+ddr3_fetch_eye`
  is this pass. While building that tip they noted the eye test forces
  offset 0 in the C++ harness. After the rejection they read their own
  tip back: the plusarg is only used in that C++ testbench to zero
  offsets, the Verilog never reads it, and the default center-10 lanes
  match the Dock pass by coincidence, so the fake witness looks correct.
  They also wrote that `+ddr3_place_fetch` forces offset +1 and ignores
  the lane numbers. `4dfd5d8` is that correction, and it says in the
  same note that the model still cannot name the next build's edge.
- Handed step 5, they wrote: the Dock kept steps `000B` and `0007` and
  printed the even-word alias, so this place's column is one code below
  the fetch eye; teach the stand-in that pair, then program one code
  further back and check it on the board. The same stretch sets
  `+ddr3_pd_eye` centers to 10 and 6. That is the step-9 sequence
  again. The load that followed stayed on the alias, and `89fd0ae`
  then took the eye out of the flag.

## Tip `89fd0ae`

This tip can print the P/D Dock alias.
`+ddr3_pd_eye +ddr3_lane0=11 +ddr3_lane1=7` and the same flag with
lane 1 at 6 both expect R5 `AAAAAAAA`, R9 `55555536`, mask `F0`.
The Dock banner is `CH1394`. `--pc 1390` accepts any PC in
`[0x1390, 0x1398)`, so that banner and `CH1390` both pass the same
row. Both board loads were that plateau. The fetch image was loaded
back and still passes. Step 5 stays with the stand-in until a loaded
pair passes, or until a conclusion is sourced from the RTL rather
than from the next integer below the bin.

The flag has no offset 0. Lane 0 at 11 is forced to offset +1, which
is the only code `step - 11` would have called 0. Lane 1 at 6 and at
7 are both forced to +1, and 7 is the only code `step - 7` would have
called 0. No pair under `+ddr3_pd_eye` is the column. That part of
the tip matches the two UARTs.

`stand-in matches` still prints. The blink rows under `ddr3pd` pass
no `+ddr3_pd_eye` and no lane plusargs, so they are default lanes 10
and 10. The script's own comment says those steps are not a Dock
pair. A green run of that script is the software check at the old
center, plus a replay of two misses.

The committed `DDR3_PD` image does not explain the column from a
parameter the stand-in failed to read. At `89fd0ae` its backoff is
1 and 3, the same as `DDR3_FETCH`. The controller has no `DDR3_PD`
branch. The UART hold is the memory prologue at `0x1394`, which runs
before the P/D chain, and that prologue is the same stores as the
fetch image. What the two images do not share is the placed route of
the larger CPU. Fetch with backoff 1 and 3 passes, and when lane 0's
edge moved from `000C` to `000D` the programmed step moved from
`000B` to `000C` and the column stayed the pass. The P/D build with
the same backoff was the alias at edges `000C` and `000A`. Backoff
2 and 4 was still the alias, and lane 0's edge moved with the
rebuild so its programmed step stayed `000B`.

The working tree on `cursor/ddr3-pdchain-e003`, not in `89fd0ae`,
names the next guess in every copy of the story. Centers are 10 and
5. `WLEVEL_BACKOFF` / `WLEVEL_BACKOFF1` are 3 and 5, which program
steps `000A` and `0005` if the edges stay `000D` and `000A`. The eye
harness has a row for that pair, and the CPU blink rows pass
`+ddr3_pd_eye +ddr3_lane0=10 +ddr3_lane1=5` and expect the delay-loop
pass. The top of `docs/primer20k/step5-ddr3.md` calls that pair the
eye. The Dock section of the same file still says the constants were
put back to backoff 1 and 3, no further step was loaded, and the
fetch image is on the Dock. Lane 1 at 6 and at 7 were both the alias.
One code below a two-code bin is the step-9 guess: both lanes at 10
and both lanes at 9 were `AAAAAAAA`.

## What the stand-in actually does

`sim/Ddr3UserModel.v` is a user-port model. It stores two bytes per
column, presents `dout` nine clocks after a read pulse, and drops
`busy` on the tenth. A write or a refresh drops `busy` on the sixth.
DM, the read-FIFO hold, and the WLOADN reload are separate plusargs
(`+ddr3_dm_all`, `+ddr3_dm_lane0`, `+ddr3_dm_lane1`, `+ddr3_nohold`,
`+ddr3_nowload`). Those change the command port. They do not depend
on a UART. That part can be trusted the way the HyperRAM model is
trusted: a CPU bug in the stores, the mask, or the period shows up
before a load.

The PHY is not in the model. The header says so. Alignment is
`eye_from_offset` on `programmed step - center`:

| offset | what the byte does |
|---|---|
| 0 | lands on the addressed column |
| +1 | the even word of the BC4 group fills both words; the odd word does not replace it |
| −1 | the odd word overwrites both words |
| anything else | the byte is stored that many columns away |

`+ddr3_pin_even` replaces that path. While the mask is set, the lane
numbers are not applied. `+ddr3_fetch_split` is the same kind of
replacement for one earlier UART (`DFFFDFFF`). A whole-column shift
and a per-pin mask cannot both be the reason a later line matches.

## Three copies, one story

A green `sim/run_ddr3_standin.sh` means three files agree with each
other.

1. `Ddr3UserModel.v` computes the offset and shifts the bytes.
2. `sim/tb_ddr3_eye.cpp` computes the offset again, picks the expected
   halfwords from that number, and checks the Verilog. The eye binary's
   top is the model, so this does run the shift. The expected pattern
   is chosen by the C++ offset, not by a stored UART. Editing both
   formulas in one change makes `eye pass` follow.
3. `sim/tb_ddr3_cpu.cpp` checks R5, R9, the mask, and the PC against
   constants in the script. The script's author picks the plusargs and
   the expected registers in the same edit. `run` records a failure and
   keeps going. The last line is `stand-in matches` whenever every
   process exited 0.

Nothing in that chain reads `WLEVEL_BACKOFF` from
`gowin/primer20k/blinky_top_ddr3.v`, and nothing compares the lane
plusargs with `wstep - WLEVEL_BACKOFF`. The controller comment already
says the stand-in does not read the edge.

`--pc` is a window of eight bytes: the check passes when
`pc` is in `[expect, expect+8)`. `CH1390` and `CH1394` are different
banners on the Dock. Step 4 printed both, with different R5 values.
The P/D alias rows pass `--pc 1390`, and the Dock banner is `CH1394`,
which sits inside that window. The script cannot reject a hold the
UART has already distinguished.

## Dock facts that stay closed

These lines were loaded. A later plusarg may replay one of them. It
may not move the green blink onto a pair that is not in this list.

| Image | Steps (lane 1, lane 0) | Result |
|---|---|---|
| ALU | `000A` `000A` | pass, mask `FFFFFFFFFF`, R5 `00000000` |
| Reader | `000A` `000A` | `AAAAAAAA`, mask `F0` |
| Reader, both lanes forced to 9 | `0009` `0009` | `AFF0B9CF`, mask `50`. No plusarg produces it. |
| Cold step 10 | `000A` `000A` | `DFAADFAA`. The pin mask describes this one line and ignores the step. |
| Fetch, both lanes 10, then both lanes 9 | `000A` `000A`, then `0009` `0009` | `AAAAAAAA` both times |
| Fetch pass | `0007` `000B` | pass. Edges `000A` and `000C`, backoff 1 and 3. |
| Same fetch bitstream, reloaded | `0007` `000C` | pass. Lane 0's edge moved to `000D`. The column followed the edge. |
| P/D, backoff 1 and 3 | `0007` `000B` | `AAAAAAAA`, mask `F0`, banner `CH1394`. Same steps as the fetch pass, other column. |
| P/D, backoff 2 and 4 | `0006` `000B` | `AAAAAAAA` again. Lane 0's edge moved to `000D`, so its step stayed `000B`. |

The pair `000A` `0005` is not in that list. `+ddr3_fetch_eye` with
lanes 12 and 7 is the image on the Dock now, and under the centers
from `4dfd5d8` it is offset +1 on lane 0.

## What 4K-level means here

On the Nano 4K, `FIRST_VALID` was fitted once. The header of
`sim/HyperRamUserModel.v` says 12 predicted about 0.520 Hz before the
load, and 13 is the value locked after the board measured about
0.500 Hz. Steps 2 through 8 say the parameter stays 13 and the model
was not edited. A wrong fixup is a dark hold at a known PC. The
period formula did not grow a new name per image.

The DDR3 command-port timing can be held to that standard now. The
column cannot, until the route is an input the model has before the
UART. Until then a trustworthy script has all of the following:

- The invocation that is allowed to print `stand-in matches` uses the
  backoff constants of the image about to be built, and it says the
  column is the last accepted place, not a new center.
- A replay of an old UART is a separate section and cannot turn the
  summary green by itself.
- `tb_ddr3_eye.cpp` and `Ddr3UserModel.v` share one offset function.
  A second copy that is edited in the same commit is not a check.
- `--pc` names the banner on the wire. A window that covers both
  `CH1390` and `CH1394` does not.
- A pair that has not been loaded does not appear as offset 0 in the
  eye harness, the CPU rows, or the step note.

## What the 4K path did that this does not

`sim/HyperRamUserModel.v` stores the bytes it is given and returns those
bytes after `FIRST_VALID`. The header records one fit: 12 was the
pre-load model (predicted about 0.520 Hz) and 13 is the value locked
after the Nano 4K measured about 0.500 Hz. Steps 4 through 8 say
`FIRST_VALID` stays 13 and the HyperRAM model was not edited. The period
formula stayed `103*N+142` because new software sits outside the delay
loop. A wrong fixup is a dark hold at a known PC. The memory model is
not given a new parameter per image.

The DDR3 user port can be that kind of model for the CPU once the column
is known: command timing, DM, and the bytes. It is not that kind of
model for the column. Write leveling is a per-build route. Re-running
full place-and-route for a larger imem moves the route while the DLL
codes can stay put. The 4K IP did not do that, so one latency served
every later step.

## Gaps

- Two builds with the same `wstep_run` must be allowed to return
  different columns. The committed model cannot.
- The pass case of the script must be the steps the bitstream will
  print (`wstep - WLEVEL_BACKOFF` from the RTL parameters), for the
  image under test. A second case may record an old UART. That second
  case must not be the one the summary calls the pass.
- A center edited in the same change as a new UART is a description of
  that UART. The blink witness has to stay on the steps that were
  loaded until a later load at the new steps passes.
- Pin masks and column offsets are separate regimes. One invocation
  should not claim both.
- Shapes the column model cannot produce (`AFF0B9CF`, the sweep sums)
  stay unnamed. A mask fitted to one of them is not a prediction of
  the next one.

## What has to stop

- Printing `stand-in matches` for a pass whose lane plusargs differ
  from the steps in the image being built.
- Treating a plusarg as modeled when the Verilog only uses it to
  disable another plusarg, as `+ddr3_fetch_eye` did at `0cd9710`.
  `sim/tb_ddr3_eye.cpp` at that tip forced offset 0 for the flag.
  The CPU witness calls `Ddr3UserModel.v`, which did not. The two
  have to implement the same plusargs.
- Adding an image-named center (`place_fetch`, `fetch_eye`, `pd_eye`)
  after the UART and moving the green blink onto steps that have not
  been loaded.
- Loading that inferred center as the next bitstream and calling the
  script a prediction. Both lanes at 9 were that prediction. The Dock
  still printed `AAAAAAAA`. Backoff 3 and 5, for steps `000A` and
  `0005`, is the same guess under `ddr3pd`.
- Modules accepting `stand-in matches` without running the witness at
  the steps the UART prints. That check is what rejected `0cd9710`.
  The image on the Dock right now prints `0007` `000C` and passes.
  `+ddr3_fetch_eye` at those steps holds with R5 `FFAAFFAA`.
- Treating `--pc 1390` as the Dock banner. The window is eight bytes,
  and `CH1394` passes it. Step 4 already printed those two banners
  with different sums.

## Fixes, before another Modules step trusts the sim

1. Keep one alignment input, and make it the measured edge plus a
   route term. Programmed step = edge − backoff, from the same
   parameters the bitstream uses. The route term is what differs
   between the fetch pass and the P/D miss, because those edges were
   the same codes. A new center constant per image is the route term
   with the name changed, and it is only known after the load.

2. Split the script. One section replays old UARTs and may carry the
   old plusargs. The section whose success prints `stand-in matches`
   runs the programmed steps of the image about to be loaded, and
   fails if those plusargs disagree with `LANE0_STEP`, `LANE1_STEP`,
   `WLEVEL_BACKOFF`, and `WLEVEL_BACKOFF1`. Label that run as "bytes
   if the column matches the last accepted place." It is a software
   check. It becomes a board prediction only when the previous
   bitstream's route was kept.

3. Until a build can keep the DDR3 route while the imem changes, every
   new place-and-route is a new eye measurement. The software sim can
   still run first, at the last accepted alignment, so a CPU bug is
   caught before the load. The first UART decides whether the column
   survived. A miss stops the step. It is not turned into the next
   center and loaded again. That is the rule that already ended the
   step-9 trial and the P/D trial.

4. Keep `+ddr3_pd_eye` as a record of two misses, and keep it out of
   any sentence that says the column is known. It has no offset 0.
   Do not load another backoff to hunt one. Lane 1 at 6 and at 7 were
   the same alias, and lane 0's edge moved so the extra backoff did
   not move its step. The fetch image now on the Dock is a pass at
   `0007` `000C`. The centers from `4dfd5d8` call that pair a miss.
   The next model has to follow the edge the controller just measured,
   which is what the fetch place did and what the fixed centers do not.
