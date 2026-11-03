# Nano 4K blink after the monorepo layout move (PR #7)

Gowin from `nano4k/` (`tools/gowin_build.sh`), SRAM load only:

```sh
tools/sram_load.sh -b tangnano4k nano4k/gowin/impl/pnr/blink2hw_4x.fs
```

Webcam `/dev/video0`, ROI `550,280,68,97` (user LED on the right of the board).

| | |
|---|---|
| Measured | **3.437 Hz** (FFT 3.444 Hz) |
| Confidence | 0.96 |
| Edges | 185 in 27 s |
| Period | 0.291 s (median 0.300 s) |

Matches the earlier 4x SRAM run (~3.42 Hz) on this same Blink2hw image (`0x60000004`). Clip not committed.
