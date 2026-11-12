# The process

How Blinky is advanced by a Cursor Project coordinator and the agents it starts. This is the normal loop the maintainer means by "the process". It is not a history of incidents. One-off exceptions (a cable that could not move overnight, a GitHub runner that stalled, a Dock that needed a person at the hub) are named only where they produced a standing rule.

The Project's job is to take items from `docs/todo.md`, one at a time, prove each item, land it on `main`, and start the next. The coordinator does not implement the FPGA work itself. It starts a fresh agent for each item, watches the proof, and keeps the queue moving without waiting for a person unless the proof actually needs hands at the desk.

The project's goal, the two boards, and how plans are written are in `docs/strategy.md`. Read that first. This file is only the operating loop around that goal.

## One item, one agent, one proof

Work comes from `docs/todo.md`. The `Next:` line is the queue. That file is an index; the write-up lives in the document the item names.

Each item is one small step: one capability, the blink kept, a published rate, a measured result. The coordinator starts **a new agent for every item**. That is why this is a Project. Reusing the same agent across items is the failure mode the maintainer asked for a Project to prevent.

The agent reads, in this order:

1. `docs/strategy.md` (via `AGENTS.md`)
2. `.cursor/skills/prove-ladder/SKILL.md`
3. `.cursor/skills/work-todo/SKILL.md`
4. `docs/todo.md`, and only the item on `Next:`
5. The write-up that item names

It does not start the next item. If two items were stuffed into one prompt, the agent still stops after the first, reports, and waits. Combining HDMI items 14 and 15 in one session was the example that made that rule explicit.

A space problem that can be fixed without changing the architecture stays inside the item. If the Nano 4K still does not fit, the agent stops and names the next open bring-up ledger item. It does not take that cut in the same task. The coordinator then starts a **new** agent for the ledger cut, and a **new** agent to retry the original item.

## How a step is proved

Prove every ladder step in this order. Do not skip a stage. A step is done only when simulation, the Tang Nano 4K, and the Primer 20K / Dock all agree.

The skill is `.cursor/skills/prove-ladder/SKILL.md`.

### 1. Simulation first

Verilator (`tools/run_verilator_sim.sh`) proves the CPU image that the Nano 4K runs. That is the default sim. It is where a 4K miss returns.

A full Icarus plus Micron `ddr3.v` run through `Modules.Init` to two LED edges (`IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh`) is **only** for a real DDR3 failure: calibration, the write eye, the controller, or the Micron protocol. If the Nano 4K and the Primer 20K already blink on this tip and there is no such failure, the Dock stage is closed. N=5 does not skip the boot: that image still runs `Modules.Init` before the delay loop, so the ladder must not demand the long PHY run just to print a blink score.

A failed 4K stage returns to Verilator. A Dock failure in calibration, the write eye, the controller, or the Micron protocol returns to the full Icarus plus Micron run. Any other Dock failure returns to Verilator. Fix the cause, then run the ladder again from sim. Do not reload hardware until that sim passes. Loop until sim, 4K, and 20K agree. Stop the loop when the Nano 4K does not fit, and report that stage.

### 2. Tang Nano 4K (HyperRAM)

Load the same tip with `openFPGALoader ... -m` (SRAM only). On the Omarchy desk the Nano has been bus `003:081`, idcode `0x100981b`, GW1NSR-4C. USB addresses move after a replug: detect, do not hard-code. Never write a bitstream to flash, internal or external.

The one flash exception is a **data file** built by the disk image builder, onto the Nano's external SPI NOR (Puya P25Q32, 4 MiB), and only inside `0x200000`–`0x3FFFFF`. Never below `0x200000`, never a `.fs` or other bitstream, never the internal flash. Verify the write by reading it back.

The Nano has no working UART and no usable JTAG data path. Its proof is the LED. A dark LED is a fail. The LED (and the square or bitmap on the screen) only come on after Blink stores the arm word computed from its self-checks, so a skipped check cannot look like a pass. Status blocks on screen may show before the arm word; they report how far the boot got, and they are never a pass.

Every step publishes its blink rate from a formula before the board is trusted. The webcam measures that rate.

Button tests need a person. They never gate overnight work. The Nano S1 pause is the maintainer's, by hand, when they are there.

### 3. Primer 20K / Dock (DDR3)

Only after the 4K stage. Same tip, SRAM load only. No flash writes of any kind. On the Omarchy desk the Dock has been bus `003:078`, idcode `0x81b`, GW2A-18. Detect each time.

