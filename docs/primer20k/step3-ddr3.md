# Step 3: LDB/STB and the .rsc reader on the Primer 20K (not proven)

`FPGA_IMAGE=ddr3rsc` is the DDR3 prologue, the fixup ALU, then the
byte reader at `0x1800`, then Blink3. `FPGA_IMAGE=ddr3` stays the
memory-only prologue. `FPGA_IMAGE=ddr3fixup` stays the ALU image.
`FPGA_IMAGE=rsc` stays the Nano 4K HyperRAM reader. The failure path
is the two-instruction hold, so the ALU still sits at `0x1400` and the
reader at `0x1800`. The reader hold is `0x1B44`.

The DDR3 path is unchanged from the ALU proof: 16 controller clocks
after busy, a refresh, 16 more clocks, read calibration after 16 hits,
`HOLD` on a user read, and a one-cycle `WLOADN` pulse so the write
delay reloads. Lane 0's `WSTEP` stays forced to 10.

## Locked rate, from simulation only

Verilator, before any load, N = 5, 32, 128, 512, 1024. The edge
periods were 3668, 19220, 74516, 295700, and 590612. Residual 0
against the step-1 line:

`pclk/edge = 576*N + 788`

N = 262144 is 150,995,732 controller clocks per edge.

- edge = 96750000/150995732 = 0.640747 Hz
- full blink = 0.320373 Hz
- 93.641 frames at 30 fps

The reader is outside the delay loop. At N = 5 the first edge moved
from the ALU image's cycle 25434 to cycle 32902; the period stayed
3668. The trace stored a zero at all 40 check addresses (`0x7C0`
through `0x87C`) and never visited `0x1B44`. `+ddr3_corrupt` and
`--break-slot 30` both ended with 0 LED edges.

The pin requires those 40 zeros. The armed mask is 40 bits. Slots
20..31 are the lane word `0x44332211`, the four lane bytes, the
neighbour `0xA5A5A5A5`, the updated byte `0x77`, the surviving byte
`0x33`, the name, the key `0x13579BDF`, version 1, and size `0x100`.

## Hardware

The first SRAM load of `ddr3rsc_n262144.fs` on bus 003 device 078 did
not blink. UART on M11, after calibration: PC `0x1394` (the prologue
hold), mask `00000000F0`, R5 `AAAAAAAA`, raw `wstep` `000D`,
`wstep_run` `000A`. That is the same odd-column pattern-sum the first
ALU placement produced. Place algorithms 0, 1, and 2 all sat there.
The reader never started, so this was not an LDB/STB failure.

Forcing lane 0 to step 9, with lane 1 left on its calibrated step,
changed R5 from `AAAAAAAA` to `AAFFAAFF`: lane 0's bytes became `FF`
and lane 1's stayed `AA`. A later placement that walked lane 1 across
0..255 with lane 0 held at 9 parked at lane 1 = `0xFA` with R5
`65FFFFFF` and the complement sum `A9FFFFE1`. Three bytes matched.
The CPU stayed in the prologue hold and L14 stayed dark. Lane 0 at 8
and at 10 were worse (`20AA38AA`, `9AFF9AFF`). No pair put R5 at
`FFFFFFFF`.

The webcam was not used. The locked rate was not changed to chase the
camera. The Nano 4K was not loaded. The Dock was put back on the
accepted ALU bitstream `ddr3fixup_n262144.fs`.

## Simulation stand-in

`sim/Ddr3UserModel.v` is the command port after calibration. The PHY
(OSER8, DQS, the DLL) is not in it, and the controller and the bridge
were not changed to hide a miss. Read `data_ready` is still the 9th
clock, read `busy` clears on the 10th, write and refresh `busy` clear
on the 6th, and `calib` rises after 64 clocks. The array is still 4096
halfwords, two bytes per column. A halfword write is one BC4 beat: DM
unmasks that beat and drives `din` onto both lanes. It does not mask
one byte of the x16 beat. The bridge has already merged a byte store
into `din`. Both lanes have to land on that same beat, or the merged
byte does not come back.

