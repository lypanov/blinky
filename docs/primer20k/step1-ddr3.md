# Step 1: DDR3 data port on the Tang Primer 20K Dock

## Proven: 64-word command port

The bitstream with `` `define DDR3_PORT_TEST `` in `blinky_top_ddr3.v` is the one that ran. It writes 64 halfwords (`addr ^ 16'hA5A5`), refreshes between words, then reads them back. L14 blinks only if every word matches one sample edge. The locked rate, from the PLL before the load, is

`pclk / 2^27 = 96750000 / 134217728 = 0.720844 Hz`

A13 blinks from the 27 MHz pin for the whole run, at `27000000 / 134217728 = 0.201166 Hz`, so a configured FPGA is visible when the compare fails. C13 stays dark.

SRAM load was `openFPGALoader --busdev-num 003:078 -b tangprimer20k -m` (idcode `0x81b`, GW2A-18). The Nano 4K at `003:081` was detected and not loaded (idcode `0x100981b`, GW1NSR-4C). Place-and-route reported 0 setup and 0 hold endpoints on every clock.

UART on M11, the Dock's FT2232 channel B, at 115200 (`pclk/840`):

```
B
C
P 003F 0000 0000 0000 0 0
```

`B` is PLL lock, `C` is `read_calib_done`, `P` is a pass. `003F` is the last word address. The three sample fields stay 0 on a pass; they are latched only when a compare fails. The next digit is the locked edge, `0`, meaning `dout` matched on the `data_ready` cycle and every later word matched that same cycle. The last digit is the attempt, `0`. Calibration finished, and the first attempt passed. The controller reset retry did not run.

The webcam tool's headline is not this rate. On the clip taken after that UART line (`blink-measure/20261105-055225-mcp`, `measure_blink` `roi=primer20k` `duration=20` `warmup=2`) it reported `status=blinking 0.75 Hz`, `edge=0.541`, `fft=0.75`, confidence 0.78, because the pass LED and the 0.201 Hz marker sit a few pixels apart and the detector mixed them. The raw frames do not. At 30.0 fps (the Nano 4K LED in the same clip is 60.1 frames, 0.499 Hz):

| LED | frame deltas | mean frames | measured Hz | predicted frames |
|---|---|---:|---:|---:|
| L14 pass | 41, 42, 41, 42, 42, … | 41.600 | 0.721154 | 41.618 |
| L14, second core | 42, 42, 41, 42, 42, … | 41.667 | 0.720000 | 41.618 |
| A13 alive | 149, 149, 150, 149 | 149.250 | 0.201005 | 149.131 |

Fifteen pass intervals span 624 frames. Fifteen times 41.618 is 624.3. The error is a fraction of one camera frame, and the duty is a square wave. An earlier clip of the same bitstream (`20261105-055015-mcp`), before the UART reload, measured the same pass LED at 41.643 frames (0.720412 Hz) over 583 frames against a prediction of 582.7.

The behavioural model passes on edge 0, fails closed when reads return 0 (`+ddr3_corrupt`), and passes on edge 1 when `dout` is one clock behind `data_ready` (`+ddr3_late`). Hardware locked edge 0, so the miss on the earlier image was not "sample one clock late."

That earlier 64-word image sampled `dout` on `data_ready` as well, waited only until `busy` fell, and used `RCALIB_COUNT` 8. It left L14 dark. `busy` falls at `tRC` (20 nCK, about 52 ns). A 1 Gbit DDR3 needs `tRFC` of 110 ns after a refresh, and the write's auto-precharge is not finished when `busy` falls either. The passing image waits 16 controller clocks (165 ns) after `busy` before the next command, and it commits read calibration after 16 matching bursts, which is what NESTang uses on this Dock. Both changes are in the image that passed. The one-cycle-late sample and the init retry are not: edge 0 matched on attempt 0.

The pins are not the difference. The placer puts the DDR balls on banks 4, 5, and 6, all `SSTL15` / `BANK_VCCIO=1.5`, the same balls as `nestang-v04` `nestang_dock.cst` including `nCS` at P5. The documented 1.5 V keys land on those banks (T2–T5 on bank 4, C7/D7/E8/E9 on bank 6). Byte 0, DQS0, and CK are on bank 5. Gowin's DDR3 IP was not swapped in. Its manual treats `tRFC` as its own REFRESH-to-ACTIVE parameter, separate from `tRC`, which is the gap this controller was not waiting.

