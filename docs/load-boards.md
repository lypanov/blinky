# Loading the boards

SRAM only (`openFPGALoader -m`). Never flash. Resolve the USB device from the
**port**, not from a remembered `003:0xx` address; that number moves.

Both boards are usually plugged in. `tools/sram_load.sh` does not pass
`--busdev-num`, so it can program the wrong FPGA. Use `tools/load_dock.py`
for the Dock.

## Primer 20K Dock (DDR3)

USB port `3-3.1.1`. The Nano 4K is `3-3.3`; do not open it.

```sh
tools/load_dock.py <bitstream.fs> <disk.bin>
```

Defaults are `--tries 16`, `--wait-s 12`, `--armed-s 40`. You do not need to
pass them. The write eye fails on some SRAM loads; sixteen tries is the
usual room to see a `C.0440` wait.

That is the whole load. It:

1. Reads bus and address from `/sys/bus/usb/devices/3-3.1.1/`.
2. Binds FTDI channel B with `sudo -n /usr/local/sbin/blinky-bind-dock-uart`.
   That helper is passwordless. `sudo -n true` is not, and is the wrong check.
3. SRAM-loads the Dock only (`--busdev-num`, `-m`, board `tangprimer20k`).
4. Listens on UART B at 115200 without an FTDI reset (a reset drops DDR3).
5. Sends the disk only on a wait line: `C.0440`, mask `0000000000`, `G A55A`.
6. Waits until the mask is `FFFFFFFFFF`.

A load that sits at `..0080` with `F 4B` did not train. It is not a UART bug.
Reload; do not send. A line that trains (`C.`) but has already left `0440`
(`04B8`, `00F4`, and the like) took a start bit during configure. Reload; do
not send. `G FF5A` or `G 855A` on the wait can take bytes and still never arm.
Reload. The script retries those cases; it does not sit out the full listen.

Do not write a second sender. The UART open is `tools/send_dock_disk.py`.
Do not send until a line starts with `C.`. Bind **before** the SRAM load so
the kernel driver can set TX; RX status lines without a bind do not mean TX
works.

After a 0 exit, the LED is the pass. Webcam `/dev/video2`. The capture card
is `/dev/video0`, YUYV 1024×768 at 60 Hz, only after the arm word. A locked
grey field with luma about 139 and U=V=128 is “not armed”, not a dead cable.

## Tang Nano 4K (HyperRAM)

Not in the script yet. The Dock path was proven first. The 4K uses the same
SRAM-only rule on port `3-3.3`, then a NOR disk at `0x200000`, and it must
not touch the Dock. Item 45 on the 4K is unconfirmed here.
