---
name: prove-ladder
description: >-
  Prove each Blinky ladder step in order: Verilator for the Nano 4K
  image, then Tang Nano 4K HyperRAM hardware, then Primer 20K Dock
  DDR3. A full Icarus plus Micron run through Modules.Init to two LED
  edges is only after a real DDR3 failure. Use when advancing a ladder
  step, proving a step, loading the 4K or the Dock, or checking a blink
  on the webcam. A step is done only when sim, 4K, and 20K all agree.
---

Prove every ladder step in this order and do not skip a stage. First run simulation until the expected checks pass. Verilator (`tools/run_verilator_sim.sh`) proves the CPU image. Then load the same tip on the Tang Nano 4K (HyperRAM) and confirm on hardware — usually the LED blinks at the published formula rate, measured by the webcam, with a dark LED meaning fail. Only after that, prove the same tip on the Primer 20K / Dock (DDR3). When the Nano 4K and the Primer 20K already blink on this tip and there is no real DDR3 failure, the Dock stage is closed. A step is done only when sim, 4K, and 20K all agree.

A full Icarus plus Micron run through Modules.Init to two LED edges (`IMAGE=ddr3modules sim/run_ddr3_cpu_phy.sh`) is only for a real DDR3 failure: calibration, the write eye, the controller, or the Micron protocol. N=5 does not skip the boot. That image still runs Modules.Init before the delay loop, so the ladder must not demand the run just to print a blink score.

A failed 4K stage returns to Verilator. A Dock failure in calibration, the write eye, the controller, or the Micron protocol returns to the full Icarus plus Micron run. Any other Dock failure returns to Verilator. Fix the cause, then run the ladder again from sim. Loop until sim, 4K, and 20K agree. Stop the loop when the Nano 4K does not fit. Report that stage.

How to load each board, and how to read the capture card, is `docs/load-boards.md`. The LED is the pass. The HDMI stick (`/dev/video0`) is a second witness of the same arm word, only after that pass. Capture with `tools/hdmi_capture.sh` (open the stick, then load). YUYV 720×480 on the Nano and 1024×768 on the Dock. White is 255. A locked grey field with luma about 139 and U=V=128 is not armed, or the size does not match the cable. Do not convert YUYV to RGB, and do not run `measure_blink` on HDMI. The webcam is `/dev/video2`; `measure_blink.sh` defaults to `/dev/video0`, so an LED clip needs `--device /dev/video2`.
