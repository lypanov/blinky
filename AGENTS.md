# Agent notes

## Subagents

Always use non-fast for subagents. Do not pass a model slug that ends in `-fast`.

## Loading boards

Dock SRAM load and UART disk: `docs/load-boards.md`. Run `tools/load_dock.py`.
Never flash. Never program the Nano while loading the Dock. The Nano 4K path
is not in the script yet.

## Merging

Rebase. That is the maintainer's preference for landing pull requests. `main` stays a straight line: each branch commit is replayed, the patch stays the same, the SHA changes. PRs #41–#43 landed this way.

### A stack

Rebase-merge one branch at a time, from the bottom. After a parent is on `main`, rebase the next branch onto that `main` and force-push it with `--force-with-lease` before rebase-merging. `git rebase origin/main` skips commits whose patches are already on `main`.

Set a child PR's base to `main` only after that rebase. Rebase-merging a child that still carries the parent's old SHAs replays the parent commit. That replay conflicts once a later commit has edited the same lines. A merge commit of the same pair conflicts too. Merging a child into its parent branch leaves `main` unchanged.

When a later PR already contains an earlier PR's commit, rebase-merge the earlier PR first. Rebase the later branch afterwards so the shared commit drops. Merging the later PR first makes the earlier commit conflict on replay.

The open DDR3 stack is that shape. #44 (`47d9f07` on `cursor/ddr3-step5-stock-080c`) and #45 (`cursor/ddr3-step6-moddesc-1318`) both target `main`, and #45's first commit is #44's head. #46 (`cursor/ddr3-step7-files-572c`) targets #45's branch. #47 (`cursor/ddr3-step8-modules-d4d7`) targets #46's branch.

1. Rebase-merge #44. It is already based on `0fa8e8a`.
2. Rebase #45 onto the new `main`, force-push it, rebase-merge #45. Leave `cursor/ddr3-step6-moddesc-1318` in place until #46 is rewritten. Deleting it makes GitHub retarget #46 onto `main` while #46 still has the old SHAs.
3. Rebase #46 onto the new `main`, force-push it, set its base to `main`, rebase-merge #46. Leave `cursor/ddr3-step7-files-572c` until #47 is rewritten.
4. Rebase #47 onto the new `main`, force-push it, set its base to `main`, rebase-merge #47.

That sequence keeps today's #47 tree (`533d878`, `3e3f4320`). `main` gains five commits: #44's one, #45's two step-6 commits, then #46, then #47.
