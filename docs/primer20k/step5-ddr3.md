# Primer 20K step 5: P chain and D chain

Step 4 is accepted. This image is `FPGA_IMAGE=ddr3pd`. It is not the
Nano 4K `pdchain` image, and that image is not loaded here. The
software is the same walk as `docs/hyperram/step5.md`: the ROM holds
the unfixed module words, the prologue at `0x1C00` walks both chains,
and the ten fixed words are overlaid from a constant-address table
so the delay loop does not take a DDR3 round trip. `extraChecks` is
37. The pin gate is 45 bits. Slots 32..36 are the chain compares.
The UART still prints 40 bits, so those five slots are not on the
wire.

The delay word stays `60000004` (N=262144). The loop is unchanged,
so the period stays `576*N+788`. At N=262144 that is one edge every
150995732 `pclk` cycles, 0.640747 Hz, a full blink of 0.320373 Hz,
93.641 frames at 30 fps. The rate is not adjusted to a camera.

The pattern sum is the shared prologue, before the chain runs. The
controller, the BC4 write (`A[12]=0`), and the column address are
the same RTL as the fetch image. `ddr3_controller.v` has no
`DDR3_PD` branch. Three SRAM loads programmed different write steps
and printed one even-word alias. Lane 0 steps 10 and 11, and lane 1
steps 5, 6, and 7, are that bin. `+ddr3_pd_eye` names those codes
and has no offset-0 pair. The stand-in has no write-level input.

`WSTEP` is not the missing eye. The Gowin `DQS` model, `X4` mode,
is a 25 ps tap (`del = 0.025` in `prim_sim.v`). `DQSW0` is
`dqsw0_dly_in[WSTEP]`. `DQSW270` is the inversion of the tap at
`DLLSTEP+WSTEP`. One code slides both clocks and leaves DQ against
DQS where it was. `fclk` in the timing report is 2.584 ns, so one
beat is 1.292 ns, about 52 taps. Read calibration commits the first
`rburst` and does not compare `dq_in`. `RCLKSEL` moves that pulse
by 1/4 CK. A place that accepts the next quarter-cycle keeps the
neighbour beat, and write-level backoff cannot put it back. The
change this image needs is that compare.

## Simulation, before the load

`sim/run_ddr3_standin.sh` builds no bitstream and loads neither FPGA.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| ddr3pd | 5 | 3668 | 38626 |
| ddr3pd | 8 | 5396 | 40354 |
| ddr3pd | 32 | 19220 | 54178 |

3668, 5396, and 19220 are `576*N+788`. The first edge is 5076 cycles
later than the stored-BL image. Those numbers are the chain when
the model column is aligned, at default steps 10 and 10. That pair
is not a Dock program, and `sim/run_ddr3_standin.sh` does not run
it. A `ddr3pd` blink fails the script unless its lane plusargs are
a loaded pass. There is no such pass, so the script prints
`stand-in replays matched` and refuses `stand-in matches`. The
three Dock pairs print R5 `AAAAAAAA`, R9 `55555536`, mask `F0`.
The sim samples that hold at PC `0x1394`.

Bare `+ddr3_fetch_eye` leaves both lanes at 10. It holds at
`0x1394` with R5 `00544054`, R9 `00A9C18C`, mask `30`, and 0 edges.
That image is not loaded.

`--break-slot 32` and `CHAIN_FIX=0` are holds of that same aligned
column (`0x1D8C` / `0x1D90`). The script does not run them: they
reach the chain only when the column is the model's default, and
that default is not on the Dock. A UART mask of `FFFFFFFFFF` with
`H` and PC `1D8C` or `1D90` is one of those holds, not the blink.

## Dock, first SRAM load

One SRAM load, `openFPGALoader --busdev-num 003:078 -b tangprimer20k
-m`, no flash. The Nano 4K was not opened.

TNS is 0.000 on `pclk` and `cpu_clk`, setup and hold, 0 failing
endpoints. The bitstream is `ddr3pd_n262144.fs`. The ALU bitstream
and the accepted fetch bitstream were not overwritten. SRAM only,
`003:078`. The Nano 4K was not opened. No webcam: the pin did not
reach the delay loop.

The programmed steps are still `0007` `000B`. The line repeats:

```
CH1394 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 0007 000B
```

Calibration `C`, hold, PC `0x1394`, mask `F0`, R5 `AAAAAAAA`,
R9 `55555536`. UART order is lane 1 then lane 0, so lane 1 is
`0007` and lane 0 is `000B`. With backoff 1 and 3 that is edges
`000A` and `000C`. The sums are the even-word alias.
`+ddr3_pd_eye +ddr3_lane0=11 +ddr3_lane1=7` prints this line.
`+ddr3_place_fetch +ddr3_lane0=11 +ddr3_lane1=7` is a different row:
R5 `FFAAFFAA`, R9 `02540136`, mask `30`. The fetch witness at these
steps is a pass on the fetch place, not on this one.

