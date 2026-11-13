# Coordinator handoff

For a new coordinator (Claude PM thread) taking over. Read this, `PROJECTS.md`, each project's `README.md` and `todo.md`, and `docs/pm-todo.md`.

## The job

Keep every project's `todo.md` stocked (about 5+ open items), flag tracks that stall, keep project READMEs current, and run the housekeeping list in `docs/pm-todo.md`. Push the maintainer when project management falls behind.

## Rules from the maintainer

- `todo.md` items are decided (discussed with a strong model). Ideation chats (voice, Sonnet) are brainstorm only, never authoritative.
- Never invent to-do items; propose them and let the maintainer decide.
- Planning PRs are one commit, force-pushed as they change, merged at the end of the planning thread (the Cursor agent gets bogged down rebasing).
- No shared index of to-dos. `PROJECTS.md` lists projects only.
- Short, plain replies; facts with sources; subagents for wide reading.
- Bitstreams are SRAM-loaded, never flashed (except the 4K flash disk image).

## The boards

- **Tang Primer 20K Dock:** the Oberon machine (book GUI, DDR3), retro cores (BBC Micro, NESTang) one bitstream at a time, Pi 400 over USB UART.
- **Tang Nano 4K:** testing ground for Oberon work before it reaches the Dock, avoiding DDR3 trouble. Long-term: BBC B port, after soldering.

## Status (13 Nov 2026)

- Oberon queue at item 44; 48 is the monorepo layout (PR #117); another thread plans reboot-to-load/framing as 49+ (PR #104).
- Repo goes private after item 47.
