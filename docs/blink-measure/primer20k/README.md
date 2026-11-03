# Primer 20K Dock blink measurements (Bee, 3 Nov 2026)

Sipeed wiki Dock LED (`gowin/primer20k/led.v`), 27 MHz on H11, user LEDs
active-low including L14. SRAM load only: `openFPGALoader -b tangprimer20k -m`.

Webcam ROI `340,104,106,102` on `/dev/video0`. Judge frequency, not which LED.

| Build | COUNT_VALUE | Expected Hz | Measured Hz | confidence |
|---|---|---|---|---|
| [1hz/](1hz/) | 13_499_999 | 1.000 | **1.000** | 0.96 |
| [2hz/](2hz/) | 6_749_999 | 2.000 | **2.003** | 0.92 |

Measured ratio 2hz/1hz = **2.003**. Tracks the intended doubling.

Each folder has `roi.png`, `brightness.png`, and `result.json`. Clips are not committed.
