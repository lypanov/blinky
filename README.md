# Blinky — Project Oberon RISC5 subset (Tang Nano 4K)

Chisel 6.6 / Mill 0.12.5 CPU. **Not RISC-V.** ISA: [`docs/risc_5_arch.txt`](docs/risc_5_arch.txt). Memory map: [`docs/memory_map.txt`](docs/memory_map.txt).

Commit `a68a501` is the last known-good-on-hardware snapshot: Oberon `Blink2hw` plus UART. `main` through PR #16 is Blink3 on the **Tang Nano 4K**. This branch SRAM-loads the same Blink3 image on the **Tang Primer 20K Dock** (never flash; do not touch the Nano 4K — it stays on the Pi). LED MMIO snoops stores to `0x10` or `0x50`.

## Tang Primer 20K Dock

SRAM-only. Detected on Bee as **Dock** (`usb-SIPEED_JTAG_Debugger_FactoryAIOT_Pro`, `openFPGALoader --detect` → GW2A-18C). Not Lite — do not use Lite-bottom constraints (they clash with Dock UART on T13).

Blink3 (same linked image as the 4K) on user LED **L14**, 27 MHz **H11**:

```sh
BOARD=primer20k tools/gowin_build.sh                          # N=262144
tools/sram_load.sh -b tangprimer20k gowin/primer20k/impl/pnr/blink3_n262144.fs
BOARD=primer20k BLINK3_MAXITER=131072 tools/gowin_build.sh    # then load blink3_n131072.fs
```

`.fs` bitstreams are gitignored (~1.7 MB). Predicted blink rate is `15N+18` cycles at 27 MHz: **3.433 Hz** at N=262144, **6.866 Hz** at N=131072. Measurements: [`docs/blink-measure/blink3-primer20k/`](docs/blink-measure/blink3-primer20k/).

Also: pinout, wiki 1 Hz / 2 Hz blinky, NESTang v0.4 UART ROM load.

- Pins, HDMI pairs, BL702 UART, SRAM rule: [`docs/primer20k/board-notes.md`](docs/primer20k/board-notes.md)
- NESTang build, UART loader, nestest / Alter Ego stills: [`docs/primer20k/nestang.md`](docs/primer20k/nestang.md)
- Wiki blinky measurements: [`docs/blink-measure/primer20k/`](docs/blink-measure/primer20k/)

Load bitstreams with `tools/sram_load.sh` (`openFPGALoader -b tangprimer20k -m`).
Do not pass `-f`.

## Verilator simulation (Phase 1)

Needs: JDK 11+, Mill 0.12.x on `PATH`, Verilator 5.x, Python 3 with `matplotlib` (for the PNG), optional GTKWave.

```sh
# from the repo root
tools/run_verilator_sim.sh
# equivalent:
make -C sim sim
```

What you get:

| artifact | path |
|---|---|
| FST waveform (GTKWave) | `sim/out/blink2.fst` |
| LED edge log | `sim/out/led_toggles.csv` |
| timing-diagram PNG | `sim/out/led_waveform.png` |
| cycle trace | `sim/out/blink2_trace.json` |

Open the waveform:

```sh
gtkwave -S sim/gtkwave_led.tcl sim/out/blink2.fst sim/gtkwave_led.gtkw
```

The sim prints `[LED] cycle=…` lines and a mean period. After the `main` MT/0x50 map, Verilator measures a **steady 84-cycle** LED period (edges at 98, 182, 266, …). That is the old 78-cycle loop plus six extra memory-wait cycles now that `LDW R13, [R12, 0x4]` is a real load instead of the R13 hack. Hardware `Blink2hw` uses `maxIterations := 262144` and is not the sim default.

Sim-only delay: set `BLINK2_CODE` if you want a different image (the hardware image is a long delay loop and is not the default):

```sh
BLINK2_CODE=tests/Blink2test.code mill chisel-blinky.runMain gcd.CPUSimTop
make -C sim run CYCLES=800 TOGGLES=6
```

FPGA bitstream for the Tang Nano 4K is Blink3 (linked `LightToggle` + `AMemoryMappedToggle`, trampoline at address 0 that `BL`s each BEGIN). SRAM only:

