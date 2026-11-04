# UART press gates the Blink3 LED

The gate sits in the SoC, after the CPU's LED register (`UartLedGate` in
`CPUMinimalWrapper` and in the Verilator top). A latched press forces the
pin off. The core keeps fetching, and `ledState` keeps toggling, so a release
shows the phase the register is already in.

This run is Verilator plus synthesis. Neither board was loaded, and no
serial device was opened.

## Protocol

8N1, 115200 baud, 27 MHz (Nano 4K PLL bypass and Primer 20K H11). One bit is
234 cycles. The receiver is the existing `UartRx`.

| byte | latch |
|---|---|
| `0x01`, ASCII `1`, or space `0x20` | pressed, pin forced off |
| `0x00` or ASCII `0` | released, pin follows the CPU register |
| anything else | latch unchanged |

Later a host can send `0x01` on key-down and `0x00` on key-up. That host is
not part of this change.

## Where the pins are

Tang Nano 4K: `tang-nano-4k.cst` places RX on package pin 18 and TX on pin 19.
The onboard BL702 (bus 3 device 81) does expose a USB-UART on its second
interface, but schematic 3603 does not connect that UART to the FPGA, and
pins 18/19 are camera data. The SRAM test is written up in
[`hardware.md`](hardware.md).

Tang Primer 20K Dock: `gowin/primer20k/primer20k.cst` maps FPGA TX to **M11**
and FPGA RX to **T13**, the BL702 USB-UART balls (same as BeebFpga and
NESTang). L14 is still the active-low Blink3 LED, so a forced-off pin
(active-high 0) drives L14 high and the LED stays dark. This Dock build was
not loaded.

## Verilator, N=5

`tools/run_uart_led_gate.sh` uses maxIterations = 5 so an edge is
`15*5+18 = 93` cycles and a 2340-cycle UART frame is easy to see. The FPGA
image is still N=262144.

Press frame starts at cycle 500 and the latch sets at cycle **2725**, while
the CPU register is still 1 (it rose at 2715 and would have stayed 1 until
2808). The pin drops at 2725 and stays 0 for the whole latch. Release frame
starts at cycle 4200; the latch clears at cycle **6425** with both the pin
and the register already 0. The next edge of both is cycle **6435**, one
93-cycle step after the CPU edge at 6342 that happened while the pin was held
off.

| | |
|---|---|
| CPU edge period | 93, every gap, including the 39 edges inside the press |
| press latch | cycle 2725 through 6424 (3700 cycles) |
| pin while pressed | 0 |
| release | cycle 6425, pin = CPU LED = 0 |
| next shared edge | 6435 |

![Pin forced off while the CPU register keeps blinking](uart_gate_n5.png)

```sh
tools/run_uart_led_gate.sh
PORT=8768 tools/run_visualizer.sh
# pin forced off, CPU LED still on:
#   http://127.0.0.1:8768/?p=uartgate&gate=off
# pin high again, in phase with the register:
#   http://127.0.0.1:8768/?p=uartgate&gate=on
```

![Visualizer at the cut: pin forced off, CPU LED on](uart_vis_pressed.png)

![Visualizer after release: pin follows the CPU LED](uart_vis_released.png)

## Synthesis

Both builds finished syn+PNR and wrote an SRAM-loadable `.fs`. Nothing was
programmed.

| board | part | UART pins from the pin report | bitstream |
|---|---|---|---|
| Tang Nano 4K | GW1NSR-4C | RX pin 18 (`IOB13[A]`), TX pin 19 (`IOB13[B]`), LED pin 10 | `gowin/impl/pnr/blink3_n262144.fs` |
| Primer 20K Dock | GW2A-18C | RX **T13**, TX **M11**, both LVCMOS33 | `gowin/primer20k/impl/pnr/blink3_n262144.fs` |

```sh
tools/gowin_build.sh
BOARD=primer20k tools/gowin_build.sh
```

The `.fs` files are gitignored. Do not pass `-f`.

The Nano 4K bitstream above was SRAM-loaded on bus 3 device 81
(`openFPGALoader --busdev-num 003:081 -b tangnano4k -m`, no `-f`). The
Primer 20K was not loaded. Webcam `check_all(duration=10)` moved the 4K
from 0.968 Hz to 3.329 Hz (Blink3 is 3.433 Hz). Three `0x01` / `0x00`
cycles on `/dev/ttyUSB3` (interface 1 of that same BL702, 115200 8N1)
left the 4K at 3.32 Hz the whole time. Path, schematic, and stills:
[`hardware.md`](hardware.md). The 4K was left running this image.
