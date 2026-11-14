# BBC Micro (retro)

Status: boots to the MOS banner on the Primer 20K Dock over HDMI (PR #24, not yet merged; lands in item 48). Owner of this file: the project coordinator.

## Decided

- **Runs on the Dock** for now, SRAM-loaded instead of the Oberon bitstream (one at a time).
- **Input:** keyboard bytes from the Pi 400 over the same UART link and byte protocol as Oberon (see `pi/input/README.md`).
- **Long-term goal: the BBC B on the Tang Nano 4K, whatever it takes.** Desk check (13 Nov 2026): the Dock build uses ~12.5K logic and 46/46 block RAM; the 4K has 4.6K LUT and 180 Kbit block RAM, so this is a new port (RAM/ROM in HyperRAM, extras stripped), not a rebuild. Comes after the 4K soldering, which is the final physical project.

## Known loose ends (from PR #24)

- 12 timing violations in the Dock build.
- No PS/2 keyboard tested; game discs not in the repo.
- The branch shares no history with `main`; item 48 re-applies it rather than rebasing.

## Not decided

- NES (NESTang) also runs on the Dock (on `main`). It does not fit the 4K as published either. Whether it gets a 4K port is open.