`sim/run_ddr3_standin.sh` is the witness. N = 5 is `--mov-iter 5`.
The board was not loaded for this model. No bitstream was built, and
neither FPGA was programmed.

### Passing eye

`+ddr3_center` is the programmed step the data eye is centered on.
The default is 10, which is the ALU place: the controller forces lane
0's `wstep_run` to 10, and lane 1's write-level result landed on that
same step. `HOLD` is on, and the read's last cycle reloads the write
delay (`WLOADN`). The reader bitstream's place is not this one. Its
center is 9, so the same force of 10 is one step above the eye. That
case is `+ddr3_center=9`, below.

| image | first edge | period | R5 | R9 | mask |
| --- | --- | --- | --- | --- | --- |
| `ddr3` | 22634 | 3668 | `FFFFFFFF` | `FFFFFFE1` | `FF` |
| `ddr3fixup` | 25434 | 3668 | `FFFFFFFF` | `FFFFFFE1` | `FFFFFFF` |
| `ddr3rsc` | 32902 | 3668 | see below | `FFFFFFE1` | `FFFFFFFFFF` |

The reader reuses R5, and the blink edge is at PC `0x101C`, so R5
there is 0. On the prologue and ALU images R5 is still the pattern
sum. A set mask bit is a check word stored as zero. The 40 reader
bits are `0x7C0` through `0x87C`. N = 32 on the reader image has
period 19220 and first edge 48454, which is 32902 + 576*27. The
locked line was not refit.

The command-port byte walk passes only on this eye. Four STB bytes
`11 22 33 44` at `0x920` read back as `0x44332211`. The neighbour
word `0xA5A5A5A5` at `0x924` survives, including after STB `0x77` at
byte 3, which updates the word to `0x77332211` and leaves byte
`0x33` in place. A flat `mem[idx] <= din` store would pass that walk
with a wrong DM or a one-lane write as well. The cases below fail it.

### What each plusarg does

| plusarg | command-port effect |
| --- | --- |
| (none) | center 10, both lanes programmed to 10, `HOLD`, `WLOADN`, one BC4 beat. This is the ALU place |
| `+ddr3_center=N` | programmed step the data eye is centered on. The reader place measured on the Dock is 9. The step register is a separate plusarg |
| `+ddr3_lane0=N` `+ddr3_lane1=N` | programmed write delay for that lane. Offset `N - center` selects the beat. 0 lands on the addressed column. +1 is the even-word alias. -1 lets the odd word overwrite the group. Any other offset stores that lane's byte that many columns away |
| `+ddr3_nohold` | the read FIFO is not reset |
| `+ddr3_nowload` | no `WLOADN` reload after `HOLD` |
| `+ddr3_dm_all` | `din` is written to all four beats of the group |
| `+ddr3_dm_lane0` | only lane 0, `DQ[7:0]` |
| `+ddr3_dm_lane1` | only lane 1, `DQ[15:8]` |
| `+ddr3_corrupt` | reads return 0 |
| `+ddr3_late` | `dout` is one clock after `data_ready` |

DM faults ignore the write-delay eye. The port test still reports
edge 0 on the good model, fails closed on `+ddr3_corrupt`, and
reports edge 1 on `+ddr3_late`.

### Reader image, 0 LED edges

The UART signatures are from the two-instruction prologue hold
(`0x1390`/`0x1394`), which is what `ddr3rsc` and `ddr3fixup` use.
The prologue-only image's failure path is the scanner, and that
scanner overwrites R5, so these R5 values are checked on `ddr3rsc`.