The Dock has a UART, so it can be tested with nobody there. A Primer 20K load counts only when the UART shows the boot succeeded. Programming SRAM three times is not that check. From item 29 onward, a Dock result counts only after **three** SRAM loads that agree. One load is not enough to call it good or bad.

When the HDMI capture card is on the other board, the Dock is still programmed. Its proof in that case is the LED and the UART, not the capture card.

### Where the measurements are taken

Both boards sit on the self-hosted machine **omarchy-blinky** (same physical box as the `~/jjrss @ omarchy` worker, different Cursor worker). That is the FPGA desk. Hardware agents run there so they can talk to the FTDI cables, Gowin place-and-route, the webcam, and the capture card.

The webcam MCP is a streamable-HTTP server on that machine, `http://127.0.0.1:8766/mcp`, code in `tools/webcam-mcp/`. It does not touch the FPGA, serial ports, or `openFPGALoader`. The camera is a Logitech QuickCam Pro (`046d:0991`). `device=auto` follows that camera by USB id. After the HDMI stick is plugged in, the webcam is `/dev/video2`; `/dev/video0` is the UGREEN capture card (`15389`) and must not be assumed.

Usual tools:

- `measure_blink` — named board (`roi=nano4k` or `roi=primer20k`); headline Hz is that board's classified blinking LED
- `check_all` — one clip, both boards
- `detect_leds` — colour, blinking vs steady, board assignment (20K = three LEDs, 4K = two)
- `capture_still` / `capture_video` — stills and clips under `~/fpga/captures/` and `~/fpga/blink-measure/`

Clips are the proof artifact. A board result names the edge rate, the published formula, confidence, and the clip path.

HDMI is a second witness next to the LED. There is one capture card. The maintainer moves the cable. The screen rate has to match the formula and the webcam LED rate in the same run. Grab a frame and confirm there is a locked picture before measuring; green snow is not a measurement. Overnight, with nobody to move the cable, HDMI stays on the Dock; the 4K is proved by Verilator and the LED, and a 4K picture check waits until morning. A working LED is enough to keep going. When the maintainer is at the machine, ask for a 4K picture catch-up without stopping the agent that still needs the Dock capture.

**pi400** is a connected self-hosted worker with this repo, on a Raspberry Pi 400. It was listed beside omarchy-blinky for the whole Project. It was not the machine for this FPGA ladder. It is the machine for later device work (see "What is generic" below).

## How the coordinator starts agents

The coordinator is the Cursor Project (the long-running cloud conversation). It does not share a worktree with the hardware agents.

### Placement

| Kind of work | Where it runs | Why |
|---|---|---|
| A to-do or ledger item that loads a board, measures an LED, or runs Gowin | Self-hosted worker **omarchy-blinky** (`40d06603-5ab1-4ffe-bac1-718ab77971f9`) | The boards, webcam, and capture card are there |
| A docs-only or skill change that must not collide with a hardware worktree | Cursor's default **cloud** environment | Own checkout; no USB; no Gowin |
| A research pass over other cloud transcripts | Cloud | The Omarchy worker cannot see every cloud environment |
| Work for a different device on the Pi 400 | Self-hosted worker **pi400** | Not used for this ladder |

The Project's Run-on grant for Blinky hardware is omarchy-blinky. List workers before placing. Do not place on a machine that is not approved. Do not place FPGA loads on pi400.

The process does not pin a model slug. `AGENTS.md` does pin one constraint: subagents are non-fast (do not pass a model whose slug ends in `-fast`). Hardware agents are Cursor cloud agents **placed** on the self-hosted worker, not local chat threads and not GitHub Actions runners.

### Startup sequence

1. Create a tracked task for the item (one leaf per item).
2. Confirm omarchy-blinky is connected, idle, and approved.
3. Start a **new** agent on that worker, linked to the task. Give it its own git worktree under `/home/lypanov/fpga/`, branched from current `origin/main`. Do not reuse another agent's checkout on this shared machine.
4. Send the worker link in chat **after** the create returns, not in the same tool batch.
5. Subscribe to the pull request and to CI on its branch once a PR exists. Subscribe a timer for progress notes (half an hour while the maintainer is around, hourly overnight).
6. When the item is proved and on `main`, remove the worker from the finished task and start a **new** agent for the next `Next:` line.

Do not resume a spent agent onto the next item. If an agent is confused or has been on the same item too long, start a new agent on the **same** worktree with a short handoff of where it stuck, and do not resume the old one. One leaf task has one worker.