```sh
tools/gowin_build.sh                          # N=262144
tools/sram_load.sh -b tangnano4k gowin/impl/pnr/blink3_n262144.fs
BLINK3_MAXITER=131072 tools/gowin_build.sh    # N=131072, then load blink3_n131072.fs
tools/measure_blink.sh
```

`FPGA_IMAGE=blink2 tools/gowin_build.sh` still emits the old Blink2hw small IMEM. `BOARD=primer20k` builds the same CPU for the Dock (GW2A-18C). Do not pass `-f` / flash. Do not load the Nano 4K from Bee (it is on the Pi). Sim says an LED edge is `15N+18` cycles at 27 MHz (upper bound if SPRAM wait-states apply). 4K measurements: [`docs/blink-measure/blink3/`](docs/blink-measure/blink3/).

## Oberon compiler (Norebo)

Blink2 / Blink3 `.Mod` files are compiled with Wirth's Project Oberon 2013 `ORP` via [project-norebo](https://github.com/pdewacht/project-norebo), pinned in `tools/norebo.pin`.

```sh
tools/setup_norebo.sh              # clone pin, run upstream ./build.sh
python3 tools/verify_raw_oberon_code.py   # raw code vs historical unfixed dumps
tools/process_mod_files.sh         # compile tests/*.Mod; writes tests/raw/ *before* fixup
```

The clone lands in `tools/project-norebo/` (gitignored). After the monorepo layout (PR #7) keep the pin and scripts in `tools/` and point them at `core/tests/`. `.rsc` object files are gitignored; the bit-for-bit check uses tiny hex dumps in `tests/fixtures/unfixed/`, not binary `.rsc` files.

## Visualizer (Phase 2)

Local web page (Python 3 stdlib HTTP server). Blink2 and Blink3 buttons load
**real Verilator traces**. The Python loader relocates Blink3's `BL` at
`0x108C` to Toggle (`0x1000`). `BL` writes `R15 = PC + 4`, so Toggle returns
into LightToggle's loop. A sim-only trampoline at address 0 uses `BL` (not
planted `MOV R15`) to call `AMemoryMappedToggle` BEGIN (`0x1028`) then
LightToggle — a static stand-in for `Modules.Load`'s `body` calls. Stepping
is one **instruction** (PC change), not one clock. `I` jumps to BEGIN, `L`
to `light := 0`, `F` to the `BL`.

On Bee (this Linux PC):

```sh
tools/run_visualizer.sh          # binds 127.0.0.1:8765 only
# regenerate traces after CPU/loader/sim changes:
make -C sim traces
```

On Alex's Mac, leave that running on Bee and forward the port. Nothing is
exposed to the internet:

```sh
ssh -N -L 8765:127.0.0.1:8765 bee
open http://127.0.0.1:8765/                 # Blink2
open http://127.0.0.1:8765/?p=blink3        # Blink3
open http://127.0.0.1:8765/?p=blink3n5      # Blink3 with maxIterations = 5 (LED period 93)
open http://127.0.0.1:8765/?p=blink3&delay  # maxIterations := 262144 (MHI / dmem[0x74])
open http://127.0.0.1:8765/?p=blink3&init   # AMMT BEGIN at 0x1028
open http://127.0.0.1:8765/?p=blink3&light  # STW light := 0 at 0x1038
```

Same Wi-Fi as Bee, still not the internet: `tools/run_visualizer.sh --bind 0.0.0.0`
then `http://<bee-lan-ip>:8765/`.

Keyboard: Space run/pause, `S` / `→` next instruction, `A` / `←` previous, `R`
reset, `I` AMMT BEGIN, `L` light:=0, `D` delay 262144, `F` jump to BL Toggle if present,
`2` / `3` / `5` switch program (`5` is Blink3 with N=5), `[` / `]` speed.

Bee can run Blink3 and the NESTang Alter Ego sim side by side. Commands, the N=5 waveform, and the Alter Ego frames are in [`docs/sim-bee/README.md`](docs/sim-bee/README.md). Both commands stay in Verilator. NESTang stays in `~/fpga/nestang`.

A UART press byte forces the LED pin off without stalling the CPU. Verilator proof: [`docs/uart-led-gate/README.md`](docs/uart-led-gate/README.md).

---

Chisel Project Template
=======================

