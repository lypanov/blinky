# Oberon sources

`src/Kernel.Mod`, `src/FileDir.Mod`, `src/Files.Mod`, and `src/Modules.Mod` started as Niklaus Wirth's Project Oberon (Revised Edition 2013) inner core, fetched from

`https://people.inf.ethz.ch/wirth/ProjectOberon/Sources/<Name>.Mod.txt`

`Modules.Mod` is the 8.1.2019 text. `docs/OberonSources/Modules.Mod` is the 2016 copy and is not what the compiler reads. Line endings are the publisher's CRLF. Checksums are `SHA256SUMS`. The licence is `LICENSE.txt`.

`FileDir.Mod` and `Modules.Mod` are still those bytes. `docs/OberonSources/Kernel.Mod` and `docs/OberonSources/Files.Mod` are still the book. The copies the compiler reads differ, as of the RAM sector table:

`Kernel.GetSector` returns a sector from a two-slot table in RAM when `PutSector` has stored it, and otherwise reads the disk as before. `PutSector` stores into that table and does not call `WriteSD`. The table is cleared with the sector map and is lost at power-off. The flash is not erased.

`Files.Close` still writes modified pages through `PutSector`. It then drops the cached page, wipes it, and marks the buffer ring full so the next read reuses that buffer and comes back through `GetSector`. A stale buffer reads as zeros.

`Kernel.Trap` still calls `New` for trap 0. Any other trap stores `80H +` the trap number at −84, so bit 8 stays clear and the status blocks show bit 7 and the number, then stops.

The published Project Oberon 2013 sources have no separate boot linker. `Modules.Load` is the linker, and it cannot load the inner core because the core contains `Modules`. The host linker is `CoreLinker.Mod` from the pinned Norebo tree, `tools/project-norebo/Norebo/CoreLinker.Mod`, commit `0e4731bc2c2551c907b7cba96079efd1316e92d6` of `https://github.com/pdewacht/project-norebo`. Its heading says it is derived from NW 20.10.2013. `CoreLinker.LinkDisk` writes the boot file: a directory sector, then the image whose word 0 branches to the Modules body, word 4 is the allocation pointer, and word 5 is the root descriptor. The same offsets are what `VDisk.GetSector` and the book's `BootLoad` use.

`src/BootLoad.Mod` is that loader, from `https://people.inf.ethz.ch/wirth/ProjectOberon/Sources/BootLoad.Mod.txt` (NW 20.10.2013 / PR 4.2.2014). The card is already idle, so the body does not run `InitSPI`. The switch is the user button, so the line path is not compiled in. `Uart` selects the NOR or the Dock copy. The header, the checksum, and the arm checks stay.
