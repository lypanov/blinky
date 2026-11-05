# Micron DDR3 Verilog model

Upstream Micron SDRAM DDR3 model **version 1.74**.
Copyright 2003 Micron Technology, Inc. All rights reserved.

Private-repo import only. Do not redistribute these files further.

- Obtained via https://github.com/alice820621/SystemVerilog-Implementation-of-DDR3-Controller
  after the official Micron download failed.
- `ddr3.v` includes `1024Mb_ddr3_parameters.vh` when `den1024Mb` is defined.
- nand2mario Icarus + Gowin `prim_sim` expects:
  `-D SIM -D den1024Mb -D sg25 -D x16`
