# To-do

One item at a time, from the top. This file is an index. The write-up is in the file each item names.

Next: 11.

1. Omit the Logger on the 4K. [`docs/bringup-ledger.md`](bringup-ledger.md) item 1. That is the 4K UART change. The Dock training UART stays. Both blink laws stay. Done. The measured result is in the ledger.

Ledger items 2–5 are not to-dos. If a later item cannot fit on the Nano 4K without an architecture change, name the next ledger item you would take. Do not take it in the same task.

2. The 32 KB reserve. [`docs/modules-mod-plan.md`](modules-mod-plan.md), Proof 1 in "Work from this tip". Done. The measured result is in the plan.
3. `DIV`, `H`, and `SYSTEM.BIT`. Same file, Proof 2. Done. The measured result is in the plan.
4. The trap at `MT[0]`. Same file, Proof 3. Done. The measured result is in the plan.
5. Compiled `Modules.Check` on the ROM loop. Same file, Proof 4. Done. The measured result is in the plan.
6. Place Blink5 and fetch that body. Same file, Proof 5. Done. The measured result is in the plan.
7. One sector step. Same file, Proof 6. Done. The measured result is in the plan.
8. Real `Modules.Init` and `Modules.Load("Blink5")`. Same file, Proof 7. Done. The measured result is in the plan.

9. Count every Nano 4K block RAM and remove the dead ones. [`docs/bringup-ledger.md`](bringup-ledger.md), "Block RAM, item A". Done. Nothing among the ten blocks is dead. The list is in the ledger.
10. Pathfinder: write the Nano 4K's external SPI flash, SRAM-reload, read it back. Same file, "Block RAM, item B". Nano 4K only. Done. The measured result is in the ledger. JEDEC `85 60 16`, and the page survived a fresh SRAM load.
11. Replace the pre-armed check mask with an arm word that software must compute. Same file, "Block RAM, item C".

The rest of `docs/modules-mod-plan.md` is the original fifteen and the boot path. Read a section when the proof cites it. Those headings are not a second queue.
