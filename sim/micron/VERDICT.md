# Verdict: cleaned classic ports, handoff yes

Icarus 12 note, after the handoff: five task ports in `ddr3.v`
declare the old `reg` width on the `input`. The operations in those
tasks are unchanged. The cleaned file before that edit was
SHA-256 `b8275b279bde5346a7d036f61122d4de0f11e577d41467e86800558e17ef1c8c`.

The shell prescribed below is now applied on this branch. No board
step was run. `1024Mb_ddr3_parameters.vh` is unchanged
(SHA-256 `7c08190c734edc3a5fa09199ae849ad235c9b3930dfb223f5e517a426c2e5384`).

`ddr3.v` is the classic Micron v1.74 body. The only difference from
buttercutter/DDR `ddr3.v`
(SHA-256 `81d7af65d262aeb6fe7fb6f1f8090c9b9cc8a2dc8135734db5f23c45ce75b03d`)
is that `` `define den2048Mb 1 `` is not present, plus the five
Icarus port widths named above. Ports are `rst_n`,
`ck`, `ck_n`, `cke`, `cs_n`, `ras_n`, `cas_n`, `we_n`, `dm_tdqs`,
`ba`, `addr`, `dq`, `dqs`, `dqs_n`, `tdqs_n`, `odt`. The three
`bufif1` drivers write `dqs`, `dqs_n`, and `dq`. There is no
`intf.mem` port, no `ifx.` assign, and no baked `den1024Mb`, `x8`,
or `sg093`.

Compile with `-D SIM -D den1024Mb -D sg25 -D x16`. Those flags select
the 1Gb parameters, the DDR3-800 `sg25` row (`TCK_MIN` 2500 ps), and
the x16 row (`DQ_BITS` 16, `ROW_BITS` 13, `DQS_BITS` 2). This remains
a private-repo import of Micron Verilog model v1.74. Do not
redistribute it.

This cleaned tree may be handed to the DDR3 sim agent.

## What the import was before the cleanup

The imported `ddr3.v` was SHA-256
`324b53caf7acd31cfda4ae180dd6326cd70c645680e8d727383243b362603257`
(166121 bytes). The header was already Micron 1.74, copyright 2003,
changelog ending at SPH 09/08/15. With comments stripped it matched
the buttercutter body except for a student shell: `` `define den1024Mb ``,
`` `define x8 ``, `` `define sg093 ``, `module ddr3 (intf.mem ifx)`,
`ck_n` tied to `~ifx.ck`, read data driven onto `dq0` / `dqs0` /
`dqs0_n`, and the mask pin renamed to `dm`. The parameter file tests
`sg093` before `sg25` and `x8` before the `x16` else, so the nand2mario
command line could not override those baked defines.

The parameters file's only student text is its first comment line.
That line was left in place.

## Mirrors that were not used as the replacement

| File | SHA-256 | Why not copied as-is |
|---|---|---|
| buttercutter/DDR `ddr3.v` | `81d7af65d262aeb6fe7fb6f1f8090c9b9cc8a2dc8135734db5f23c45ce75b03d` | Classic ports, but bakes `` `define den2048Mb 1 ``. This tree is that file with the define removed. |
| nguyentrungduong `testbench/ddr3.v` | `77f69079950f1db521d526b213ce10564b0d2dfb6dabfe469149c6c2360efea9` | Classic ports, but bakes `den8192Mb`, `sg125`, and `x16`, and adds `FLY_BY_DELAY` on the DQ driver. |
