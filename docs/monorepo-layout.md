# Item 48: the monorepo layout

## Why

Main today is one project in the root. Its code (`src/`, `sim/`, `gowin/`, `tests/`, `oberon/`) and its two pin files (`tang-nano-4k*.cst`) sit in the root, and 134 files sit in `docs/`. The side tracks (ESP32-C6, M5Paper, Pi input box, BBC Micro core) are mostly still open pull requests, so main has almost nothing of them yet: `esp32c6/docs/netatmo-setup.md`, and the NESTang notes in `docs/primer20k/` plus `tools/nestang_uart_load.py`. If those PRs land into the root, every track makes the mess worse. This item gives each track its own directory first. Item 49 (DDR3 training that survives a rebuild, write-up `docs/ddr3-training.md`) edits files under the new `primer20k/` path, so 48 must land before 49 starts.

## What

Redo PR #7 (`cursor/monorepo-layout-1c29`) on current `main`. Do not rebase PR #7; main has moved too far. Use its layout as the plan, apply it as `git mv` plus path fixes, and close PR #7 (and the earlier planning PR #117) when this lands.

| Directory | What |
|---|---|
| `core/` | Chisel RISC5 CPU, Verilator sim (a Verilog simulator), Oberon sources and tests, Verilog both boards share, the Oberon queue's write-ups |
| `nano4k/` | Tang Nano 4K: Gowin project, pin files, notes, measurements |
| `primer20k/` | Dock: Gowin project, pin files, DDR3, notes, measurements |
| `retro/nestang/` | NESTang notes and stills, UART loader. NESTang itself is cloned at build time; main has no submodule and no overlay |
| `retro/beeb/` | BBC Micro core; arrives with PR #24, nothing on main yet |
| `mcu/esp32c6/`, `mcu/m5paper/` | today's `esp32c6/`; M5Paper arrives with PRs #107 and #108 |
| `pi/input/` | Pi 400 input box; arrives with PR #118 (see below) |
| `tools/` | build, load, measure, webcam MCP (stays where it is) |
| `docs/` | cross-track docs only (strategy, load-boards, pointer files) |

Mill (the build tool; `build.mill`, module `chisel-blinky`) stays at the root. Only its source path changes: the module root becomes `core/`.

## What moves where

Every top-level entry of today's tree. Entries that stay still get path edits.

| Today | Goes to | Note |
|---|---|---|
| `src/` | `core/src/` | 9 path strings in 3 Scala files (`sim/visualizer/imem/...`); `build.mill` source path |
| `sim/` | `core/sim/` | whole tree, including the DDR3 and HyperRAM benches |
| `oberon/`, `tests/`, `blink-01.Mod` | `core/oberon/`, `core/tests/` | `tests/fixtures/` goes along; `blink-01.Mod` is unreferenced, goes with the tests |
| `gowin/`: `button_gate.v`, `uart_word_rx.v`, `video.v`, `FpSnap.v`, `KeepBit.v`, `ip/gowin_sp.*` | `core/rtl/` | used by both boards' Tcl and by the sim scripts |
| `gowin/`: `blinky_top*.v`, `blinky.sdc`, `gowin_build*.tcl`, `spi_*`, `ip/` rest | `nano4k/` | Nano 4K only (HyperRAM, SPI flash) |
| `tang-nano-4k.cst`, `tang-nano-4k-hdmi.cst` | `nano4k/` | named in 2 Tcl files and `build.sh` |
| `gowin/primer20k/` | `primer20k/` | its Tcl finds the root as `../..`; becomes `..` |
| `esp32c6/` | `mcu/esp32c6/` | |
| `tools/` | stays | only `nestang_uart_load.py` goes, to `retro/nestang/` |
| `.github/`, `.cursor/`, `.cursorrules`, `.vscode/`, `.gitignore`, `AGENTS.md`, `README.md`, `build.sh`, `.mill-*`, `project/` | stay | text edits. CI runs `sim/run_frame_check.sh`; `.gitignore` has about 20 `gowin/` and `sim/` entries; `README.md` names `modules_n65536.fs` but the script writes `modules_n1000.fs` |
| `docs/`: `strategy.md`, `load-boards.md` | stay | |
| `docs/`: `todo.md`, `bringup-ledger.md` | pointer files stay | content goes to `core/todo.md`, `nano4k/bringup-ledger.md` |
| `docs/`: `next-steps`, `screen-and-boot`, `modules-mod-plan`, `hdmi`, `led-ladder`, `main-forward-plan`, `handover.mainloop`, `monorepo-layout` (this file), ISA, memory map, RSC and linker texts, `OberonSources/` | `core/docs/` | the Oberon queue's write-ups, with the queue |
| `docs/hyperram/`, `docs/blink-measure/{blink3,main-forward}` and loose images | `nano4k/docs/`, `nano4k/measurements/` | |
| `docs/primer20k/` notes and steps, `docs/ddr3-training.md`, `docs/blink-measure/{blink3-primer20k,primer20k}` | `primer20k/docs/`, `primer20k/measurements/` | `ddr3-training.md` goes with the Dock, from whichever branch carries it |
| `docs/primer20k/nestang.md` and the 3 `hdmi-monitor-*.jpg` | `retro/nestang/` | |

