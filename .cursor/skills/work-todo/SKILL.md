---
name: work-todo
description: >-
  Take one Blinky to-do from docs/todo.md. Read the prove-ladder skill, then
  the to-do, then the bring-up ledger and the modules plan as that item
  requires. Use when starting an agent on the current bring-up, taking the
  next to-do, or when the Nano 4K runs out of space.
---

Norebo is `/home/lypanov/fpga/norebo-compiled`. A worktree has no `tools/project-norebo`. Before the first compile or `tools/run_verilator_sim.sh`, `tools/setup_norebo.sh` is a no-op when that tree matches `tools/norebo.pin`. Do not clone into the worktree. Do not `rm -rf` the machine tree.

Read these, in this order:

1. `.cursor/skills/prove-ladder/SKILL.md`. Follow it for every proof. If the user says **HDMI is plugged into 4K** or **HDMI is plugged into 20K**, that skill says which board to prove now, and when to ask for a cable switch.
2. `docs/todo.md`. Take the item named on the `Next:` line. One item. Do not start the next.
3. The documents that item names. Read those sections when the item needs them. `docs/bringup-ledger.md` is the Nano 4K space list. `docs/modules-mod-plan.md` is the modules plan.

A space problem that can be fixed without changing the architecture stays inside the item. If the Nano 4K still does not fit, stop. Name the bring-up ledger item you would take next. The open ledger items, lowest number first, are that list. They are not the to-do unless `docs/todo.md` says so.
