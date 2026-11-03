# Main-forward plan

Bring `main` (7d47778, 9 Mar 2025) onto `blink2-4x` (a68a501 plus Verilator/visualizer/webcam/Gowin tooling and a 2x Blink2hw delay word) **one small step at a time**, keeping Blink2 blinking in the Verilator simulator after every step.

- Branch: `main-forward`, created from `blink2-4x` (`7944e4c`).
- Do not touch PR #2 or `blink2-4x` / `verilator-sim-a68a501`.
- Keep blink2-4x tooling (`tools/run_verilator_sim.sh`, visualizer, webcam meter, `tools/gowin_build.sh`) and the 2x Blink2hw delay word (`MHI R0, 0x4` / `0x60000004`, `maxIterations := 262144`).
- After each step: `tools/run_verilator_sim.sh` and confirm LED edges. Record the result here.

## Commits on `a68a501..main` (oldest first)

| SHA | Subject | Kind |
|---|---|---|
| `e1fef8c` | Logger class replaces UartTest; UART LED-toggle messages | CPU / UART |
| `ed9d355` | Logger can append a hex byte | CPU / UART |
| `14d7b97` | cursorrules: `./build.sh` compile check | docs |
| `e920df6` | Failed UART hex memory dump | CPU / mem — **reverted** |
| `073dda5` | `.rsc` format spec | docs |
| `1f9d7c9` | Fixup-aware rsc_parser; R13 hack R0→R12; Blink2/3 images use `LDW R13, [R12, 0x4]` | CPU / linker / images |
| `387b227` | Back out `e920df6` | net-zero with `e920df6` |
| `71f84f1` | First `image_dump` / `module_loader`; parser dumps addresses | linker |
| `5cb18fe` | More fixup/loader work; `mt_table.py`; process_mod_files calls loader | linker |
| `f9bb7b6` | Refresh `.asm` listings with addresses | images |
| `f6719da` | Final system-image fixup fixes | linker |
| `5e8ccb2` | Custom memory image on CPUSubset0 + system-image test | CPU / tests |
| `9d190e2` | Drop R13 load hack; setup R12/MT + vars at 0x50; IMEM halt 0xA0→0xB0 | CPU / memmap — **LED risk** |
| `0d5f6e2` | PC always starts at 0x80; restore trace init in system-image test | CPU / tests |
| `7d47778` | ignore `__pycache__` | already on blink2-4x as `__pycache__/` |

## Known risks (from `main` and the ISA)

### 1. LED snoop 0x10 vs variables at 0x50

On a68a501 / blink2-4x the R13 load hack forces `LDW R13, [R0, off]` to 0x10, so Blink2's `STW` of `light` hits the LED snoop at **0x10**.

`1f9d7c9` retargets that hack to R12 and the compiled images to `LDW R13, [R12, 0x4]`. The hack still returns 0x10, so Blink2 still writes the LED at 0x10.

`9d190e2` **removes the hack** and installs a real MT:

- `MOV R12, 0x10`
- `MOV R13, 0x50`; `STW R13, [R12, 0x04]` so `[0x14] = 0x50`
- module vars live at **0x50**

Blink2 then stores `light` at 0x50, while `CPUSubset0` still snoops **0x10**. The Treadle test on `main` even waits for writes at 0x50, not the LED. **This is the change that stops the LED toggling.** Minimal fix: snoop both 0x10 and 0x50 so Blink2 (and old 0x10 programs) still drive `io.led`.

### 2. BL does not save R15

