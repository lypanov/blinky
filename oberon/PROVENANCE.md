# Provenance

Fetched 4 November 2026 from Niklaus Wirth's Project Oberon page (Revised Edition 2013):

<https://people.inf.ethz.ch/wirth/ProjectOberon/>

Each file in `src/` is `Sources/<name>.txt` from that page, with the `.txt` suffix removed. The bytes are unchanged, including CRLF line endings. `src/verilog/` is `SourcesVerilog/RISC5.v`, `PROM.v`, and `RISC5Top.v`: the reset address, the PROM window, and the negative-address I/O map cited by the boot section of `docs/modules-mod-plan.md`.

`LICENSE.txt` is `license.txt` from the same page. It matches <http://www.projectoberon.net/wirth/ProjectOberon/license.txt>. Software copyright 2013 Niklaus Wirth (NW), Jürg Gutknecht (JG), and Paul Reed (PR/PDR). Permission is granted to use, copy, modify, and distribute the software and its documentation for any purpose, with or without fee, provided the copyright notice and the permission notice appear in all copies. The book PDF is not in this tree.

`SHA256SUMS` lists `LICENSE.txt`, this file, and every file under `src/`.

## What was already in the repository

`docs/OberonSources/` is an earlier copy with no licence file. After CRLF normalisation:

| File | Against this tree |
|---|---|
| `Kernel.Mod`, `FileDir.Mod`, `Files.Mod`, `Oberon.Mod` | identical |
| `Modules.Mod` | the older text. `docs/OberonSources/Modules.Mod` matches `inner.zip` on projectoberon.net (header `9.4.2016`). The file here is the page's later text (header `8.1.2019`): `Load` begins with `error(0, name)`, and a failed load rolls import refcounts back when `res >= 3`. |
| `ORG.Mod` | the 18.4.2016 generator. The file here is the 17.9.2018 revision. |

The plan cites `oberon/src/`. The pinned Norebo compiler (`tools/norebo.pin`) remains the compiler that produces `.rsc` files; step 13 of the plan checks that those files match what this `Modules.Mod` reads.

Not imported: the Oberon font, the SD-card disk image (`RISCimg.zip`), and the rest of the Verilog board support. The published page has no `Linker.Mod`. The prelinked inner-core image is described in the plan.
