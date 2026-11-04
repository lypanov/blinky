# Tang Nano 4K SRAM load and UART attempt

SRAM only, on the Nano 4K. The Primer 20K was not programmed and its tty was not opened. The 4K was left running this bitstream (Blink3 N=262144, latch clear, LED blinking).

## How a byte would have to travel

| hop | what |
|---|---|
| USB device | bus **3**, device **81**, `0403:6010`, product "SIPEED JTAG Debugger", serial "FactoryAIOT Pro". This is the Nano 4K's onboard BL702, which enumerates as an FT2232. The other debugger (bus 3 device **78**, USB path `3-3.3`) is the Primer 20K and was not opened. |
| JTAG (channel A) | USB interface **0**, sysfs `3-3.1.1:1.0`, tty `/dev/ttyUSB2` when `ftdi_sio` is bound. `openFPGALoader` uses this channel. |
| UART (channel B) | USB interface **1**, sysfs `3-3.1.1:1.1`, tty **`/dev/ttyUSB3`**. Confirmed with `udevadm` (`ID_USB_INTERFACE_NUM=01`, `ID_PATH=pci-0000:00:14.0-usb-0:3.1.1:1.1`). Not `/dev/ttyUSB0` or `/dev/ttyUSB1` (those are `3-3.3`, the 20K). |
| line | 115200 baud, 8 data bits, no parity, 1 stop bit. DTR and RTS cleared before any write, so opening the port does not pulse modem lines. |
| bytes | `0x01` press (force the pin off), `0x00` release. Same bytes the gate accepts, along with ASCII `1` / space and ASCII `0`. |
| FPGA pins in the bitstream | `tang-nano-4k.cst`: RX package pin **18** (`IOB13[A]`, LVCMOS18, pull-up), TX package pin **19** (`IOB13[B]`). LED is pin 10. |

IDCODE read on bus 3 device 81 before the load: `0x100981b`, Gowin GW1NSR-4C.

`libftdi` `usb_reset` returns -6 while channel B's `ftdi_sio` driver is attached. Both interfaces of **this** device were detached in userspace, then:

```sh
openFPGALoader --busdev-num 003:081 -b tangnano4k -m gowin/impl/pnr/blink3_n262144.fs
```

Log: `write to ram`, `Load SRAM 100%`, `CRC check: Success`. No `-f`. Channel B was reattached afterwards so `/dev/ttyUSB3` came back. The 20K interfaces stayed on `ftdi_sio` the whole time.

## What the schematic says

Sipeed `Tang_Nano_4K_3603` ([PDF](https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf)):

- Package pins 18 and 19 are `PIXDATA5` / `PIXDATA3` on the camera connector, not a UART.
- The BL702 page wires GPIO0/1/2/15 to JTAG and GPIO17 to the debugger LED. GPIO23–GPIO28, the usual UART pins on this chip, have no nets.

![BL702 page of Tang Nano 4K schematic 3603](hardware/tang-nano-4k-bl702-schematic.png)

So the tty is real, and the bytes left the machine, but the board does not connect that UART to the FPGA pins this bitstream listens on.

## Webcam

Tool: `check_all(duration=10)` at `http://127.0.0.1:8766/mcp`. Each call records about 10 s and returns both boards. Predicted Blink3 rate is **3.433 Hz**. The 20K stayed near 6.65 Hz on every call.

| step | Nano 4K | Primer 20K |
|---|---|---|
| before SRAM load | 0.968 Hz blinking | 6.647 Hz blinking |
| after SRAM load, before any byte | **3.329 Hz** blinking | 6.648 Hz blinking |
| `0x01` then 10 s (try 1) | 3.326 Hz blinking | 6.653 Hz blinking |
| `0x00` then 10 s | 3.326 Hz blinking | 6.651 Hz blinking |
| `0x01` then 10 s (try 2) | 3.328 Hz blinking | 6.633 Hz blinking |
| `0x00` then 10 s | 3.319 Hz blinking | 6.641 Hz blinking |
| `0x01` then 10 s (try 3) | 3.328 Hz blinking | 6.656 Hz blinking |
| `0x00` then 10 s | 3.316 Hz blinking | 6.655 Hz blinking |

A 1.2 s read of `/dev/ttyUSB3` while the LED was toggling returned **0 bytes**. The logger in the bitstream sends a line on every LED store, so a connected TX pin would not have been silent.

The press windows were the failure: the pin was supposed to go dark for those 10 s. It kept the Blink3 rate. The MCP reported a real blink each time (edge and FFT agree, confidence 1.0). That is the board, not an MCP miss.

![Before load, 4K at 0.97 Hz](hardware/01-preload-annotated.jpg)

![After SRAM load, 4K at 3.33 Hz](hardware/02-blink3-annotated.jpg)

![4K trace after load](hardware/02-blink3-nano4k.png)

![During the first 0x01, 4K still at 3.33 Hz](hardware/03-press1-annotated.jpg)

![4K trace during the first press byte](hardware/03-press1-nano4k.png)

Clips (not committed, ~3.5 MB each) are under `~/fpga/blink-measure/20261104-213949-check` through `20261104-214232-check`.

The 4K is still running this SRAM image. The last byte on the wire was `0x00`. The LED was blinking at 3.316 Hz at the end of that measurement.
