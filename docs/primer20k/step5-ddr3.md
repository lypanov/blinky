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

DDR3 programming starts from the accepted fetch backoff: lane 0
minus 1, lane 1 minus 3. The stand-in has no write-level input.
`+ddr3_pd_eye` is this place's measured plateau, not an eye. Lane 0
at 11 with lane 1 at 7, and lane 0 at 11 with lane 1 at 6, are both
the even-word alias. The flag has no offset-0 pair.

## Simulation, before the load

`sim/run_ddr3_standin.sh` builds no bitstream and loads neither FPGA.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| ddr3pd | 5 | 3668 | 38626 |
| ddr3pd | 8 | 5396 | 40354 |
| ddr3pd | 32 | 19220 | 54178 |

3668, 5396, and 19220 are `576*N+788`. The first edge is 5076 cycles
later than the stored-BL image. Those rows are the column-aligned
case, default steps 10 and 10, which is not a Dock pair. The pass
line there is PC `0x101C`, R5 `00000000`, R9 `00000008`, mask
`1fffffffffff`. The two Dock pairs print R5 `AAAAAAAA`, R9
`55555536`, mask `F0`, PC `0x1390`.

Bare `+ddr3_fetch_eye` leaves both lanes at 10. It holds at
`0x1394` with R5 `00544054`, R9 `00A9C18C`, mask `30`, and 0 edges.
That image is not loaded.

`--break-slot 32` holds at `0x1D8C` / `0x1D90` with mask
`1effffffffff`, R5 `00000000`, R9 `00000008`, and 0 edges.
`CHAIN_FIX=0` holds on the same PC with R5 `FFFFFFF4`,
R9 `00000008`, mask `ffffffffff` (the low 40 bits), and 0 edges.
Neither image is loaded. A UART mask of `FFFFFFFFFF` with `H` and
PC `1D8C` or `1D90` is one of those holds, not the blink.

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
`+ddr3_pd_eye +ddr3_lane0=11 +ddr3_lane1=6` prints this line. A
repeated `AAAAAAAA` does not name the next step. No further WSTEP
change. The constants are back at backoff 1 and 3.

The accepted fetch bitstream was loaded back. This reload's lane 0
edge is `000D`, so the steps are `0007` `000C`, and the line is the
fetch pass: delay-loop PC, mask `FFFFFFFFFF`, R5 `00000000`, R9
`FFFFFFE1`. The Dock is on that image. No webcam. Nothing was
written to flash. The Nano 4K was not loaded. Step 6 is not started.
