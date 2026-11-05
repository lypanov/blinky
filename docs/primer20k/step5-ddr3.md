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

DDR3 programming is the accepted fetch image: lane 0 is its
write-level edge minus 1, lane 1 is its edge minus 3. On the fetch
build those steps were `000B` and `0007`. A new place can move the
edge. The stand-in has no write-level input and does not name the
edge of this build. The witness for this software, if the steps are
still 11 and 7, is `+ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7`.

## Simulation, before the load

`sim/run_ddr3_standin.sh` builds no bitstream and loads neither FPGA.

| image | N | cycles between edges | first edge |
|---|---:|---:|---:|
| ddr3pd | 5 | 3668 | 38626 |
| ddr3pd | 8 | 5396 | 40354 |
| ddr3pd | 32 | 19220 | 54178 |

3668, 5396, and 19220 are `576*N+788`. The first edge is 5076 cycles
later than the stored-BL image. The pass line is PC `0x101C`,
R5 `00000000`, R9 `00000008`, mask `1fffffffffff`.

Bare `+ddr3_fetch_eye` leaves both lanes at 10. It holds at
`0x1394` with R5 `00544054`, R9 `00A9C18C`, mask `30`, and 0 edges.
That image is not loaded.

`--break-slot 32` holds at `0x1D8C` / `0x1D90` with mask
`1effffffffff`, R5 `00000000`, R9 `00000008`, and 0 edges.
`CHAIN_FIX=0` holds on the same PC with R5 `FFFFFFF4`,
R9 `00000008`, mask `ffffffffff` (the low 40 bits), and 0 edges.
Neither image is loaded. A UART mask of `FFFFFFFFFF` with `H` and
PC `1D8C` or `1D90` is one of those holds, not the blink.

## What the Dock must print

One SRAM load, `openFPGALoader --busdev-num 003:078 -b tangprimer20k
-m`, no flash. The Nano 4K stays unloaded.

If this place keeps the fetch edges, the line is calibration `C`,
no hold, a delay-loop PC, UART mask `FFFFFFFFFF`, R5 `00000000`,
R9 `00000008`, lane 1 `0007`, lane 0 `000B`. Then L14 at the locked
rate above. Raw frames, not the tool's hertz headline.

If the UART is a sum the model prints for a miss at those steps, or
the steps are not `0007` `000B`, stop. Do not walk WSTEP. The
stand-in cannot name a new edge.

## Dock, one SRAM load, stopped

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
R9 `55555536`. That is the even-word alias. The witness for these
same steps is a pass (R5 `00000000`, mask `1fffffffffff`).
`+ddr3_place_fetch +ddr3_lane0=11 +ddr3_lane1=7` is a different row:
R5 `FFAAFFAA`, R9 `02540136`, mask `30`. No current plusarg prints
`AAAAAAAA` while the two lanes are 11 and 7. Stopped. No WSTEP
walk. The accepted fetch image was loaded back. The Dock is on
that SRAM image again.
