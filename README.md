# blinky

FPGA lab monorepo. **SRAM-only** bitstream load (`openFPGALoader -m`). Never `-f` / flash, even if a board already has something in flash.

Do not commit ROMs (`.nes`) or bitstreams (`.fs`).

| Directory | What |
|---|---|
| [`core/`](core/) | Chisel RISC5 CPU (**not RISC-V**) + Verilator sim + visualizer |
| [`nano4k/`](nano4k/) | Tang Nano 4K Gowin project, CST, blink measurements |
| [`primer20k/`](primer20k/) | Primer 20K Dock notes, wiki blinky, blink measurements |
| [`retro/`](retro/) | NESTang v0.4 (git submodule) + Dock CST overlay + UART loader + HDMI stills |
| [`pi/`](pi/) | Raspberry Pi notes (placeholder) |
| [`mcu/`](mcu/) | MCU notes (placeholder) |
| [`tools/`](tools/) | Build / SRAM-load / blink-measure scripts, [webcam MCP](tools/webcam-mcp/) |

**Licences.** Mixed tree. NESTang (`retro/nestang`) is GPL (fpganes / Strigeus lineage); `hdmi2` inside it is MIT (Sameer Puri). Do not mix NESTang HDL with the Chisel CPU in one bitstream. v0.4 has no LICENSE file in-tree; treat it as GPL as documented upstream.

Clone with the submodule:

```sh
git clone --recurse-submodules git@github.com:lypanov/blinky.git
# or after a plain clone:
git submodule update --init --recursive
```

## SRAM load

`-b` is required (two boards). Always `-m`. Never `-f`.

```sh
tools/sram_load.sh -b tangnano4k nano4k/gowin/impl/pnr/<bitstream>.fs
tools/sram_load.sh -b tangprimer20k primer20k/gowin/impl/pnr/primer20k_blink.fs
```

## core — RISC5 CPU

Chisel 6.6 / Mill 0.12.5. ISA: [`core/docs/risc_5_arch.txt`](core/docs/risc_5_arch.txt). Memory map: [`core/docs/memory_map.txt`](core/docs/memory_map.txt).

Hardware image: `core/tests/Blink2hw.Mod` (`maxIterations := 262144`, 2x delay word `0x60000004`). Simulation: `core/tests/Blink2test.Mod` (`maxIterations := 5`). LED MMIO snoops stores to `0x10` or `0x50`.

Mill is invoked from the **repo root**. Oberon `.code` files live under `core/tests/`; set `CHISEL_CPU_PROJECT_ROOT` to `core/` (the scripts do this).

```sh
# from the repo root
tools/run_verilator_sim.sh
# equivalent:
make -C core/sim sim
```

| artifact | path |
|---|---|
| FST waveform (GTKWave) | `core/sim/out/blink2.fst` |
| LED edge log | `core/sim/out/led_toggles.csv` |
| timing-diagram PNG | `core/sim/out/led_waveform.png` |
| cycle trace | `core/sim/out/blink2_trace.json` |

```sh
gtkwave -S core/sim/gtkwave_led.tcl core/sim/out/blink2.fst core/sim/gtkwave_led.gtkw
```

FPGA bitstream for the Nano 4K:

```sh
tools/gowin_build.sh
tools/sram_load.sh -b tangnano4k nano4k/gowin/impl/pnr/<bitstream>.fs
```

Visualizer:

```sh
tools/run_visualizer.sh
# then open http://127.0.0.1:8765/
```

CPU tests: `mill chisel-blinky.test` from the repo root, or `tools/run_cpu_with_trace.sh`.

## nano4k

Tang Nano 4K (`GW1NSR-4C`). Gowin sources in [`nano4k/gowin/`](nano4k/gowin/), constraints [`nano4k/tang-nano-4k.cst`](nano4k/tang-nano-4k.cst). Past blink measurements: [`nano4k/docs/blink-measure/`](nano4k/docs/blink-measure/).

## primer20k

Tang Primer 20K Dock. Pins and SRAM rule: [`primer20k/board-notes.md`](primer20k/board-notes.md). Wiki blinky: [`primer20k/gowin/`](primer20k/gowin/). Measurements (1.000 Hz then 2.003 Hz): [`primer20k/blink-measure/`](primer20k/blink-measure/).

```sh
tools/gowin_build_primer20k.sh
tools/sram_load.sh -b tangprimer20k primer20k/gowin/impl/pnr/primer20k_blink.fs
```

## retro — NESTang

All NESTang work lives here, not under `primer20k/`. Submodule [`retro/nestang`](https://github.com/nand2mario/nestang) pinned at tag **v0.4** (last release with Primer 20K). Dock CST overlay, UART loader, HDMI stills: [`retro/nestang.md`](retro/nestang.md).

Free ROMs only. UART loader, not FPGA flash and not SD.

## tools

- `tools/gowin_build.sh` — Nano 4K Chisel + Gowin
- `tools/gowin_build_primer20k.sh` — Primer wiki blinky
- `tools/sram_load.sh` — SRAM only; requires `-b`
- `tools/measure_blink.sh` — LED Hz from `/dev/video0`
- [`tools/webcam-mcp/`](tools/webcam-mcp/) — streamable HTTP MCP on **127.0.0.1:8766** (`capture_still`, `list_cameras`, `capture_burst`)