Cloud vs Omarchy is a placement choice, not a personality choice. The evening picture and the prove-ladder skill rewrite ran in the cloud so they would not touch the hardware worktree. The uptime check, every ladder item, and every board load ran on omarchy-blinky.

## What those agents are prompted with

The quotes below are trimmed kickoff text from the Blinky Project: one prompt the maintainer wrote, and the coordinator's launch notes from the turns that started those workers. They are not rewritten.

### 1. Name the next item (read-only, Omarchy)

Used once at the start of the night, before the maintainer said go. No edits, no sim, no board.

> Follow the user prompt exactly without editing, building, simulating, or loading a board. Use the existing blinky checkout, pull the latest merge, and read `docs/todo.md`. Name only the next item, then stop. Also return every remaining indexed item after it, quoted from `docs/todo.md`, and name the source file and section for the earlier list.

### 2. First ladder item (`DIV`, `H`, `SYSTEM.BIT`)

The pattern for a normal to-do. One item, own worktree, skills, prove, PR.

> Take one item, following the prove ladder, and not skipping stages or starting the next item. Branch from `origin/main`. Read the prove-ladder and work-todo skills. Follow `docs/todo.md` item 3. Do not redo the logger or the 32 KB reserve. Create a new git worktree so this shared self-hosted machine is not fighting the previous checkout. Open a PR when finished. The prove ladder includes sim and boards on Omarchy.

### 3. Maintainer-written HDMI prompt (items 14–15)

Sent as "here is the prompt". The coordinator was told not to follow the "one branch, two items" part as-is; after this run, Primer 20K HDMI steps each get their own agent.

> Pull main. Work through `docs/todo.md` items 14 and 15, in order, using the work-todo skill (which has you follow prove-ladder). Read `docs/hdmi.md` first. The capture card is on the Nano 4K. When an item is done, record the result where it says, mark it done, set `Next:`, commit, and go on to the next. If the 4K doesn't fit, follow "When the 4K does not fit" in `docs/hdmi.md`: shrink first, then stop and report the sizes with video off, at the first attempt and at the smallest attempt, what each shrink saved, how many CLS are still missing, and which bring-up ledger item (3, 4 or 5) would cover it. Don't take a ledger cut yourself. Use one branch, one commit per item, and open one PR at the end.

### 4. One Dock HDMI item (the corrected form)

Item 17, after the "do not combine them" correction. This is the normal hardware prompt.

> New worktree under `/home/lypanov/fpga/` from current `origin/main`. Cover only item 17. Follow `AGENTS.md`, work-todo, and prove-ladder. Read `docs/todo.md` and `docs/hdmi.md` first. The capture card is on the Dock. SRAM loads only; no bitstream flashing. Item 18 and ledger cuts are forbidden. The full DDR3 blink simulation waits until a real Dock DDR3 failure. If 4K video does not fit, shrink it and stop to report. One branch, one commit, one pull request. Fast-forward `origin/main` after green CI. Report board results and failed checks. Own the git worktree and do not reset other agents' checkouts.

### 5. Takeover on the same worktree

When the current agent is stuck, not when starting a new item.

> Start a new agent on the same worktree. A few sentences of where we got stuck and what the latest issue was. There were issues reproducing the previous Dock step reliably, so a Dock result counts only after three runs.

### Reusable template

Hardware item on the machine that holds the device:

```
Pull origin/main. Make a new worktree and a new branch. Do not reuse
another agent's checkout.

Read AGENTS.md, then .cursor/skills/prove-ladder/SKILL.md, then
.cursor/skills/work-todo/SKILL.md, then docs/todo.md. Take only the
item on the Next: line: <ITEM>. Read the write-up it names. Do not
start the next item.

Prove it on the ladder: simulation first, then the Nano 4K, then the
Primer 20K / Dock. SRAM-load bitstreams only (-m). The Nano disk data
file is the only flash write, and only in 0x200000–0x3FFFFF.

A full Icarus + Micron DDR3 blink run is only after a real DDR3
failure. If both boards already blink on this tip, the Dock stage is
closed.

Publish the blink formula before trusting the board. Measure with the
webcam MCP. A failed check leaves the LED dark. A Dock result counts
only after three SRAM loads, and only when the UART shows the boot
succeeded. The Nano has no UART; watch the LED.

If the 4K does not fit after shrinking inside this item, stop and name
the next open bring-up ledger item. Do not take that cut yourself.

Record the measured result in the write-up, mark the to-do Done, set
Next:, commit, and open one PR. Fast-forward origin/main after green
CI (no merge commit). Do not start the next item. Do not reset other
checkouts. Report board results and failed checks as they happen.
```