You've done the [Chisel Bootcamp](https://github.com/freechipsproject/chisel-bootcamp), and now you
are ready to start your own Chisel project.  The following procedure should get you started
with a clean running [Chisel3](https://www.chisel-lang.org/) project.

## Make your own Chisel3 project

### Dependencies

#### JDK 11 or newer

We recommend using Java 11 or later LTS releases. While Chisel itself works with Java 8, our preferred build tool Mill requires Java 11. You can install the JDK as your operating system recommends, or use the prebuilt binaries from [Adoptium](https://adoptium.net/) (formerly AdoptOpenJDK).

#### SBT or mill

SBT is the most common build tool in the Scala community. You can download it [here](https://www.scala-sbt.org/download.html).  
mill is another Scala/Java build tool without obscure DSL like SBT. You can download it [here](https://github.com/com-lihaoyi/mill/releases)

#### Verilator

The test with `svsim` needs Verilator installed.
See Verilator installation instructions [here](https://verilator.org/guide/latest/install.html).

### How to get started

#### Create a repository from the template

This repository is a Github template. You can create your own repository from it by clicking the green `Use this template` in the top right.
Please leave `Include all branches` **unchecked**; checking it will pollute the history of your new repository.
For more information, see ["Creating a repository from a template"](https://docs.github.com/en/free-pro-team@latest/github/creating-cloning-and-archiving-repositories/creating-a-repository-from-a-template).

#### Wait for the template cleanup workflow to complete

After using the template to create your own blank project, please wait a minute or two for the `Template cleanup` workflow to run which will removes some template-specific stuff from the repository (like the LICENSE).
Refresh the repository page in your browser until you see a 2nd commit by `actions-user` titled `Template cleanup`.


#### Clone your repository

Once you have created a repository from this template and the `Template cleanup` workflow has completed, you can click the green button to get a link for cloning your repository.
Note that it is easiest to push to a repository if you set up SSH with Github, please see the [related documentation](https://docs.github.com/en/free-pro-team@latest/github/authenticating-to-github/connecting-to-github-with-ssh). SSH is required for pushing to a Github repository when using two-factor authentication.

```sh
git clone git@github.com:lypanov/chisel-blinky.git
cd chisel-blinky
```

#### Set project organization and name in build.sbt

The cleanup workflow will have attempted to provide sensible defaults for `ThisBuild / organization` and `name` in the `build.sbt`.
Feel free to use your text editor of choice to change them as you see fit.

#### Clean up the README.md file

Again, use you editor of choice to make the README specific to your project.

#### Add a LICENSE file

It is important to have a LICENSE for open source (or closed source) code.
This template repository has the Unlicense in order to allow users to add any license they want to derivative code.
The Unlicense is stripped when creating a repository from this template so that users do not accidentally unlicense their own work.

For more information about a license, check out the [Github Docs](https://docs.github.com/en/free-pro-team@latest/github/building-a-strong-community/adding-a-license-to-a-repository).

#### Commit your changes
```sh
git commit -m 'Starting chisel-blinky'
git push origin main
```

### Did it work?

You should now have a working Chisel3 project.

You can run the included test with:
```sh
sbt test
```

Alternatively, if you use Mill:
```sh
mill chisel-blinky.test
```

You should see a whole bunch of output that ends with something like the following lines
```
[info] Tests: succeeded 1, failed 0, canceled 0, ignored 0, pending 0
[info] All tests passed.
[success] Total time: 5 s, completed Dec 16, 2020 12:18:44 PM
```
If you see the above then...

### It worked!

You are ready to go. We have a few recommended practices and things to do.

* Use packages and following conventions for [structure](https://www.scala-sbt.org/1.x/docs/Directories.html) and [naming](http://docs.scala-lang.org/style/naming-conventions.html)
* Package names should be clearly reflected in the testing hierarchy
* Build tests for all your work
* Read more about testing in SBT in the [SBT docs](https://www.scala-sbt.org/1.x/docs/Testing.html)
* This template includes a [test dependency](https://www.scala-sbt.org/1.x/docs/Library-Dependencies.html#Per-configuration+dependencies) on [ScalaTest](https://www.scalatest.org/). This, coupled with `svsim` (included with Chisel) and `verilator`, are a starting point for testing Chisel generators.
  * You can remove this dependency in the build.sbt file if you want to
* Change the name of your project in the build.sbt file
* Change your README.md

## Problems? Questions?

Check out the [Chisel Users Community](https://www.chisel-lang.org/community.html) page for links to get in contact!