| case | PC | mask | R5 | R9 |
| --- | --- | --- | --- | --- |
| `+ddr3_center=9` | prologue hold | `F0` | `AAAAAAAA` | `55555536` |
| `+ddr3_center=9 +ddr3_lane0=9` | prologue hold | `F0` | `AAFFAAFF` | `550054E1` |
| `+ddr3_lane0=11 +ddr3_lane1=11` | prologue hold | `F0` | `AAAAAAAA` | `55555536` |
| `+ddr3_lane0=9 +ddr3_lane1=9` | prologue hold | `F0` | `55555554` | `AAAAAA8C` |
| `+ddr3_lane1=9` | prologue hold | `F0` | `550054FF` | `AAFFAAE1` |
| `+ddr3_lane0=9` | prologue hold | `F0` | `00550054` | `FFAAFF8C` |
| `+ddr3_nohold` | prologue hold | `A0` | `AAAAAAAA` | `55555536` |
| `+ddr3_nowload` | `0x1B44` | `FFFFFFF` | `FFFFFFBF` | `FFFFFFE1` |
| `+ddr3_corrupt` | prologue hold | `0` | `0` | `0` |
| `+ddr3_dm_all` | prologue hold | `C0` | `55555554` | `AAAAAA8C` |
| `+ddr3_dm_lane0` | prologue hold | `30` | `00FF00FF` | `1EE11EE1` |
| `+ddr3_dm_lane1` | prologue hold | `0` | `FF00FF00` | `E11EE100` |
| `--break-slot 30` | `0x1B44` | `BFFFFFFFFF` | `0` | `FFFFFFE1` |

One step above the eye writes the even word of a BC4 group into both
words of the group on that lane, and does not let the odd word
replace it. An odd column then reads back the even column, which is
the pattern sum `AAAAAAAA` and the complement sum `55555536`. An odd
column that was stored on its own is kept: MT[1] at `0x14`, MT[2] at
`0x18`, the alias word `0x11111111` at `0x114`, and the sentinel at
`0x7F0`. Those four checks still pass, so the mask is `F0`. On the
ALU place that step is programmed 11. On the reader place it is the
forced step 10 (`+ddr3_center=9`).

`+ddr3_center=9 +ddr3_lane0=9` is the sweep that forced lane 0 to 9
and left lane 1 where the place put it. Lane 0 is back in the eye
(its bytes sum to `FF`) and lane 1 stays on the alias (`AA`), so R5
is `AAFFAAFF` and R9 is `550054E1`. The mask is still `F0`.

One step below the eye writes the odd word over both words of the
group. On the ALU place that is programmed step 9: R5 `55555554`,
R9 `AAAAAA8C`, mask `F0`. The UART value `AAABB34B` from lane 0
forced to 11 on the reader place is two steps above that place's
eye. It is not this whole-beat result.

`+ddr3_nohold` is a read alias. The writes land, and a column with
`addr[1]` set returns the even column. The sums match, but the
isolated odd words do not, so the mask is `A0` (MT[2] and the
sentinel still match). This is not step 1's earlier mask `0000`.

`+ddr3_nowload` does not move the prologue. Those stores happen
before any read, so the low 28 mask bits are set and R9 is still
`FFFFFFE1`. `HOLD` stops the write clock, and without the reload a
store that follows a read lands two columns later. The eye test
writes `0x5A74` at column `0x28`, reads it, then writes `0x1111` and
finds that half at `0x2A`. The byte walk is the same case, so the
CPU sits in the reader hold at `0x1B44` with the top 12 mask bits
clear. R5 there is `FFFFFFBF`, the reader's own accumulator, not
the prologue sum. The refresh pair does not clear the skew.

Any other offset stores that lane's byte that many columns away.
`+ddr3_lane1=12` on the default center leaves the `0x11` at column
`0x30` and puts the `0x22` at `0x32`. The parked UART residuals
`65FFFFFF` /
`A9FFFFE1`, `AAABB34B`, `20AA38AA`, and `9AFF9AFF` are not
reproduced. Those were sub-beat DLL eyes from one placement. The
command-port model does not invent them.

`+ddr3_dm_all` paints every beat of the group, so a neighbour in the
same burst does not survive and the prologue is not the `F0` alias.
`+ddr3_dm_lane0` leaves lane 1 at `00` (`00FF00FF`).
`+ddr3_dm_lane1` leaves lane 0 at `00` (`FF00FF00`).

