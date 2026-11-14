---
name: prove-ladder
description: >-
  Prove each Blinky ladder step in order: Verilator for the Nano 4K
  image, then Tang Nano 4K HyperRAM hardware, then Primer 20K Dock
  DDR3. A full Icarus plus Micron run through Modules.Init to two LED
  edges is only after a real DDR3 failure. Use when advancing a ladder
  step, proving a step, loading the 4K or the Dock, or checking a blink
  on the webcam, or when the user says HDMI is plugged into 4K or 20K.
  A step is done only when sim, 4K, and 20K all agree, unless skip 20K
  or skip 4K is given for that item.
---

## Webcam MCP (LEDs)

The LED camera is the webcam MCP on this machine, not `measure_blink.sh`
and not an import of `server.py`.

- URL: `http://127.0.0.1:8766/mcp`
- Service: `systemctl --user status webcam-mcp.service`
- Device: `/dev/video2` (Logitech). `/dev/video0` is the HDMI stick.
- Tools: `list_cameras`, `capture_still`, `auto_adjust`, `detect_leds`,
  `measure_blink`, `check_all`

Cursor desktop on Bee gets those tools from `~/.cursor/mcp.json`. A cloud
agent on the same box often does not: its catalog is GitHub, Notion, and
the like, not that local URL. Call the HTTP MCP with the service venv:

```python
from mcp import Client

async with Client("http://127.0.0.1:8766/mcp", read_timeout_seconds=120) as client:
    await client.call_tool("check_all", {"duration": 16, "device": "/dev/video2"})
```

Interpreter: `/home/lypanov/fpga/blinky-webcam-mcp/tools/webcam-mcp/.venv/bin/python`

Do **not** `import server` from `tools/webcam-mcp/server.py`. That is the
same functions on a private path, not the MCP. `tools/measure_blink.sh
--device /dev/video2` is only if the service is down.

`roi=nano4k` is a blob, not a pixel. If that result is FFT-only with no
edges, or the box is on the far right of the 640 frame, it is not the
lamp. Open the annotated still and measure the other lower orange blob.

Which board has the HDMI cable: `.cursor/skills/identify-hdmi-board/SKILL.md`.

## HDMI cable

The maintainer's words **HDMI is plugged into 4K** and **HDMI is plugged into 20K** name which board the capture card is on. Prove that board now. Size is YUYV 720×480 on the 4K and 1024×768 on the 20K. When the room is lit, confirm with `.cursor/skills/identify-hdmi-board/SKILL.md`.

An item is not done until sim, 4K, and 20K all agree, unless the maintainer says **skip 20K** or **skip 4K** for that item (for example "skip 20K for item 47").

If HDMI is on the 4K and the 20K stage is still required, after the 4K HDMI proof **stop and ask the maintainer to switch HDMI to the 20K**. Do not mark the item done. Do not assume the cable has moved. Same if HDMI is on the 20K and the 4K stage is still open: ask for the switch to the 4K.

## Norebo

Verilator compiles Oberon with the machine tree `/home/lypanov/fpga/norebo-compiled`. `tools/setup_norebo.sh` creates it if it is missing. Do not clone `tools/project-norebo` in the worktree. If you `tee` the sim log, use `set -o pipefail`.

## Ladder

Prove every ladder step in this order and do not skip a stage. First run simulation until the expected checks pass. Verilator (`tools/run_verilator_sim.sh`) proves the CPU image. Then load the same tip on the Tang Nano 4K (HyperRAM) and confirm on hardware — usually the LED blinks at the published formula rate, measured by the webcam, with a dark LED meaning fail. If Gowin CT1135 names `bodyFor_31_N`, that N is this netlist. Grep the place log for `bodyFor_31_` and put that wire in `tang-nano-4k-hdmi.cst`. Only after that, prove the same tip on the Primer 20K / Dock (DDR3). When the Nano 4K and the Primer 20K already blink on this tip and there is no real DDR3 failure, the Dock stage is closed. A step is done only when sim, 4K, and 20K all agree.

A full Icarus plus Micron run through Modules.Init to two LED edges (`IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh`) is only for a real DDR3 failure: calibration, the write eye, the controller, or the Micron protocol. N=5 does not skip the boot. That image still runs Modules.Init before the delay loop, so the ladder must not demand the run just to print a blink score.

A failed 4K stage returns to Verilator. A Dock failure in calibration, the write eye, the controller, or the Micron protocol returns to the full Icarus plus Micron run. Any other Dock failure returns to Verilator. Fix the cause, then run the ladder again from sim. Loop until sim, 4K, and 20K agree. Stop the loop when the Nano 4K does not fit. Report that stage.

After a negative test (stuck disk, trap, damaged font), SRAM-load the good image on that board before finishing. Leave both boards blinking. Do not leave a stuck or trap picture on HDMI.

How to load each board, and how to read the capture card, is `docs/load-boards.md`. The LED is the pass. The HDMI stick (`/dev/video0`) is a second witness of the same arm word, only after that pass. Capture with `tools/hdmi_capture.sh` (open the stick, then load). YUYV 720×480 on the Nano and 1024×768 on the Dock. White is 255. A locked grey field with luma about 139 and U=V=128 is not armed, or the size does not match the cable. Do not convert YUYV to RGB, and do not run `measure_blink` on HDMI.