Add only the deltas for that item: which write-up, where the capture card is, 4K-only if the to-do says so, a three-line handoff if this is a takeover. Do not paste the whole night plan into the prompt. The skills and `docs/todo.md` are the source of truth; the prompt names the item and the constraints that are easy to miss.

## How results come back

The worker reports in its own thread. The Project receives that as a worker message: rates, place numbers, clip paths, UART lines, PR URL. The coordinator puts a short version in chat when a board result or a failed check happens. A sim rerun is not a reason to stay silent. Progress notes go out on the timer (half an hour when the maintainer is around, hourly overnight). Do not ask the maintainer to open the worker transcript to learn the state.

### Pull requests and merge

One item, one branch, one PR, based on `main`. `main` stays a straight line: rebase, not a merge commit. The maintainer's preference, and `AGENTS.md`, is rebase. PRs #41–#43 landed that way. The night loop does the same.

The coordinator's GitHub token cannot merge (403). The Omarchy agent fast-forwards `origin/main` to the already-rebased PR head. GitHub then marks the PR merged. No new commit is invented for the merge.

If `main` moved under the PR, rebase the feature branch onto current `origin/main`, force-push with `--force-with-lease`, wait for CI again, then fast-forward. Do not start the next item until that commit is on `main`, so the `Next:` line the next agent reads is true.

Stacked PRs were used earlier for the DDR3 file/module stack. That is not the night loop. The night loop is sequential: land, then start the next agent from that `main`. `AGENTS.md` still describes how to rebase-merge a stack if one exists (bottom first, force-push the child, only then retarget its base to `main`). Do not rebase-merge a child that still carries the parent's old SHAs.

The agent that proved the item opens the PR. The coordinator watches it. Do not stop the ladder because a PR is open or "for review". Continue. Land a step when it is proved.

### CI

GitHub Actions workflow `ci` (`.github/workflows/test.yml`) runs on `ubuntu-latest` for every push and pull request. It is mill tests, a Verilator frame check, Norebo/`.rsc` checks, and webcam-MCP unit tests. It is not Gowin place-and-route and not a board load. A healthy run is about two minutes with warm caches.

The coordinator subscribes to CI on the PR branch. Green CI is the usual gate before fast-forwarding `main`. A GitHub runner stall (apt failing to reach the Ubuntu archive for an hour) is not a proof failure. Local mill, Verilator, and the board measurements are what count. Do not leave the ladder idle for hours on CI. After a stall, stay on GitHub-hosted `ubuntu-latest`; do not move the suite for one bad afternoon.

### What counts as done

All of these:

- Simulation, Nano 4K, and Primer 20K agree on this tip (or the item is explicitly 4K-only in `docs/todo.md`)
- The published blink formula was written before the board was trusted, and the webcam (and capture card, when the picture is the proof) measured that rate
- A failed check left the LED dark; a pass did not
- Bitstreams were SRAM-loaded; the only flash write, if any, was a Nano disk image in `0x200000`–`0x3FFFFF`, read back
- Dock: UART shows boot succeeded, on three loads when the three-load rule applies
- The measured result is recorded in the write-up the to-do names
- The to-do line is marked Done, `Next:` points at the following item
- One PR is open or already on `main`

Not done: a place-and-route that was never loaded; three SRAM programs with no UART or LED check; a status-block picture without the arm word; an agent that stopped because it wanted a review.

### When the maintainer is pinged

Ping when a person is actually required:

- Move the HDMI capture cable
- Press Nano S1 (or any button test)
- A Dock power cycle the agent cannot do
- The Nano 4K does not fit and a ledger cut needs a choice the docs do not already rank
- After the first Nano HDMI picture, before the first Primer 20K HDMI work, until they have said the 20K is plugged in
- In the morning, if overnight work stopped (three items in a row failed, or a DDR3 attempt spent about four hours on a run that had clearly gone wrong)

Do not ping, and do not wait, for: permission to start the next item after they have already said to run the queue; an open PR; CI that is merely slow; a board result you can put in chat yourself.

Overnight stop rules, when they have left you the queue: end the night after three items in a row that do not pass, or after about four hours on a DDR3 attempt that is obviously the wrong long sim rather than real work. Do not cut an agent short that is still doing obvious work. A step with no real dependency on the failed one can be skipped and returned to later. If the board stops making progress, stop.

