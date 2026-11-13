# Project coordinator's list

Not an agent queue. Housekeeping the coordinator (Claude PM thread) tracks and raises with the maintainer.

1. Make the repo private on GitHub once item 47 is done (Settings → Danger Zone). Maintainer, by hand.
2. Close PR #7 once item 48 lands.
3. PR #105 (Nano video PLL): its owner checks whether it already landed or needs re-merging.
4. PR #106 (project process doc): merge later, after the repo is private. Not part of 48.
5. PR #20 (dual sim Bee, Verilator Blink3 + NESTang Alter Ego): find out what it is and whether it's still needed.
6. PR #21 (Modules plan): check it is superseded by `docs/modules-mod-plan.md`, then close.
7. PRs #39, #40, #46, #47 (old DDR3 step stack): check they're superseded, then close together.
8. Delete stale branches (blink-meter, blink2-4x, blink3-*, fix-bl-*, webcam-*, etc.), only at a standstill when no agent is working.
9. Pi input controller notes: move them from Grokbot into `pi/input/` so every thread can see them.
10. Each track keeps at least ~5 open to-do items; flag tracks that run low (Oberon, retro, input, ESP/M5Paper).
11. Keep project READMEs (`pi/input/`, `retro/beeb/`, others) and `docs/pm-handoff.md` current whenever a track's to-dos change.
12. Confirm the Pi 400 powers the Dock via the hub, once the hub is free.
13. Ask the maintainer: which NES was "verified on the 4K" in old notes? Nothing in the repo backs it.