Recorded results (`*.json`, and the pasted paths in measurement notes) are history. They are not rewritten.

## Pull in the open track PRs

48 is also where the side-track PRs land, each in its new home, one at a time in this order. Rebase each onto the new layout, move its files, merge. Each lands only after its parent in the list.

| PR | Branch | Goes to |
|---|---|---|
| #24 | `cursor/beeb-primer20k-7573` | `retro/beeb/` (needs a rebase; 9 days stale) |
| #107, then #108 | `cursor/m5paper-hello-eink`, `cursor/m5paper-square-swap` (#108 is stacked on #107) | `mcu/m5paper/` |
| #110 | `cursor/esp32c6-room-scan-a44f` | `mcu/esp32c6/` |
| #113, then #115 | `cursor/wifi-zigbee-coex-f6a4`, `cursor/wifi-zigbee-inverse-8f20` (#115 is stacked on #113) | `mcu/esp32c6/` |
| #114 | `cursor/vindstyrka-overnight-log-71c1` (base is `cursor/blink3-nano4k-ddbe`, not main) | `mcu/esp32c6/`, only after its base is on main |
| #118 | `cursor/space-led-faf1` | inside 48, `pi/input/`: a key listener for the Pi's PWR LED is Pi input-box work |

Before 48 (so 48 starts from a quiet main): #125 (records item 46 in the Oberon queue docs that 48 renames; land it, or close it) and #105 (Nano video PLL, touches `gowin/`; its owner decides). Not part of 48: #119 (a DS18B20 sketch for the TTGO T8, a different board from the C6; it needs its own `mcu/` directory, the maintainer's choice, after 48), #122 (stacked on `cursor/main-32kb-reserve-787f`, and main already has `tools/load_nano.py`; the owner checks if it is still needed), #104 (planning, renumbered to 50 or later), #106 (process doc, after 48), and the old #20, #21, #39, #40, #46, #47.

## Split the to-do lists

`docs/todo.md` and `docs/bringup-ledger.md` are replaced in 48 by short pointer files (plain Markdown, not symlinks): a few lines saying the list has moved, where to, and that nothing should be added here. There is no shared to-do file and no index of to-dos.

- The Oberon queue moves, unchanged and with its numbering, to `core/todo.md`. The bring-up ledger moves to `nano4k/bringup-ledger.md`. Links to write-ups are fixed to the new paths; item 49's link goes to `primer20k/docs/ddr3-training.md`.
- 48 creates no other to-do files. It does not gather items from the incoming PRs, branches or notes. Track to-do lists (`retro/beeb/`, `mcu/m5paper/`, `mcu/esp32c6/`, `pi/input/`) are written later by the planning thread, with the maintainer.
- A root `PROJECTS.md` lists the projects: one line each with name, directory and purpose. It does not list or link to-do items.
- In the same commit, update `.cursor/skills/work-todo/SKILL.md`, `AGENTS.md`, `.cursorrules`, `docs/strategy.md` ("Where things are") and every link so the Oberon (Blinky) agent reads only `core/todo.md` and the ledger at its new path. After 48, the only files mentioning `docs/todo.md` or `docs/bringup-ledger.md` are the two pointer files.

## Rules

- Moves and path fixes only. No behaviour change, no new features. Gowin Tcl lists its files in a fixed order; keep the order.
- Board docs move with their board; links in the to-do lists and write-ups are updated in the same commit as the move.
- Scripts must not hard-code `/home/<user>/...`; use paths relative to the repo root. Today one script does: `tools/test_led_detect.py` (2 clip paths).