`+ddr3_corrupt` returns 0, and the CPU image produces 0 LED edges.
`--break-slot 30` adds 1 to one reader expected constant. The
prologue and ALU checks stay zero. Bit 38 (reader slot 30) stays
clear, the mask is `BFFFFFFFFF`, and the CPU stays in the reader
hold with 0 LED edges.

The board was not loaded for the model change itself.

## Fidelity check (2026-11-05, stop)

`sim/run_ddr3_standin.sh` on `9f370e6` printed `stand-in matches`.
The default eye (both lanes at step 10, `HOLD`, `WLOADN`) predicts a
pass for `ddr3rsc`: mask `FFFFFFFFFF`, R9 `FFFFFFE1`, R5 `00000000`
once the reader has reused it, PC in the Blink3 loop, full blink
0.320373 Hz. The odd-column signature is a different plusarg,
`+ddr3_lane0=9 +ddr3_lane1=9`: prologue hold, mask `F0`, R5
`AAAAAAAA`, R9 `55555536`.

The accepted ALU bitstream, sampled before the step-3 load, matched
the word-path pass. UART (8 hex digits, the older print):

```
C.1084 0FFFFFFF FFFFFFFF 0000003B 2F520004 00000039 00000002 FFFFFFE1 000C 000A
```

Mask `0FFFFFFF`, R5 `FFFFFFFF`, R9 `FFFFFFE1`, PC in the delay loop,
`wstep_run` `000A`.

The step-3 bitstream was rebuilt from this tree
(`ddr3rsc_n262144.fs`, 09:26, delay word `60000004`, setup and hold
TNS 0 on `pclk` and `cpu_clk`) and SRAM-loaded on bus 003 device 078.
The controller still forces lane 0 to step 10. After the boot line,
every UART line was:

```
CH1390 00000000F0 AAAAAAAA 000003F9 A5A5A5A5 000003EF 00000000 55555536 000D 000A
```

| | model, no plusarg | board, `wstep_run` `000A` |
| --- | --- | --- |
| PC | Blink3 loop | `0x1390` prologue hold |
| mask | `FFFFFFFFFF` | `00000000F0` |
| R5 | `00000000` in the loop | `AAAAAAAA` |
| R9 | `FFFFFFE1` | `55555536` |
| raw wstep | | `000D` |

The board at the model's passing step shows the signature the model
at `9f370e6` only emitted for both lanes at step 9. The reader never
started. No webcam. The locked rate was not changed. The Dock was put
back on `ddr3fixup_n262144.fs`. Steps 4–8 were not started.

## Reader place

The miss is which programmed step the data eye sits on, not a second
write to `wstep_run`. The controller still forces lane 0 to 10 after
read calibration and leaves lane 1 on the write-level result. On the
ALU place that force is the eye: the accepted bitstream at
`wstep_run` `000A` returns R5 `FFFFFFFF`. Write leveling there
reported raw `wstep` `000C`. On the reader place leveling reported
`000D`, one step higher, and the data eye moved the other way. Lane 0
programmed to 9 came back correct on that place, and lane 0 left at
the forced 10 aliased. Lane 1, which the RTL does not force, aliased
with it. UART does not carry `wstep1`. The sums put lane 1 in the
same beat as the forced step 10.

`+ddr3_center` is that data eye. Default 10 is the ALU place, and the
prologue, ALU, and reader images still pass there, at the same first
edges and the same period. `+ddr3_center=9` is the reader bitstream
as placed, with both lanes left at the beat step 10 names:

| | `+ddr3_center=9` | Dock, `wstep_run` `000A` |
| --- | --- | --- |
| PC | prologue hold `0x1390`/`0x1394` | `0x1390` |
| mask | `F0` | `00000000F0` |
| R5 | `AAAAAAAA` | `AAAAAAAA` |
| R9 | `55555536` | `55555536` |

