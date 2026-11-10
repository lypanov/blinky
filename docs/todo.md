# To-do

One item at a time, from the top. This file is an index. The write-up is in the file each item names.

Next: 28.

1. Omit the Logger on the 4K. [`docs/bringup-ledger.md`](bringup-ledger.md) item 1. That is the 4K UART change. The Dock training UART stays. Both blink laws stay. Done. The measured result is in the ledger.

Ledger items are not to-dos. If a later item cannot fit on the Nano 4K without an architecture change, name the next open ledger item you would take (lowest number first). Do not take it in the same task.

2. The 32 KB reserve. [`docs/modules-mod-plan.md`](modules-mod-plan.md), Proof 1 in "Work from this tip". Done. The measured result is in the plan.
3. `DIV`, `H`, and `SYSTEM.BIT`. Same file, Proof 2. Done. The measured result is in the plan.
4. The trap at `MT[0]`. Same file, Proof 3. Done. The measured result is in the plan.
5. Compiled `Modules.Check` on the ROM loop. Same file, Proof 4. Done. The measured result is in the plan.
6. Place Blink5 and fetch that body. Same file, Proof 5. Done. The measured result is in the plan.
7. One sector step. Same file, Proof 6. Done. The measured result is in the plan.
8. Real `Modules.Init` and `Modules.Load("Blink5")`. Same file, Proof 7. Done. The measured result is in the plan.

9. Count every Nano 4K block RAM and remove the dead ones. [`docs/bringup-ledger.md`](bringup-ledger.md), item 4. Done. Nothing among the ten blocks is dead. The list is in the ledger.
10. Pathfinder: write the Nano 4K's external SPI flash, SRAM-reload, read it back. Same file, item 5. Nano 4K only. Done. The measured result is in the ledger. JEDEC `85 60 16`, and the page survived a fresh SRAM load.
11. Replace the pre-armed check mask with an arm word that software must compute. Same file, item 6. Done. The measured result is in the ledger.

12. The disk image builder, and the host writes the 4K's flash disk. Same file, item 7. Nano 4K only. Done. The measured result is in the ledger.
13. Boot the 4K from the flash disk: the ROM becomes a bootstrap. Same file, item 8. Nano 4K only. Done. The measured result is in the ledger.

14. Nano 4K: HDMI timing, and the whole screen flashes with the LED. [`docs/hdmi.md`](hdmi.md), step 1. Capture card on the 4K. Done. The measured result is in that file.
15. Nano 4K: one square blinks on a black screen, drawn by Blink5. Same file, step 2. Capture card on the 4K. The 4K's video stops here. Done. The measured result is in that file.
16. Dock: the same full-screen flash. Same file, step 3. Capture card on the Dock. Done. The measured result is in that file.
17. Dock: the same square. Same file, step 4. Done. The measured result is in that file.
18. Dock: a blink counter in text on screen. Same file, step 5. Done. The measured result is in that file.

19. Button gate on both boards, proved on hardware. [`docs/next-steps.md`](next-steps.md), item 19. Brings back PR #22. Done. The measured result is in that file.
20. Screen check in Verilator: one frame at a chosen cycle against a host-drawn image. Same file, item 20. Done. The measured result is in that file.
21. Dock: the screen at 1024×768. Same file, item 21. Done. The measured result is in that file.
22. Dock boots like the 4K: the same `disk.bin` and bootstrap, the disk sent over the UART into DDR3. Same file, item 22. Done. The measured result is in that file.
23. Retire the old step images from the CPU. Same file, item 23. Also bring-up ledger item 11. Done. The measured result is in that file and in the ledger.
24. Move the bootstrap flash ports off −64 and −60. Same file, item 24. Done. The measured result is in that file.
25. The millisecond timer at −64; Blink paces itself with `Kernel.Time`. Same file, item 25. Done. The measured result is in that file.
26. The button as Oberon input: Blink reads it and decides. Same file, item 26. Done. The measured result is in that file. The Nano S1 check is the maintainer's, by hand.
27. Hardware `MUL`. Same file, item 27. Done. The measured result is in that file.
28. `NEW` and garbage collection, with a lowered memory limit. Same file, item 28.
29. The blink rate read from a file on the disk. Same file, item 29.
30. File writes through a RAM overlay; the rate changes partway through a run. Same file, item 30.
31. Oberon's own boot linker and `BootLoad` build and boot the disk. Same file, item 31.

The rest of `docs/modules-mod-plan.md` is the original fifteen and the boot path. Read a section when the proof cites it. Those headings are not a second queue.
