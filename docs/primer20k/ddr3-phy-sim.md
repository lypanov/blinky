# DDR3 PHY sim (Icarus, Micron, prim_sim)

`sim/Ddr3UserModel.v` stays the fast command-port stand-in. This
bench is the soft `ddr3_controller` against the Micron model and a
patched Gowin `prim_sim`. The controller trains the write eye before
it raises `read_calib_done`. The Dock load is `docs/primer20k/step5-ddr3.md`.

```bash
sim/run_ddr3_phy.sh
```

The script prepends `~/.local/bin` to `PATH`. Icarus is not a system
package on this machine; 12.0 was built there. `GOWIN_PRIM_SIM`
overrides the default `/opt/gowin-eda-ide/simlib/gw2a/prim_sim.v`.
`sim/patch_prim_dqs.py` copies that file and replaces the DQS
255-tap cascade with constant transport delays, `N*0.025-0.001` ns.
The vendor cascade does not reach calibration under Icarus. A
variable `#(WSTEP*0.025)` delay matches a CK edge and the Micron
model drops the strobe. The vendor file is not edited.
The compile line is `iverilog -g2012 -s tb_ddr3_phy` with
`-D SIM -D den1024Mb -D sg25 -D x16`. Sparse memory files go under
`/tmp/ddr3-phy-model` (`+model_data+`).

Exit 0 is only `PHY_SCORE pass`: `dq_in[0]` at `data_ready` matches
the written word, and the Micron model printed no `ERROR`.
`read_calib_done` alone does not pass the run. A byte in any other
IDES slot does not pass either.

## What this run did

Clocks are 100 MHz `pclk` and 400 MHz `fclk`. `ck` lags `fclk` by
90 degrees. With `ck` leading, the model rejects the write on
`tDQSS` / `tDSS`.

Write leveling commits at code 26/26. The eye then scans offsets
-4..+12 from that edge and locks the first row with three
consecutive full-word passes. This run locks steps 22/23
(`run=16/17`), `rclkpos=1`, `rclksel=3`, at cycle 1984. Code 26 is
the model's write-level edge, not a Dock step. The model stores
the writes:

- column 0: `1111`
- column 1, same burst: `22221111`
- column 16: `3333`

Read calibration's first `rburst` is `rclkpos=1`, `rclksel=7`.
That is the trailing edge: `dq_in[0]` there is X. Under `SIM` the
commit steps back one CK (4 steps of 1/4 CK), to `rclksel=3`.
At `data_ready`, `dq_in[0]` is `1111`, `2222`, and `3333` for
those three reads. There is no Micron `ERROR`. The score is
`PHY_SCORE pass`.

`+phase_sweep` prints `dq_in[0]` across the gate. `rclksel` 1, 3,
and 4 at `rclkpos` 1 return the three words. `rclksel` 7 does not.
The default run does not sweep.

This pass does not reproduce the Dock even-word alias. Column 1
comes back as `2222` in `dq_in[0]`. `1111` is the other beat of
that burst and shows up in other slots, and in earlier cycles
while the previous read shifts out. The scored cycle is the
written word.

CKE is delayed 400 ps in the bench (pad delay the direct register
does not have). Without it the model reports `tIH` by 275 ps.
The bench waits 8 extra `pclk` after refresh. The controller ends
refresh at tRC; the model requires tRFC (110 ns). Reset and CKE
are still the short `SIM` waits. `tZQinit` is not shortened.

## `SIM` shortcuts in the controller

Labeled in `gowin/primer20k/ddr3/ddr3_controller.v`.

- `dout` is `dq_in[4]`. DDR3-800 silicon uses `dq_in[0]`. The bench
  scores `dq_in[0]`.
- `dllstep` is forced to 25 and `dlllock` is forced high.
- Reset and CKE waits are 1 and 19 `pclk` ticks. ZQ stays at 512.
- Write leveling starts at `8'h18`. An X or Z on DQ is not a high.
- Read calibration starts at `rclkpos=1`, `rclksel=6`, commits on
  `rburst`, then steps back one CK. Silicon keeps the `rburst`
  phase.
- `WLEVEL_COUNT` and `RCALIB_COUNT` are 2.
- `dm_out`'s default is nonblocking, so the unmask reaches the pin.
  Serializer inputs are cleared during reset.

## What the Dock showed

The same trainer on the Primer 20K Dock locked steps `0009`/`0007`
(write-level edges `000D`/`000A`) and the step-5 self-test passed.
`rclkpos=1`, `rclksel=3` matched this bench. The sim lock 22/23 is
the wide model eye, not the Dock pair. See `step5-ddr3.md`.
