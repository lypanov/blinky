# Item 48: the monorepo layout

## Why

The repo now holds more than the Oberon machine: the ESP32-C6, the M5Paper, the Pi input box, NESTang and the BBC Micro core. All of it sits in the root or in `docs/`. Every new track makes that worse, and the per-track to-do lists have nowhere to live. This item gives each track its own directory before more tracks arrive.

## What

Redo PR #7 (`cursor/monorepo-layout-1c29`) on current `main`. Do not rebase PR #7; main has moved too far. Use its layout as the plan, apply it as a script of `git mv`s plus the path fixes, and close PR #7 when this lands.

| Directory | What |
|---|---|
| `core/` | Chisel RISC5 CPU, Verilator sim, Oberon sources and the disk build |
| `nano4k/` | Tang Nano 4K: Gowin project, CST files, measurements |
| `primer20k/` | Dock: Gowin project, CST files, DDR3, measurements |
| `retro/nestang/` | NESTang submodule, Dock overlay, UART loader, stills |
| `retro/beeb/` | BBC Micro core (the `beeb-primer20k` branch already uses this path) |
| `mcu/esp32c6/` | today's `esp32c6/` |
| `mcu/m5paper/` | placeholder |
| `pi/input/` | Pi 400 input box (README already there) |
| `tools/` | build, load, measure, webcam MCP |
| `docs/` | cross-track docs only (strategy, process); no to-do files |

Mill stays at the root.

## Pull in the open track PRs

48 is also where the side-track PRs land, each in its new home, one at a time in this order. Rebase each onto the new layout, move its files, merge.

| PR | Branch | Goes to |
|---|---|---|
| #24 | `cursor/beeb-primer20k-7573` | `retro/beeb/` (needs a rebase; 9 days stale) |
| #107 | `cursor/m5paper-hello-eink` | `mcu/m5paper/` |
| #108 | `cursor/m5paper-square-swap` | `mcu/m5paper/` |
| #110 | `cursor/esp32c6-room-scan-a44f` | `mcu/esp32c6/` |
| #113 | `cursor/wifi-zigbee-coex-f6a4` | `mcu/esp32c6/` |
| #115 | `cursor/wifi-zigbee-inverse-8f20` | `mcu/esp32c6/` |
| #114 | `cursor/vindstyrka-overnight-log-71c1` | `mcu/esp32c6/` |

Not part of 48: #104 (another planning thread, becomes 49+), #105 (Nano video PLL, its owner checks it), #106 (process doc, later).

## Split the to-do lists

`docs/todo.md` and `docs/bringup-ledger.md` are replaced in 48 by short pointer files (plain Markdown, not symlinks): a few lines saying the list has moved, where to, and that nothing should be added here. There is no shared to-do file and no index of to-dos.

- The Oberon queue moves, unchanged and with its numbering, to `core/todo.md`. The bring-up ledger moves to `nano4k/bringup-ledger.md`.
- 48 creates no other to-do files. It does not gather items from the incoming PRs, branches or notes. Track to-do lists (`retro/beeb/`, `mcu/m5paper/`, `mcu/esp32c6/`, `pi/input/`) are written later by the planning thread, with the maintainer.
- `pi/input/README.md`, `retro/beeb/README.md`, `docs/pm-handoff.md` and `docs/pm-todo.md` already exist; leave their content alone.
- A root `PROJECTS.md` lists the projects: one line each with name, directory and purpose. It does not list or link to-do items.
- In the same commit, update `.cursor/skills/work-todo/SKILL.md`, `AGENTS.md`, `.cursorrules` and every link so the Oberon (Blinky) agent reads only `core/todo.md` and the ledger at its new path. After 48, the only file mentioning `docs/todo.md` or `docs/bringup-ledger.md` is the pointer file itself; check with `git grep`.

## Rules

- Moves and path fixes only. No behaviour change, no new features.
- Board docs move with their board; links in the to-do lists and write-ups are updated in the same commit.
- Scripts must not hard-code `/home/<user>/...`; use paths relative to the repo root.

## Proof

- Verilator sim passes as before.
- Nano 4K: rebuilt from `nano4k/`, SRAM load, the LED blinks at the same rate as before the move.
- Dock: rebuilt from `primer20k/`, three SRAM loads, Blink runs.
- `git log --follow` works for a moved file (spot-check one).

## Timing

Take this right after item 47 (the repo goes private at that point too), before any of the next planned items. It touches every path, so open branches will need a rebase; land or close them first where possible (the beeb branch especially).