`+ddr3_center=9 +ddr3_lane0=9` is the sweep: lane 0 back in the eye,
lane 1 still aliased, R5 `AAFFAAFF`, R9 `550054E1`, mask `F0`. One
step above the eye is the even-word broadcast. On the ALU place that
programmed step is 11. One step below is the odd-word overwrite. The
locked rate was not changed. The board was not loaded for this model
change.

## Programmed step for the reader place

The reader build (`DDR3_READER`) loads both lanes with absolute step
9 after read calibration. Write leveling still searches on the live
step; the force is the same point as the lane-0 force of 10, which
is `rcalib_done`. Lane 1 is left on the write-level result for the
prologue and the ALU. Those bitstreams are not rebuilt.

`+ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9` is still offset 0 inside
the stand-in: every pin on the addressed column, the same whole-beat
hit as the ALU place. N=5 first edge 32902, period 3668. N=32 first
edge 48454, period 19220. R5 `00000000`, R9 `FFFFFFE1`, mask
`FFFFFFFFFF`. The line is still `576*N+788`. That run is not a
prediction for this bitstream. The Dock section below is the
prediction that failed, and the following section is why no column
rule was substituted for it.

## Fidelity check of the step-9 bitstream (stop)

The reader netlist was rebuilt with `LANE0_STEP=9` and `LANE1_STEP=9`
(synthesis printed those parameters). Setup and hold TNS were 0 on
`pclk` and `cpu_clk`. The delay word was `60000004`. SRAM load was
bus 003 device 078. After the boot line every UART line was:

```
CH1390 0000000050 AFF0B9CF 000003F9 A5A52505 000003EF 00007F60 450FEFF1 000D 0009
```

| | `+ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9` | Dock |
| --- | --- | --- |
| PC | Blink3 loop | `0x1390` prologue hold |
| mask | `FFFFFFFFFF` | `0000000050` |
| R5 | `00000000` | `AFF0B9CF` |
| R9 | `FFFFFFE1` | `450FEFF1` |
| `wstep_run` | 9 | `0009` |
| raw wstep | | `000D` |

The force of 9 is in the bitstream: `wstep_run` is `0009`, and raw
leveling is still `000D`, the same edge the previous reader place
reported. The UART is not the pass, and it is not either miss the
stand-in already emits for this center (`AAAAAAAA` / `F0` /
`55555536` with both lanes at 10, or `AAFFAAFF` / `F0` / `550054E1`
with only lane 0 at 9). Mask bit 4 (MT[1]) and bit 6 (the alias word)
are the only prologue checks that stored zero. The sentinel beat
sampled by the CPU is `2505`, with `A5A5` in the other beat. No
plusarg in `sim/run_ddr3_standin.sh` prints R5 `AFF0B9CF` or R9
`450FEFF1`. No webcam. The locked rate was not changed. The Dock was
put back on `ddr3fixup_n262144.fs`. Steps 4–8 were not started.

## The step-9 sample is not a column eye

The stand-in was not given a new plusarg. Nothing that moves whole
columns, or that edits a beat by a bitwise mask, produces this UART
together with the two words that did match. The board was not loaded
for the check.

The last read is column `0x3F9`, the high half of the sentinel at
`0x7F0`. The CPU's beat is `2505` and the other captured beat is
`A5A5`. The last store is the high half of the sentinel difference,
`0x7F60` at column `0x3EF`. That is
`(0x2505A5A5 - 0xA5A5A5A5) >> 16`, so the word the CPU read is
`0x2505A5A5`. The low half, column `0x3F8`, came back `A5A5`. The
high half lost DQ5, DQ7 and DQ15 (`A5A5 XOR 2505 = 80A0`). DQ0, DQ2,
DQ8, DQ10 and DQ13 stayed 1. Copying either neighbouring beat cannot
do that: the other half of this word is also `A5A5`, and the next
column was never written.

Mask `0000000050` is bits 4 and 6: MT[1] at `0x14` is still `0x50`,
and the alias word at `0x114` is still `0x11111111`. MT[2], the
sentinel, and the four fold checks missed. MT[1] and the alias are
beats 2 and 3 of their groups. The broken sentinel beat is beat 1.

