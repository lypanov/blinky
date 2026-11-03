# core — RISC5 CPU

Chisel 6.6 / Mill 0.12.5. **Not RISC-V.** ISA: [`docs/risc_5_arch.txt`](docs/risc_5_arch.txt). Memory map: [`docs/memory_map.txt`](docs/memory_map.txt).

Mill is invoked from the **repo root** (`build.mill` there points `millSourcePath` at this directory). Oberon images are under [`tests/`](tests/). Set `CHISEL_CPU_PROJECT_ROOT` to this directory (the repo scripts do).

```sh
# from repo root
mill chisel-blinky.test
tools/run_verilator_sim.sh
tools/run_visualizer.sh
tools/gowin_build.sh          # Nano 4K bitstream; SRAM-load separately
```