## Stages

Each stage is one PR, with its own proof from "Proof" below. Do not start the next stage before the proof of the one before passes. Take stage 0 right after item 47 (the repo goes private then too). Every stage touches paths, so open branches need a rebase after each one.

0. Baseline. With #125 landed, on unmoved main, run the Proof commands once and save the output in the PR text.
1. `core/`: `src/`, `sim/`, `oberon/`, `tests/`, `core/rtl/`, the Mill path, Scala strings, CI, `.gitignore`, `tools/` and Tcl paths to the moved files. Full proof.
2. `nano4k/`, `primer20k/`, `retro/nestang/`, `mcu/esp32c6/`: the Gowin trees, pin files, board docs, measurements, Tcl `ROOT` lines, generated `src/` and `impl/` folders in `.gitignore`. Full proof.
3. The to-do split: `core/todo.md`, `nano4k/bringup-ledger.md`, `core/docs/`, the pointer files, `PROJECTS.md`, skill, `AGENTS.md`, `.cursorrules`, `strategy.md`. Proof: `core/todo.md` equals the old `docs/todo.md` apart from link lines, with the same `Next:` line and the same count of numbered items; the stale-path `git grep`.
4. The track PRs in the table, one at a time. Proof for each: CI is green and the stale-path `git grep` is empty.
5. Close #7 and #117. Item 49 may start.

## Proof

All of it runs as commands; nothing is checked by eye. "Same as baseline" means the stage 0 output.

- Sim: `tools/run_verilator_sim.sh` and `sim/run_frame_check.sh` exit 0 (from `core/sim/` after stage 1), the printed edge cycles and PCs equal the baseline, and `mill chisel-blinky.test` passes. The CI job `ci` is green.
- Builds: `tools/gowin_build.sh` produces `nano4k/impl/pnr/modules_n1000.fs`, and `FPGA_IMAGE=ddr3modules BOARD=primer20k tools/gowin_build.sh` produces `primer20k/impl/pnr/ddr3modules_n1000.fs`.
- No behaviour change: `sha256sum` of `generated/CPUMinimalWrapper.v` (per board), `sim/out/disk.bin` and `sim/visualizer/imem/*.words` equal the baseline.
- 4K utilisation: logic, CLS, BSRAM and `cpu_clk` Fmax in the place report equal the baseline, which should equal the last recorded place (`screen-and-boot.md`, item 46: logic 4545/4608, CLS 2301/2304, Fmax 13.675 MHz against 13.500). The 4K has 3 CLS free, so any change is a failure.
- Nano: `tools/load_nano.py --sram-only <fs>`, then `tools/measure_blink.sh --device /dev/video2 --roi nano4k`: rise-to-rise gaps about 2 s, then 1 s, as `docs/load-boards.md` publishes for the 1000 ms disk.
- Dock: `tools/load_dock.py <fs> sim/out/disk.bin` exits 0 on three SRAM loads in a row (trained, took the disk, mask `FFFFFFFFFF`), and `tools/measure_blink.sh --device /dev/video2 --roi primer20k` shows the same gaps on each.
- No stale path: `git grep -n -E '(^|[^a-z0-9_/.-])(gowin|sim|oberon|tests|esp32c6|src/(main|test))/|docs/(todo|bringup-ledger)\.md|(^|[ /])tang-nano-4k.*\.cst' -- . ':!*.json' ':!core/docs/monorepo-layout.md'` prints only the two pointer files; and `git grep -l '/home/' -- '*.sh' '*.py' '*.tcl' '*.v' '*.scala' '*.yml'` prints nothing.
- History: `git log --follow --oneline core/sim/link_inner.py` shows more than one commit.

## To check before starting

- Files of #118 and #125, and what `cursor/blink3-nano4k-ddbe` is; titles only were available here.
- Whether the draft's `pi/input/` and `retro/beeb/` READMEs, `docs/pm-handoff.md` and `docs/pm-todo.md` come from PRs #24 and #106; none is on main. #106's `pm-todo.md` would be a to-do file outside the rule above.
- Whether Mill accepts the module root at `core/` with `-Dchisel.project.root=${PWD}` unchanged, and where `generated/` and `gowin/src/` should be written once `gowin/` is gone.
- Whether the Dock trains on a rebuild at all: item 49 exists because it does not always. If the stage 0 Dock loads fail, the Dock proof falls back to the identical hashes, and that is stated in the PR.
