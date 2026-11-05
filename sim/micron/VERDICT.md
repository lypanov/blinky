# Verdict: OK after cleanup, do not hand this tree over as-is

Checked `daee393` against the files in this directory and two other
public v1.74-labelled copies. No board step was run.

## What these bytes are

`ddr3.v` SHA-256
`324b53caf7acd31cfda4ae180dd6326cd70c645680e8d727383243b362603257`
(166121 bytes). `1024Mb_ddr3_parameters.vh` SHA-256
`7c08190c734edc3a5fa09199ae849ad235c9b3930dfb223f5e517a426c2e5384`
(55018 bytes). The header is Micron, version 1.74, copyright 2003,
and the changelog ends at SPH 09/08/15, the CWL 9 / tIS fix.

Stripping comments, the `.v` differs from buttercutter/DDR `ddr3.v`
(SHA-256 `81d7af65d262aeb6fe7fb6f1f8090c9b9cc8a2dc8135734db5f23c45ce75b03d`)
only in the port shell and the baked defines. That other file is the
classic port list and drives read data back onto `dq` / `dqs` /
`dqs_n`. This file is that body with a student shell on it.

## Why it is not a drop-in

The shell is not the model nand2mario's Makefile calls.

- Lines 100–102 are `` `define den1024Mb ``, `` `define x8 ``,
  `` `define sg093 ``. The parameter file tests `sg093` before
  `sg25`, and tests `x8` before the `x16` else. A command line
  `-D den1024Mb -D sg25 -D x16` does not win. The part that gets
  built is an 8-bit DDR3-2133 (`TCK_MIN` 938 ps, `DQ_BITS` 8,
  `ROW_BITS` 14, one DQS). The Dock controller is x16, 13 row bits,
  two DQS, at about 2.5 ns. The `sg25` row in this same header is
  `TCK_MIN` 2500 ps, and the `x16` row is `DQ_BITS` 16, `ROW_BITS`
  13, `DQS_BITS` 2. Those rows are present and unused.
- The module is `module ddr3 (intf.mem ifx)`. `ck_n` is `~ifx.ck`,
  not a pin. Read data is driven onto `dq0` / `dqs0` / `dqs0_n`
  ("to avoid inout port"). A testbench wired to `dq` / `dqs` writes
  into the model and never sees the read burst come back.
- The mask pin was renamed from `dm_tdqs` to `dm`.

`1024Mb_ddr3_parameters.vh` is the right density file. Its only
student text is the first comment line.

## Do not substitute these other mirrors

| File | SHA-256 | Why not |
|---|---|---|
| buttercutter/DDR `ddr3.v` | `81d7af65d262aeb6fe7fb6f1f8090c9b9cc8a2dc8135734db5f23c45ce75b03d` | Classic ports, but bakes `` `define den2048Mb 1 ``. |
| nguyentrungduong `testbench/ddr3.v` | `77f69079950f1db521d526b213ce10564b0d2dfb6dabfe469149c6c2360efea9` | Classic ports, but bakes `den8192Mb`, `sg125`, and `x16`, and adds `FLY_BY_DELAY` on the DQ driver. |

## Cleanup that makes this file usable

Restore the classic shell. Do not edit the tasks or the timing checks.

1. Delete the student banner and the three `` `define `` lines. Leave
   density, width, and speed to the command line.
2. Replace `module ddr3 (intf.mem ifx)` with the port list `rst_n`,
   `ck`, `ck_n`, `cke`, `cs_n`, `ras_n`, `cas_n`, `we_n`, `dm_tdqs`,
   `ba`, `addr`, `dq`, `dqs`, `dqs_n`, `tdqs_n`, `odt`.
3. Declare those as `input` / `inout` / `output`, matching the
   buttercutter declarations. `ck_n` is an input.
4. Delete every `ifx.` assign, and the `dq0` / `dqs0` / `dqs0_n` nets.
5. Point the three `bufif1` drivers back at `dqs`, `dqs_n`, and `dq`.
6. Rename the mask port back to `dm_tdqs` at the declaration and at
   the one `always @(dm)` that samples it.

After that diff, the `.v` should match the buttercutter body apart
from not defining `den2048Mb`. Compile with the published flags
`-D SIM -D den1024Mb -D sg25 -D x16` and this parameters file. Until
that patch is in the tree, the answer to handing this import to the
DDR3 sim agent is no.
