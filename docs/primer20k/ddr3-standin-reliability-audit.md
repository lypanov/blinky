# DDR3 stand-in reliability audit

The Dock stays on the accepted fetch image. This note does not load a
bitstream and does not start step 6. Step 5 remains with the stand-in
agent until a bitstream and this model agree. The audit is what has
to change before a later Modules.Load step can trust `stand-in matches`.

The sim agent's thread was not readable from this worker.
`batch-fetch-details` only runs on a managed cloud agent. The local
store for `bc-5a35e67c-7a90-564d-ac3b-59f0c2650296` has an empty file
index, and `/cursor/stores/bc-5a35e67c-7a90-564d-ac3b-59f0c2650296` is
not on this machine. What follows is from the commits, `sim/Ddr3UserModel.v`,
`sim/run_ddr3_standin.sh`, the controller, and `docs/primer20k/`.

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
| Fetch, both lanes 10, then both lanes 9 (`878b767`, `05a8c61`) | `AAAAAAAA` both times, steps `000A` then `0009` | `+ddr3_place_fetch` forced offset +1 and ignored the lane numbers. The script's pass was both lanes at 9. The Dock at 9 was the same alias. |
| Fetch pass image (`0cd9710`) | steps `0007` `000B`, R5 `00000000`, full mask, blink | `+ddr3_fetch_eye` with the lanes left at 10. In that Verilog the flag does not set a center. It only skips the place-fetch override. Center stays 10, so the green run is the ALU eye. `+ddr3_wlevel_eye` hardcoded offsets −1 and 0 and did not read the lane plusargs. |
| Same image, flag fixed (`4dfd5d8`) | same UART, no reload | `+ddr3_fetch_eye` now sets centers 11 and 7, and the pass case passes both lane numbers. That matches the program already on the Dock. The model still has no write-level input. |
| P/D chain (`df7b130`, one SRAM load) | same printed steps `0007` `000B`, R5 `AAAAAAAA`, R9 `55555536`, mask `F0`, hold `0x1394` | `+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7` is a pass (R5 0, mask `1fffffffffff`). `+ddr3_place_fetch` at those lanes is R5 `FFAAFFAA`. Nothing in the committed model prints `AAAAAAAA` for lanes 11 and 7. |

The controller already says this. `wstep_run` is the write-level edge
minus `WLEVEL_BACKOFF` (`gowin/primer20k/ddr3/ddr3_controller.v`). The
comment on those parameters says the stand-in does not read the edge.
Fetch and the P/D image both subtract 1 and 3, and both UARTs printed
`0007` `000B`, so the edge codes were `000C` and `000A` on both builds.
The column still moved. A model whose only alignment input is the
programmed step has to print one R5 for that pair. The board printed two.

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
   the step model is switched off while the mask is set). The working
   tree, not yet committed, adds `+ddr3_pd_eye` with centers 10 and 6 so
   the loaded steps become the alias, and moves the blink witness to
   lanes 10 and 6. Those lanes were not loaded. That is the step-9 move
   again: the inferred center is promoted to the pass before the Dock
   has run it.

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
- Adding an image-named center (`place_fetch`, `fetch_eye`, `pd_eye`)
  after the UART and moving the green blink onto steps that have not
  been loaded.
- Loading that inferred center as the next bitstream and calling the
  script a prediction. Both lanes at 9 were that prediction. The Dock
  still printed `AAAAAAAA`.
- Modules accepting `stand-in matches` without running the witness at
  the steps the UART prints. That check is what rejected `0cd9710`.
  It is also what has to happen to a green `+ddr3_pd_eye` run at lanes
  10 and 6.

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

4. Leave `+ddr3_pd_eye` out of the pass path. Centers 10 and 6 describe
   the miss. They are not a witness the Dock has run. The committed
   record is the right one: same steps as the fetch pass, R5
   `AAAAAAAA`, and no plusarg for that row.
