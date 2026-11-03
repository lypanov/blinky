# Tang Primer 20K Dock

Device: **GW2A-LV18PG256C8/I7** (`GW2A-18C`) on the Dock. Crystal 27 MHz on H11. openFPGALoader board: `tangprimer20k`.

SRAM only. Never `-f`.

- Board notes (pins, HDMI, BL702 UART, unverified items): [`board-notes.md`](board-notes.md)
- Wiki blinky: [`gowin/`](gowin/)
- Blink measurements (1.000 Hz then 2.003 Hz): [`blink-measure/`](blink-measure/)

```sh
tools/gowin_build_primer20k.sh
tools/sram_load.sh -b tangprimer20k primer20k/gowin/impl/pnr/primer20k_blink.fs
```

NESTang is under [`../retro/`](../retro/), not here.