R5 `AFF0B9CF` is the sum of the 32 pattern words. Its low 16 bits are
`B9CF`, not `FFFF`. Beats 1 and 3 are the high halves, so a fault
that touches only those beats cannot move the low 16 bits. Beats 0
and 2 are wrong as well, and they are wrong in a way that still
returns `0x50` and `0x11111111` and still returns `A5A5` for sentinel
beat 0.

Three column rules were checked against that constraint.

Replacing any per-beat set of bits with the next column's bits leaves
the pattern sum's low 16 bits at `FFFF`. Each one-hot bit that falls
out of a low half is the same bit the paired high half drops back
in. The board's low half is `B9CF`.

A per-beat bitwise map (each output bit passed, cleared, forced, or
flipped), limited to the maps that keep the sentinel and the two
passing words, has no pair of low-half maps whose pattern sum ends in
`B9CF` and whose complement sum ends in `EFF1` at the same time.

Sliding a per-lane set of bits by one or two columns, with the
distance allowed to change per beat, gives 2304 memories that match
the sentinel and the single-word checks. None of them has both sums.
The closest hamming distance on the two sums together is 12. Sending
those bits to the other word of the BC4 group instead (`column ^ 2`),
over every pin choice that keeps the sentinel and the two passing
words and still makes MT[2] miss, was exhaustive and had no hit.

So programmed step 9 with both lanes forced is not the center, and it
is not one whole column above or below a center. The strobe is where
the DQ pins disagree with each other. One WSTEP on this place is not
one column for every pin. The earlier fit, programmed 10 on the
previous reader place as one column above an eye at 9, was the case
where the pins that failed all failed together. Forcing lane 1 to 9
moved the data pins relative to the feedback pin. Raw `wstep` is
still `000D`, so that feedback edge did not move. The data pins are
not the feedback pin.

`+ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9` remains the whole-pin hit
in `sim/run_ddr3_standin.sh`. It is the model's arithmetic when the
programmed step equals the center, which is still the right model of
the ALU place at step 10. It is not a prediction for
`LANE0_STEP=9` / `LANE1_STEP=9`. There is no plusarg for this split.
Another SRAM load of this image will not match the stand-in. A
programmed step that comes back as R5 `FFFFFFFF` is a center the
model can name. A step that comes back as `AAAAAAAA` or `55555554`
is the whole-column miss the model already has (`+ddr3_center` one
below or one above that step). A second split-pin UART will not.

## Step sweep on one place (stop)

The reader image now walks programmed steps after read calibration
and reruns the prologue from CPU reset. The controller stays up, so
the place does not move between trials. Steps 6..16, four lane-1
choices: both lanes equal, lane 1 left on its write-level result,
and lane 1 one below and one above that result. A full mask would
have parked. None did. UART on this image prints programmed lane 1
then programmed lane 0. Write leveling put lane 1 at `000A`. No
trial returned R5 `FFFFFFFF`, `AAAAAAAA`, or `55555554`.

| programmed steps | mask | R5 | R9 |
| --- | --- | --- | --- |
| both lanes `0007`..`000A` | `0000000070` | `0C0D0D9D` | `0054FFE1` |
| both lanes `000B`..`000F` | `0000000070` | `610D629D` | `AB54AAE1` |
| both lanes `0010` | `00000000F0` | `54F854F7` | `AA87AA69` |
| lane 1 `000A`, lane 0 `0006`..`0010` | `00000000F0` | `54F854F7` | `AA87AA69` |
| lane 1 `0009`, lane 0 `0006`..`000F` | `00000000F0` | `AFF7AFF7` | `2F7B2F69` |
| lane 1 `0009`, lane 0 `0010` | `0000000000` | `AFF5AFF4` | `225B2F4B` |
| lane 1 `000B`, lane 0 `0006`..`000F` | `0000000000` | `39852DF4` / `38952DF4` | `844E914B` |
| lane 1 `000B`, lane 0 `0010` | `0000000030` | `384A2DAA` | `85399236` |

