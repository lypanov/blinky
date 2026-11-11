# Oberon sources

`src/Kernel.Mod`, `src/FileDir.Mod`, `src/Files.Mod`, and `src/Modules.Mod` started as Niklaus Wirth's Project Oberon (Revised Edition 2013) inner core, fetched from

`https://people.inf.ethz.ch/wirth/ProjectOberon/Sources/<Name>.Mod.txt`

`Modules.Mod` is the 8.1.2019 text. `docs/OberonSources/Modules.Mod` is the 2016 copy and is not what the compiler reads. Line endings are the publisher's CRLF. Checksums are `SHA256SUMS`. The licence is `LICENSE.txt`.

`FileDir.Mod` and `Modules.Mod` are still those bytes. `docs/OberonSources/Kernel.Mod` and `docs/OberonSources/Files.Mod` are still the book. The copies the compiler reads differ, as of the RAM sector table:

`Kernel.GetSector` returns a sector from a two-slot table in RAM when `PutSector` has stored it, and otherwise reads the disk as before. `PutSector` stores into that table and does not call `WriteSD`. The table is cleared with the sector map and is lost at power-off. The flash is not erased.

`Files.Close` still writes modified pages through `PutSector`. It then drops the cached page, wipes it, and marks the buffer ring full so the next read reuses that buffer and comes back through `GetSector`. A stale buffer reads as zeros.
