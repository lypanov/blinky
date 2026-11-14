---
name: prove-ladder
description: >-
  Prove each Blinky ladder step in order: simulation first (Verilator for
  the Nano 4K image, Icarus with Micron ddr3.v for a Dock DDR3 image),
  then Tang Nano 4K HyperRAM hardware, then Primer 20K Dock DDR3. Use
  when advancing a ladder step, proving a step, loading the 4K or the
  Dock, or checking a blink on the webcam. A step is done only when sim,
  4K, and 20K all agree.
---

Prove every ladder step in this order and do not skip a stage. First run simulation until the expected checks pass. The Nano 4K image is Verilator (`tools/run_verilator_sim.sh`). When the step touches DDR3, the Dock image is Icarus with the Micron `ddr3.v` model (`sim/run_ddr3_cpu_phy.sh`). The Verilator stand-in does not close that check. Then load the same tip on the Tang Nano 4K (HyperRAM) and confirm on hardware — usually the LED blinks at the published formula rate, measured by the webcam, with a dark LED meaning fail. Only after that, prove the same tip on the Primer 20K / Dock (DDR3). A step is done only when sim, 4K, and 20K all agree.

How to load each board, and how to read the capture card, is `docs/load-boards.md`. The LED is the pass. The HDMI stick (`/dev/video0`) is a second witness of the same arm word, only after that pass: YUYV 720×480 on the Nano and 1024×768 on the Dock. `tools/hdmi_stats.py --board nano|dock` prints luma. White is 255. A locked grey field with luma about 139 and U=V=128 is not armed, or the size does not match the cable. Do not convert YUYV to RGB, and do not run `measure_blink` on HDMI. The webcam is `/dev/video2`; `measure_blink.sh` defaults to `/dev/video0`, so an LED clip needs `--device /dev/video2`.