Lane 0's step does not move the sum while lane 1 stays at `000A`
(lane 0 from 6 through 16) or at `0009` (lane 0 from 6 through 15).
Lane 0 at `0010` does move it when lane 1 is `0009` (`AFF5AFF4`) or
`000B` (`384A2DAA`). The Dock was put back on
`ddr3fixup_n262144.fs`. Steps 4–8 were not started.

## The sweep table is not a plusarg target

No plusarg was added. The board was not loaded for the check.

Both lanes at step 10 are two rows. Phase 0, both lanes equal, steps
7 through 10: mask `70`, R5 `0C0D0D9D`, R9 `0054FFE1`. Phase 1, lane 1
held at the write-level result `000A` and lane 0 anywhere in 6..16,
which includes lane 0 at 10: mask `F0`, R5 `54F854F7`, R9 `AA87AA69`.
Same programmed codes, two UARTs. One command-port trial has one
result for one pair of steps. The sweep leaves the controller and the
array up, so a trial that misses the columns the prologue reads keeps
the previous trial's bytes. Phase 1 prints phase 0's step-16 line for
every lane 0 code. A miss of those columns would do that. It is not
a separate measurement of lane 1 at `000A`.

`WLOADN` is held low between commands, which is the state that loads
`WSTEP`, so a trial's stores do use the step programmed for that
trial. The disagreement is the array, not a one-trial delay lag.

The bands that do change were checked on a zeroed array and with the
array kept across the sweep order. Centers 0..20, each lane its own
center, the whole-column eye and a pure shift. A per-beat column grab
of ±8. A per-pin grab of one column either way. A remix of the four
BC4 beats, including writing a beat as zero. A per-byte map whose
each bit passes, clears, forces, or flips. A permutation of the eight
bits of a byte, same permutation on both lanes. None of those produce
`0C0D0D9D` / `0054FFE1`, `610D629D` / `AB54AAE1`, `54F854F7` /
`AA87AA69`, `AFF7AFF7` / `2F7B2F69`, or `39852DF4` / `844E914B`.

Lane 1 at 9 is the band that rewrites the pattern and then sits
still across lane 0 in 6..15: R5 `AFF7AFF7`, R9 `2F7B2F69`, mask
`F0`. That pair is a real change from the previous line, and it is
still outside the models above. The low half of `AFF7AFF7` is
`FFFF` minus bits 3, 12 and 14, with no carry out of the half. A
byte map that only clears those DQ pins (`DQ3`, lane 1 `DQ4` and
`DQ6`) does make that pattern sum, and it also clears bit 4 of the
alias byte `11`, so the alias word stops reading as `11111111`.
Mask `F0` says the alias matched. Clearing those pins is not this
band.

A cold prologue is the measurement this model can be aimed at.
Reset the DDR3 controller, or clear the 8 KiB the prologue reads,
program one pair, and let that pair's `WSTEP` load before the
stores. R5 `FFFFFFFF` is a center. `AAAAAAAA` or `55555554` is the
one-column miss already in `sim/run_ddr3_standin.sh`. A line from
this sweep will not match. If a cold prologue at one pair still
prints one of these sums, that single UART is a target. The mixed
table is not.

## Cold prologue at step 10 (stop)

Both lanes were programmed to step 10 after a controller reset.
`DDR3_nRESET` falls with that reset, so this prologue did not read
the previous image's bytes. The step was loaded while the CPU was
still reset. The line repeats:

```
CH1390 00000000F0 DFAADFAA 000003F9 25A5A5A5 000003EF 00000000 20532036 000A 000A
```

R5 is `DFAADFAA`, not `FFFFFFFF`, `AAAAAAAA`, or `55555554`. Mask
`F0` is the four single-word checks. R9 is `20532036`. The CPU is in
the prologue hold. No further pair was run. No webcam. The locked
rate was not changed. The Dock was put back on
`ddr3fixup_n262144.fs`. Steps 4–8 were not started.
