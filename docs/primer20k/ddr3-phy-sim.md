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
`-D SIM -D den1024Mb -D sg25 -D x16`.

Exit 0 is only `PHY_SCORE pass`: the DDR3-800 slot `dq_in[0]`
matches the written word, and the Micron model printed no `ERROR`.
`read_calib_done` and `data_ready` do not pass the run.
`data_ready` is a cycle count in the controller. It rises when the
captured word is X.

## What this run did

Clocks are 100 MHz `pclk` and 400 MHz `fclk`. `ck` lags `fclk` by
90 degrees, which is the PLL delay the controller comment describes.
With `ck` leading `fclk`, the model rejected the write: `tDQSS`,
`tDSS`, and a missing DQS latch edge, and both read slots were X.

With `ck` lagging, write leveling sampled DQ0 and DQ8 as 0 at codes
24 and 25, then 1 at code 26, and committed. The same edges carry
`tWLS` / `tWLH` warnings that the CK capture is indeterminate, so
code 26 is not a Dock step. Read calibration then committed at
`rclkpos=1`, `rclksel=7` because `rburst` was seen twice. It does
not compare `dq_in`.

The three reads (`1111` at column 0, `2222` at column 1, `3333` at
column 16) all came back `X` in every IDES byte. `dout128` was
`xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. One `pclk` later the dock slot
was `Z`. The model printed no `ERROR` on those writes and reads.
The score is `PHY_SCORE fail`. This run does not reproduce the
Dock even-word alias. It stops earlier: the read never returns a
word.

One init `ERROR` is still present: `tIH` on CKE by 275 ps. Reset
and CKE are still the short `SIM` waits (warnings ask for 200 us
and 500 us). `tZQinit` is not shortened. The old 2-tick ZQ made the
model reject the following ACT.

## `SIM` shortcuts in the controller

These are labeled in `gowin/primer20k/ddr3/ddr3_controller.v`.

- `dout` is `dq_in[4]`. DDR3-800 silicon uses `dq_in[0]`. The bench
  scores `dq_in[0]` (`dout128[127:112]`).
- `dllstep` is forced to 25 and `dlllock` is forced high. The DLL
  primitive does not run.
- Reset and CKE waits are 1 and 19 `pclk` ticks. ZQ stays at 512
  `pclk`.
- Write leveling starts at `8'h18` instead of 0. An X or Z on DQ is
  not treated as a high. (`if (~dq)` used to count X as a pass.)
- Read calibration starts at `rclkpos=1`, `rclksel=6`, and commits
  on `rburst`.
- `WLEVEL_COUNT` and `RCALIB_COUNT` are 2.

Icarus also needs the generate indexes declared as `genvar` outside
the `for`. `for (genvar i = ...)` made the index a variable, and
Icarus then rejected it on a primitive output.

## What Modules should re-check on the Dock

The hardware check is still the prologue compare, not
`read_calib_done` and not a `data_ready` pulse. This bench will not
show the Dock alias until a read returns a word. A later PHY sim
that prints `PHY_SCORE pass` has to show `dq_in[0]` equal to the
word that was written, with no Micron `ERROR`. Code 26 and
`rclksel=7` from this run are not a bitstream.