## Backoff 2 and 4

One named load. Lane 0 backoff 2, lane 1 backoff 4. TNS is 0.000 on
`pclk` and `cpu_clk`, setup and hold, 0 failing endpoints. The line
repeats:

```
CH1394 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 0006 000B
```

Same sums, steps `0006` `000B`. Lane 1 is `0006` and lane 0 is
`000B`. Lane 1's edge stayed `000A` (`0006` plus 4). Lane 0's edge
moved to `000D` (`000B` plus 2), so the extra backoff did not move
lane 0's programmed step. Lane 1 at 6 and lane 1 at 7 are the same
alias while lane 0 stays at 11.
`+ddr3_pd_eye +ddr3_lane0=11 +ddr3_lane1=6` prints this line.

The accepted fetch bitstream was loaded back before the next try.
That reload's lane 0 edge was `000D`, so the steps were `0007`
`000C`, and the line was the fetch pass.

## Backoff 3 and 5

One named load. Lane 0 backoff 3, lane 1 backoff 5. TNS is 0.000 on
`pclk` and `cpu_clk`, setup and hold, 0 failing endpoints. The line
repeats:

```
CH1390 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 0005 000A
```

Steps `0005` `000A`. Lane 1 is `0005` and lane 0 is `000A`. The
edges stayed `000A` and `000D` (`0005` plus 5, `000A` plus 3). The
column, the beats, the write address, and both sums match the two
earlier lines. The programmed code moved. The bytes did not.
`+ddr3_pd_eye +ddr3_lane0=10 +ddr3_lane1=5` prints this line.

## No WSTEP is this eye

The first P/D load used the fetch backoff and the fetch edges, so
its steps were the fetch eye, `0007` and `000B`. The fetch bitstream
passes at those steps. The P/D bitstream at those steps is the
alias. Both images present the same `wstep_run` / `wstep1_run` to
the same DQS primitive (`WSTEP(i0 == 0 ? wstep_run : wstep1_run)`).

The controller's own comment is the primitive's split: `DQSW0` is
`fclk` delayed by `WSTEP`, and `DQSW270` is `fclk` delayed by
`WSTEP+DLLSTEP` plus 180 degrees. The vendor `DQS` model (`X4`)
implements that as one 25 ps line, index `WSTEP` for `DQSW0` and
index `DLLSTEP+WSTEP` for the 270-degree clock. A different backoff
does not make the DQ-to-DQS phase the fetch image had, because the
fetch image's phase did not depend on `WSTEP` either. The three
measured codes are inside one beat: half of the 2.584 ns `fclk` is
1.292 ns, and 1.292 / 0.025 is about 52 taps.

`tDQSS` is a quarter of `tCK`, here about 26 taps either side of
the write-level trip. The samples are within five taps of that
trip, on the same side the fetch pass occupies. Walking out to the
quarter-cycle boundary would leave the write window. It would not
reproduce the fetch column, which already sits inside the window.

Read calibration is the search that does differ by place. It issues
a BL8 read and commits the first `rclksel` / `rclkpos` with `rburst`
set, `RCALIB_COUNT` times. It never looks at `dq_in`. `RCLKSEL`
shifts the read pulse by 1/4 CK, and one miss of `rburst` because
the route into the sample register changed takes the neighbour
quarter-cycle. That is a beat, not a 25 ps tap. The backoff
parameters only subtract from `WSTEP`. They cannot center it.

The backoff constants stay at 1 and 3. Steps `000A` and `0005` were
the next integer under the alias bin. That load is the line above,
and it is the same bin. Another host backoff would be the same
guess. The prologue is the compare at `0x1390`, before `0x1C00`,
and the controller has no `DDR3_PD` branch that could give it a
different eye.

The change is in `READ_CALIB`, after write leveling has the edge
and `wstep_run` has had the backoff subtracted. Write `16'hA55A`
to column 0 and `16'h5A5A` to column 1. Then advance `rclksel` and
`rclkpos` only while the read of column 0 is not `16'hA55A` or the
read of column 1 is the even word. Commit after `RCALIB_COUNT`
matches, and do not commit on `rburst` alone. If all 32 read gates
miss, walk both lanes one code down from the edge, lane 1 kept two
codes below lane 0, and repeat the read sweep. Stop at the first
code where both columns match. If none match inside the `tDQSS`
window, leave `read_calib_done` low. The constant
`WLEVEL_BACKOFF` cannot see the route this place-and-route moved,
and the prologue will keep holding until that search exists.

The accepted fetch bitstream was loaded back. This reload's steps
are `0007` `000C`, and the line is the fetch pass: delay-loop PC,
mask `FFFFFFFFFF`, R5 `00000000`, R9 `FFFFFFE1`. The Dock is on
that image. No webcam. Nothing was written to flash. The Nano 4K
was not loaded. Step 6 is not started.
