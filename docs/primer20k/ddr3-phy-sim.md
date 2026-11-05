# DDR3 PHY sim (Icarus, Micron, prim_sim)

This is not a Dock load and not a write-step eye. `sim/Ddr3UserModel.v`
stays the fast command-port stand-in. This bench is the soft
`ddr3_controller` against the Micron model and Gowin `prim_sim`.

```bash
sim/run_ddr3_phy.sh
```

The script prepends `~/.local/bin` to `PATH`. Icarus is not a system
package on this machine; 12.0 was built there. `GOWIN_PRIM_SIM`
overrides the default `/opt/gowin-eda-ide/simlib/gw2a/prim_sim.v`.
The compile line is `iverilog -g2012 -s tb_ddr3_phy` with
`-D SIM -D den1024Mb -D sg25 -D x16`. The model keeps its sparse
files under `/tmp/ddr3-phy-model` (`+model_data+`), not the default
`/tmp` names.

Exit 0 is only `PHY_SCORE pass`: the DDR3-800 slot `dq_in[0]`
matches the written word, and the Micron model printed no `ERROR`.
`read_calib_done` and `data_ready` do not pass the run.
`data_ready` is a cycle count in the controller. A byte in any
other IDES slot does not pass either.

## What this run did

Clocks are 100 MHz `pclk` and 400 MHz `fclk`. `ck` lags `fclk` by
90 degrees. With `ck` leading `fclk`, the model rejected the write
on `tDQSS`, `tDSS`, and a missing DQS edge.

Write leveling sampled DQ as 0 at codes 24 and 25, then 1 at code
26, and committed. Those edges still warn that the CK capture is
indeterminate, so code 26 is not a Dock step. Read calibration
committed at `rclkpos=1`, `rclksel=7` because `rburst` was seen
twice. It does not compare `dq_in`. There is no Micron `ERROR`.
CKE is delayed 400 ps in the bench, which is the pad delay the
direct CKE register does not have. Without it the model reports
`tIH` by 275 ps. Reset and CKE are still the short `SIM` waits
(warnings ask for 200 us and 500 us). `tZQinit` is not shortened.

The writes land. The model prints:

- column 0: `...1111`
- column 1, same burst: `...22221111`
- column 16: `...3333`

`dm_out` used to be a blocking `8'hff` every `pclk`. `OSER8_MEM`
samples DM on that same edge, so the beat stayed masked and the
read was the unwritten X. The bench also holds `din` until `busy`
falls. The controller reads `din` at the data beat, not at `wr`.

The reads do not pass.

- Column 0 at `data_ready`: `dq_in[0]` is X. The DQ pin does show
  `2222` for one sampled CK edge of that burst.
- Column 1 at `data_ready`: `dq_in[0]` is X. The DQ pin shows
  `1111`, and IDES has `1111` in slots 1 and 3
  (`dout128` = `xxxx1111xxxx1111xxxxxxxxxxxxxxxx`). Slot 7 has
  `1111` one `pclk` earlier. `2222` never appears. That is the
  even-word alias, in the wrong slot for the Dock compare.
- Column 16 was stored, and the sampled read burst on DQ is X.
  `3333` is not in `dout128`.

The score is `PHY_SCORE fail`. An extra 625 ps on the read strobe
was tried. Calibration moved to `rclkpos=2`, `rclksel=0`, and the
byte disappeared. That delay is not in the tree.

The bench waits 8 extra `pclk` after refresh. The controller ends
refresh at tRC (20 nCK). The model requires tRFC (110 ns) before
the next ACT.

## `SIM` shortcuts in the controller

These are labeled in `gowin/primer20k/ddr3/ddr3_controller.v`.

- `dout` is `dq_in[4]`. DDR3-800 silicon uses `dq_in[0]`. The bench
  scores `dq_in[0]` (`dout128[127:112]`).
- `dllstep` is forced to 25 and `dlllock` is forced high. The DLL
  primitive does not run.
- Reset and CKE waits are 1 and 19 `pclk` ticks. ZQ stays at 512
  `pclk`.
- Write leveling starts at `8'h18` instead of 0. An X or Z on DQ is
  not treated as a high.
- Read calibration starts at `rclkpos=1`, `rclksel=6`, and commits
  on `rburst`.
- `WLEVEL_COUNT` and `RCALIB_COUNT` are 2.
- `dm_out`'s per-cycle default is nonblocking, so the unmask reaches
  the pin. Serializer inputs are cleared while reset is held, so
  the first beat is not X.

Icarus also needs the generate indexes declared as `genvar` outside
the `for`.

## What Modules should re-check on the Dock

The hardware check is still the prologue compare, not
`read_calib_done` and not a `data_ready` pulse. This bench stores
the two beats of a BC4 pair as different bytes. A column-1 read
returns the column-0 byte on DQ and in IDES slots 1 and 3. The Dock
slot, `dq_in[0]`, is X, so this is not yet the Dock compare and it
is not a pass. A later `PHY_SCORE pass` has to show `dq_in[0]`
equal to the written word, with no Micron `ERROR`. Code 26 and
`rclksel=7` are not a bitstream.