## Standing rules from repeated corrections

These started as corrections in the Project and are now how the loop runs.

- **A new agent every item.** That is the point of the Project. Do not run the next to-do on the agent that just finished.
- **One small step per agent.** If a prompt names two items, stop after the first and start a new agent for the second.
- **Do not wait for the maintainer** unless the proof needs their hands. Waiting on an open PR, a review, or "what should I do next" while `Next:` is known is refusing the process.
- **Simulation first.** Do not reload hardware until sim passes. A dark LED on the 4K is a failed 4K stage: back to Verilator, then the ladder again.
- **The long DDR3 sim is not the default.** Icarus plus Micron through `Modules.Init` to two LED edges is only for a real DDR3 failure. Boards that already blink do not require it. N=5 does not skip the boot.
- **SRAM only.** Never a bitstream to flash. Nano disk data only in `0x200000`–`0x3FFFFF`, read back.
- **The LED is the proof.** Publish the formula, measure it, dark means fail. Loading the bitstream three times is not a measurement. On the Dock the UART must show the boot succeeded; on the 4K watch the LED.
- **Three Dock loads.** One trained load is not enough to call a Dock step good or bad.
- **Own worktree.** Shared Omarchy. Do not reset another agent's checkout.
- **Report board results when they happen.** Do not stay silent through a sim rerun or a failed check.
- **Keep going overnight without a person at the hub.** Passwordless sudo, if needed, is a named script with no arguments (`sudo -n /usr/local/sbin/blinky-bind-dock-uart` for Dock UART interface B). Never ask for a sudo password in the agent loop.
- **Do not block a proved item on a sick CI runner.** Land it and start the next item.
- **Do not stop for review.** Land a step when it is proved.
- **Subagents are non-fast.**
- **Plans and prompts in plain language.** Hardware and Oberon terms are explained the first time. Dictation from the maintainer is read for intent.

## What is FPGA-specific, and what a new Project can reuse

The next Project in this shape is an M5Paper e-ink ESP32 board on the Pi 400. Most of the loop transfers. The FPGA ladder does not.

### Reuse as-is

- A Cursor Project coordinator that only starts work, never does the device work in its own checkout
- `docs/todo.md` as an index with a `Next:` line; write-ups elsewhere; Done stays in place
- One small step per fresh agent, own worktree, one PR, rebase onto `main`, next agent from that `main`
- Skills the agent must read first, with the prompt naming only the item and the easy-to-miss constraints
- Place the agent on the self-hosted worker that is physically attached to the device (here omarchy-blinky; there pi400)
- Use cloud placement for docs-only work that would collide with a hardware worktree
- Report results in the Project chat when they happen; timer notes; ping the person only for hands
- Do not wait for review; do not reuse a spent agent; do not combine steps
- Stop the night after a short streak of dead items, not after the first difficulty
- Non-fast subagents

### Replace for a different device

| Blinky (FPGA) | What to invent for the M5Paper (and any later board) |
|---|---|
| Prove ladder: Verilator, then Nano 4K HyperRAM, then Primer 20K DDR3 | One ordered proof for **that** board (build or host sim, then the paper, then any second target) |
| Icarus + Micron `ddr3.v` only on a real DDR3 failure | Do not copy this. Put expensive sims behind a real failure of **that** bus or display, not on every step |
| Webcam MCP LED rate vs a published formula | The visible proof for e-ink (a photo of the panel, a host screenshot, a UART line). Publish what "pass" looks like before trusting the device |
| Gowin SRAM load, `openFPGALoader -m` | Whatever flashes or loads that ESP32, with an explicit rule about what may be written |
| Nano 4K CLS ledger | The M5Paper's scarce resource list (flash, PSRAM, panel refresh), if any |
| Three Dock SRAM loads and UART boot | Whatever flake the panel or USB-serial has; do not assume three loads |
| HDMI capture cable | Probably nothing; do not invent a cable-swap ritual |
| omarchy-blinky USB buses `003:081` / `003:078` | The Pi 400's serial device and how the agent finds it |

The webcam MCP stays on the FPGA desk unless the Pi 400 actually has that camera. Do not point an M5Paper agent at `measure_blink` because Blinky did.

A new Project should start with: a strategy page, a to-do index, one prove skill, one "take the next item" skill, a grant on the worker that holds the device, and a coordinator that already knows "fresh agent, one step, report, land, next".
