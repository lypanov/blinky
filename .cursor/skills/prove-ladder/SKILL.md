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
