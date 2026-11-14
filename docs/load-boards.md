# Loading the boards

SRAM only (`openFPGALoader -m`). Never flash. Resolve the USB device from the
**port**, not from a remembered `003:0xx` address; that number moves.

Both boards are usually plugged in. `tools/sram_load.sh` does not pass
`--busdev-num`, and its default board is `tangprimer20k`, so it can program
the wrong FPGA. Use `tools/load_dock.py` for the Dock and
`tools/load_nano.py` for the Nano.

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

After a 0 exit, the LED is the pass. Webcam `/dev/video2`, `--roi primer20k`.
The capture card is `/dev/video0`, YUYV **1024×768** at 60 Hz, only after the
arm word. A 20×20 square at x 300..319, y 220..239 is 400 white pixels. A
locked grey field with luma about 139 and U=V=128 is “not armed”, not a dead
cable. Sixteen tries is not always enough; a miss is `F 4B` or a left-wait,
not a script bug — run it again.

## Tang Nano 4K (HyperRAM)

USB port `3-3.3`. The Dock is `3-3.1.1`; do not open it.

```sh
tools/load_nano.py <bitstream.fs> <disk.bin>
```

The NOR write plus read-back is minutes. openFPGALoader prints percent; the
script streams that. If the disk is already on the chip:

```sh
tools/load_nano.py --sram-only <bitstream.fs>
```

That is the whole load. It:

1. Reads bus and address from `/sys/bus/usb/devices/3-3.3/`.
2. Checks the disk header (`DSK1` / `0x314B5344`, version 1, length, checksum).
   The build word is logged, not pinned; it moves between to-do items.
3. Writes only that data file to the external NOR at `0x200000`
   (`-f --external-flash -o 0x200000 --verify`). This is the one flash
   exception. Never a `.fs`, never below `0x200000`, never the Dock.
4. Reads the file back and compares. The 256 bytes at `0x1FFF00` must match
   the dump taken before the write.
5. SRAM-loads the Nano only (`--busdev-num`, `-m`, board `tangnano4k`).

The 4K has no UART disk. Do not bind or reset its FTDI. Leave `ftdi_sio`
attached; a USB reset drops VBUS. Write the NOR first, then SRAM-load, so
the new bitstream boots the new disk.

After a 0 exit, the LED is the pass. Webcam `/dev/video2`, `--roi nano4k`.
The capture card is `/dev/video0`, YUYV **720×480** at 60 Hz, only after the
arm word.

## Capture card (HDMI)

There is one stick, UGREEN 15389, `/dev/video0`. The maintainer moves the
HDMI cable. Set `--board` to match the cable. Open the stick, then load, so
a reload re-locks. The command lines are `tools/hdmi_capture.sh`.

```sh
tools/hdmi_capture.sh --board dock --out DIR --frames 1800 -- \
    tools/load_dock.py BITSTREAM.fs DISK.bin
tools/hdmi_capture.sh --board nano --out DIR --frames 1800 -- \
    tools/load_nano.py --sram-only BITSTREAM.fs
```

Native rawvideo at 60 fps, not `-c:v copy`. The first frames can be
leftovers; the script skips them. A live clip has changing hashes and the
20×20 square at x 300..319, y 220..239 going 0 then about 400. A locked
grey field with luma about 139 and U=V=128 is “not armed”, or the size does
not match the cable. `tools/hdmi_stats.py --board nano|dock` prints luma on
a few frames. White is 255. `measure_blink` is red-minus-green and reads
zero on these black-and-white frames; do not use it on HDMI, and do not
convert YUYV to an RGB PNG to judge the picture.

Webcam `/dev/video2` is the LED camera. `tools/measure_blink.sh` defaults to
`/dev/video0`. For an LED clip pass `--device /dev/video2`. Always open
`roi.png`: the Dock has two reds, the right one stays lit, and a remembered
`x,y` from an old write-up is often a few tens of pixels off. A dim Dock
lamp can FFT at 1 Hz while the edge detector chatters; the Nano lamp is
usually a clean square wave.

## Easy to get wrong

- USB **port**, not a remembered `003:0xx`. That number moves.
- `tools/sram_load.sh` with no `-b` loads the Dock. With no `--busdev-num`
  it can pick either board.
- A Dock UART bind is `sudo -n /usr/local/sbin/blinky-bind-dock-uart`,
  **before** the SRAM load. `sudo -n true` is the wrong check.
- Never `ftdi_usb_reset` on the Dock. A reset drops trained DDR3.
- Never flash a bitstream. The 4K NOR write is a **data file** at
  `0x200000` only.
- Do not load one board while loading the other.
- After a 1000 ms disk the first two LED rises are 2 s, then 1 s. A short
  clip that spans the change makes `measure_blink` untrusted.
- The wrong HDMI size on a live cable looks like the unarmed grey field
  (luma 139, U=V=128). Set `--board` to match the cable, not the other FPGA.
- HDMI: open the stick, then load (`tools/hdmi_capture.sh`). A grab after
  the load, or a clip that never reloads, can sit on one frame.
