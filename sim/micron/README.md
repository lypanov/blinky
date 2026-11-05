# Micron DDR3 Verilog model

Upstream Micron SDRAM DDR3 model **version 1.74**, cleaned to the
classic port list. Copyright 2003 Micron Technology, Inc. All rights
reserved.

Private-repo import only. Do not redistribute these files further.

Compile with `-D SIM -D den1024Mb -D sg25 -D x16`. Density, width,
and speed are not baked into `ddr3.v`.

- Ports are `rst_n`, `ck`, `ck_n`, `cke`, `cs_n`, `ras_n`, `cas_n`,
  `we_n`, `dm_tdqs`, `ba`, `addr`, `dq`, `dqs`, `dqs_n`, `tdqs_n`,
  `odt`. Read data is driven back onto `dq` / `dqs` / `dqs_n`.
- `ddr3.v` includes `1024Mb_ddr3_parameters.vh` when `den1024Mb` is
  defined.
- The body matches the classic v1.74 file apart from not defining
  `den2048Mb`, and apart from five task ports whose width is now
  on the input. Icarus 12 rejects `input i; reg [N:0] i;`. The
  tasks are `cmd_addr_timing_check` (`[4:0]`), `dm_timing_check`
  (`[4:0]`), `dq_timing_check` (`[6:0]`), `dqs_pos_timing_check`
  (`[5:0]`), and `dqs_neg_timing_check` (`[5:0]`). See `VERDICT.md`.
- `sim/run_ddr3_phy.sh` is the Icarus bench against
  `ddr3_controller`. `docs/primer20k/ddr3-phy-sim.md` says what
  that run does and does not prove.
