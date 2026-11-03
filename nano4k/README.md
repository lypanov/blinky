# Tang Nano 4K

Device: **GW1NSR-LV4CQN48PC6/I5** (`GW1NSR-4C`, QN48P). openFPGALoader board: `tangnano4k`.

SRAM only. Never `-f`.

```sh
# from repo root
tools/gowin_build.sh
tools/sram_load.sh -b tangnano4k nano4k/gowin/impl/pnr/<bitstream>.fs
```

- Gowin: [`gowin/`](gowin/) (`blinky_top.v`, IP, SDC, Tcl)
- Constraints: [`tang-nano-4k.cst`](tang-nano-4k.cst)
- CPU Verilog comes from `core/` via mill (`CPUMinimalWrapper.v`)
- Blink measurements: [`docs/blink-measure/`](docs/blink-measure/)