The CPU prologue path is still in the source, under the `` `else `` of `DDR3_PORT_TEST`. It has not blinked at 1.178879 Hz. A diagnostic load reached the failure hold at one PC change per `cpu_clk` (2.885 Hz on the PC divider), so that path completed memory operations with bad data. It is not this proof.

## Design

Fetch stays in block RAM. Data loads and stores go through the DDR3
controller when the image is `ddr3`. `FPGA_IMAGE=blink3` is still the
block-RAM Blink3. The HyperRAM images (`hyperram`, `fixup`, `rsc`,
`fetchbl`, `pdchain`, `moddesc`, `files`, `modules`) still elaborate
against the Nano 4K HyperRAM port. None of those bitstreams was rebuilt
for this step, and the Nano 4K was not reloaded.

The Dock has no HyperRAM. The memory is the onboard SK Hynix
H5TQ1G63EFR-PBC (1 Gbit, x16, 13 row, 10 column, 8 banks). `A[13]` is
wired on the Dock and tied to 0 in the top, because this chip does not
use it. The controller is nand2mario's `ddr3_controller.v` from
<https://github.com/nand2mario/ddr3-tang-primer-20k>, Apache-2.0, vendored
under `gowin/primer20k/ddr3/`. `RCALIB_COUNT` is 16, matching the
NESTang Dock copy; the rest of the PHY is that file. The same controller
already initialized this chip. Gowin's encrypted DDR3 IP was not generated.

The program is the HyperRAM step-1 prologue (`sim/build_hyperram_imem.py`).
No `.Mod` file and no `oberon/src` file was edited. The only change to the
Blink3 words, and only in this image's copy, is the setup `MOV` at `0x9C`:
`0x40000000` becomes `0x40001200`, so reset goes to the prologue. On a
match the prologue branches to address 0, which is still Blink3's
trampoline. On a mismatch it sits in the hold at `0x1390` / `0x1394` and
never stores the LED.

## What a match has to get right

The prologue writes `1<<0 .. 1<<31` at `0x400+4*i` and the two's-complement
inverse at `0x500+4*i`. It then writes `0x11111111` at `0x114` and, last,
`0xA5A5A5A5` at `0x7F0`.

It reads every pattern word, then every complement, and folds each series
with XOR and with ADD. The expected constants are immediates, not values
computed while writing:

| check | expected |
|---|---|
| pattern XOR | `0xFFFFFFFF` |
| pattern sum | `0xFFFFFFFF` |
| complement XOR | `0xFFFFFFFF` |
| complement sum | `0xFFFFFFE1` |
| load `0x14` (MT[1]) | `0x50` |
| load `0x18` (MT[2]) | `0x70` |
| load `0x114` | `0x11111111` |
| load `0x7F0` | `0xA5A5A5A5` |

Each compare stores `(got - expected)` at `0x7C0` through `0x7DC`. `R10` is
the OR of those eight differences. A non-zero `R10` branches to the hold.

The DDR3 elaboration gates the pin the same way the HyperRAM elaboration
does. A store of zero to `0x7C0+4*slot` sets one bit of an 8-bit mask.
`io.led` is the Blink3 LED state AND that mask equal to `0xFF`. There is
no extra check bit. The block-RAM elaboration does not contain this gate.

A CPU word is two little-endian 16-bit DDR words. The bridge samples
`dout` on the controller's `data_ready` pulse. A byte store, which this
prologue does not use, is a read-modify-write of the containing half so
the other byte survives.

Refresh is the bridge's job. This part needs a refresh every 7.8125 µs
(8192 refreshes in 64 ms). At the 96.75 MHz controller clock that is 756
clocks. A due refresh runs before the next CPU command and never between
the two halves of one word. A CPU request is only high for one cycle, so
a request that arrives during a refresh is latched and run after it. The
counter does not start until read calibration has finished, and the CPU
is held in reset until then. If calibration never finishes the blinking
LED stays dark. That CPU image is not the bitstream measured above.

## Why a wrong result cannot blink at this rate

- A zero RAM, an all-ones RAM, or "return the last write" misses at least
  one compare. The eight zero-difference stores are what arm the pin.
- The one remaining software hole is a `SUB` that returns 0 for unequal
  operands. That would arm the pin and also collapse the delay compare, so
  the LED would toggle every iteration, near 55 kHz, not at the rate below.
- `+ddr3_corrupt` makes the behavioural model return 0 on every read, with
  the same `data_ready` timing. On the netlist that will be synthesized,
  20000 `pclk` cycles after reset: 0 LED edges, the Blink3 body at
  `0x1048` was visited 0 times, the success branch at `0x138c` was visited
  0 times, and the CPU sat in the hold (`0x1390` for 6790 cycles, `0x1394`
  for 6788). The last `R0` was `0xFFFFFFFF`. No `DDR3_RANGE_FAULT`.

## Clock

`pclk` is the PLL's `CLKOUTD`:

- input 27 MHz, `IDIV_SEL=2`, `FBDIV_SEL=42`, so `CLKOUT = 27*43/3 = 387 MHz`
- `DYN_SDIV_SEL=4`, so `pclk = 387/4 = 96.75 MHz`
- `CLKOUTP` is that 387 MHz shifted 90 degrees and drives `DDR3_CK`

These dividers already initialized this chip. The controller and the
bridge stay on `pclk`. The controller's command timing is counted in that
clock, and its stated range is 75–100 MHz, so the PHY is not divided.

A first place-and-route put the CPU on `pclk` as well. Setup TNS was
-2697.591 ns over 1077 endpoints, worst slack -5.135 ns, `pclk` fmax
64.636 MHz. Hold TNS was 0. The DDR PHY paths were positive. That
bitstream was not loaded.

The CPU runs on `cpu_clk = pclk/4` (24.1875 MHz), from a Gowin `CLKDIV`
with `DIV_MODE="4"`. The divider starts when the PLL locks. CPU reset is
released on `cpu_clk` only after `read_calib_done`, so the CPU clocks the
reset in. The bridge stays in reset for the same interval and does not
issue commands before calibration. The SDC constrains the 27 MHz port at
37.037 ns, `pclk` at 10.336 ns, and `cpu_clk` as a divide-by-4 of `pclk`.
Hold between the two clocks is a multicycle of 1. A CPU output is sampled
on the next `pclk`. A bridge output is allowed 20.672 ns (two `pclk`) to
reach the CPU. Stall rises on the `pclk` after the request, and the next
CPU edge is three `pclk` after that, so two `pclk` still arrives in time.

Two `pclk/2` place-and-route runs were not loaded. With the store data
still combinational, the tool reported 67 setup-violated endpoints, worst
slack -2.738 ns (13.004 ns of data delay against 10.336 ns). After that
path was registered on `cpu_clk`, five endpoints remained, all from the
bridge state bit into the CPU, worst slack -0.821 ns (11.087 ns against
10.336 ns). Hold violations were 0 in both. The per-clock TNS summary
printed 0.000 because the failing paths cross between `cpu_clk` and
`pclk`. The address, the write data, and the read/write/byte strobes stay
registered on `cpu_clk`. After a word completes, `memStall` stays low for
four `pclk` with the data held. The CPU samples every four `pclk`, and a
one-cycle low can fall in the gap.

## Simulation (before the stall-hold synthesis)

`sim/Ddr3UserModel.v` is the command port only. It does not simulate
DQS, the DLL, or write leveling. Calibration rises after 64 clocks. A
read presents `dout` with `data_ready` on the clock where the controller's
cycle counter is 8, and drops `busy` on the next clock. A write or a
refresh drops `busy` when that counter is 5. The array is 4096 x 16-bit
words. The prologue stays inside it. `sim/CpuClock.v` divides the
testbench clock the way `CLKDIV` does, and the CPU is the only thing on
that clock. Periods below are in `pclk` cycles.

N=5, good model. The eight difference stores were all 0. Each store is
visible for the four `pclk` cycles of one CPU cycle, and every sample was
0. Edges, at the Blink3 store `pc=0x101c`:

| edge cycle | period |
|---:|---:|
| 7518 | |
| 8506 | 988 |
| 9494 | 988 |
| 10474 | 980 |

Further samples, still `pclk` cycles per edge:

| N | measured cycles/edge |
|---:|---|
| 32 | 5220, 5196, 5224 |
| 128 | 20276, 20172, 20280 |
| 512 | 80484, 80076, 80488 |

Least squares over those 12 periods:

`cycles/edge(N) = 156.534393*N + 204.221`

The refresh phase walks by about half a percent. N=512 spans 80076 to
80488. The line is the center of that walk.

## Prediction, locked before the stall-hold synthesis

N = 262144. The controller clock is `pclk`, 96,750,000 Hz. The CPU clock
is a quarter of that. The cycle counts are `pclk` cycles.

- cycles per edge = `156.534393*262144 + 204.221` = **41,034,756**
- edge rate = 96,750,000 / 41,034,756 = **2.357757 Hz**
- full blink (on + off) = **1.178879 Hz**
- full period = **0.848264 s**

The tool's `predicted_blink3_hz` (3.433 Hz) is the block-RAM Blink3 figure.
It is not this prediction. 1.178879 Hz is inside the detector's 0.2–8 Hz
band. It is 136% above the 0.5 Hz the Nano 4K is blinking and 66% below
the 3.433 Hz block-RAM rate. The Dock did not blink at 1.178879 Hz. The
load of this CPU image reached the failure hold, one PC change per
`cpu_clk` (2.885 Hz on the divider). The measured proof is the
command-port blink at the top of this note.

An earlier `pclk/4` bitstream, without the four-cycle stall hold, was
loaded onto the Dock. The upper board's three LEDs stayed steady for the
whole clip and the Nano 4K in the same frame kept blinking at 0.5 Hz.
That bitstream is not this prediction.