ISA (`docs/risc_5_arch.txt`): `BL` / `v=1` must do `R15 = PC + 4` then branch. `CPUSubset0` never writes R15 on a taken branch. Blink2 does not use `BL` (it saves the trampoline's R15 on the stack and returns with `BT R15`). Blink3 / `AMemoryMappedToggle` **does** use `BL`. `main` never implemented this; it remains an open issue, not something this branch invents.

### 3. IMEM is too small for a linked system image

Default IMEM is still the split map: user code 0x00–0x80 (32 words). Blink2 is 30 instructions and fits. `9d190e2` only grows setup/halt 0xA0→0xB0 / 0xB0→0xC0. Linked Blink3 lives at 0x1000+ (`tests/final_system.code`); that is why `5e8ccb2` added `customMemoryImage`. CPUSimTop keeps loading `Blink2test.code` into the small default IMEM.

### 4. Blink3 and the linker

`main` got stuck here: module_loader / fixups / system image are in-progress (o3-mini duplication in the system-image test, leftover `MOV R15, 0xA0` then `0xB0` in that duplicated setup). Port the files as `main` left them. Do not try to finish Blink3 in this series.

### 5. Blink2hw 2x delay vs `main`'s 4x word

blink2-4x changed `Blink2hw` from `MHI R0, 0x8` (`0x60000008`) to `MHI R0, 0x4` (`0x60000004`). `main` still has 0x8. When porting image/asm updates, **keep 0x4**. `tools/gowin_build.sh` greps for `60000004`.

### 6. Failed UART dump

`e920df6` + `387b227` cancel. Skip both; net on `main` is the Logger from `e1fef8c`+`ed9d355`.

## Steps

Cherry-pick where the patch applies cleanly; otherwise port by hand. After **every** step that can affect Verilog, run `tools/run_verilator_sim.sh` and require at least two LED edges and a ~78-cycle steady period (blink2-4x baseline: edges 86, 164, 242, 320, 398, 476).

### Step 0 — Baseline (`main-forward` == `blink2-4x`)

No `main` code yet. Confirm the sim still blinks.

- Result: *(pending)*

### Step 1 — Logger UART (`e1fef8c` + `ed9d355`)

Replace `UartTest` with `Logger`; wire LED stores to `Logger.log`; keep `UartTx`/`UartRx`. Extra CPU IO (`messageCode`, `trigger`, `logByte`) is unused by `CPUSimTop` (simulation has no UART). LED snoop stays 0x10. Blink2 images unchanged.

- Result: *(pending)*

### Step 2 — Docs / cursorrules (`14d7b97` + `073dda5`)

`./build.sh` note, RSC spec, cursorrules RSC pointer. No HDL change; still run sim so the log is uniform.

- Result: *(pending)*

### Step 3 — Skip reverted UART dump (`e920df6` / `387b227`)

Deferred: already backed out on `main`. No files to port.

- Result: skipped (net-zero on `main`)

### Step 4 — Fixups + R12 R13 hack (`1f9d7c9`)

Port `rsc_parser.py` rewrite, enable fixups in `process_mod_files.sh`, switch R13 hack from R0 to R12, update Blink2/Blink3/`AMemoryMappedToggle` images to `LDW R13, [R12, 0x4]`. **Keep Blink2hw `MHI R0, 0x4`.** Hack still returns 0x10, so LED snoop should still fire.

- Result: *(pending)*

### Step 5 — Module loader / image dump (`71f84f1` + `5cb18fe` + `f6719da`)

`tools/module_loader.py`, `image_dump.py`, `mt_table.py`, rsc_parser MT-table fixups, `tests/final_system.code`, `instruction_parser.disassemble_instructions` (address prefix). Blink2test `.code` unchanged except later asm refresh.

- Result: *(pending)*

### Step 6 — Asm listings with addresses (`f9bb7b6`)

Refresh `.asm` files to `0xADDR: 0xWORD    mnemonic`. Keep Blink2hw delay word 0x4.

- Result: *(pending)*

### Step 7 — Custom memory image (`5e8ccb2`)

`CPUSubset0(..., customMemoryImage)` and `CPUTestbenchWrapper` passthrough; system-image test. Default path (Blink2 / CPUSimTop) still builds the 0x00–0xB0 map. May temporarily start PC at 0 for custom images (undone in step 9).

- Result: *(pending)*

### Step 8 — Real MT / vars at 0x50 (`9d190e2`) **LED RISK**

Setup installs R12/MT and variable block at 0x50; drop R13 hack; IMEM halt at 0xB0; memory map doc; tests wait at 0x50.

**Expected without a fix:** Blink2 writes `light` at 0x50, LED snoop at 0x10 sees nothing, sim fails.

### Step 8b — Minimal LED fix (new commit, not on `main`)

Snoop **both** 0x10 and 0x50 for `io.led` (and Logger LedToggle). Restores Blink2 in sim without undoing the 0x50 variable map. Logger still reports the snoop address in the existing printf.

- Result: *(pending)*

### Step 9 — System-image test bugfixes (`0d5f6e2`)

PC always `RegInit(0x80)`; restore `initializeTest` in the system-image test.

- Result: *(pending)*

### Step 10 — gitignore `__pycache__` (`7d47778`)

blink2-4x already has `__pycache__/`. Skip unless a distinct line is missing.

- Result: *(pending)*

## Deferred / open (not blocking Blink2 sim)

| Item | Why deferred |
|---|---|
| UART hex memory dump (`e920df6`) | Explicitly backed out on `main`. |
| BL saves R15 | Missing on a68a501 **and** `main`. Needed for Blink3 `BL` into `AMemoryMappedToggle`, not for Blink2. |
| Bigger default IMEM | Blink2 fits in 0x80. Linked image uses `customMemoryImage` at 0x1000+. |
| Finish Blink3 multi-module link | `main` left this stuck (loader/fixups/system-image test still rough). Port as-is. |
| Dual LED snoop long-term | 0x10+0x50 is a sim/hardware compatibility shim. Bee can later pick a single MMIO address. |

## Sim log

| Step | Commit(s) on `main-forward` | LED edges | Mean period | Notes |
|---|---|---|---|---|
| 0 baseline | *(pending)* | | | |
