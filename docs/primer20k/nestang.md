# NESTang on Primer 20K Dock (Bee, 3 Nov 2026)

Followed [setup_primer](https://nand2mario.github.io/nestang-doc/setup_primer/):
**NESTang 0.4** is the last release that targets this board. Current `master`
dropped Primer 20K. ROM load is the **UART loader**, not FPGA flash and not SD.
SRAM only (`openFPGALoader -m`). Never `-f`.

## Build (Gowin 1.9.12.04)

Clone [nand2mario/nestang](https://github.com/nand2mario/nestang) at tag **`v0.4`**
(last release that targets Primer 20K). Tcl: `build_dock.tcl` (Dock CST, top
`NES_Tang20k`, GW2A-LV18PG256C8/I7).

```sh
git clone --branch v0.4 --depth 1 https://github.com/nand2mario/nestang.git
cd nestang
QT_QPA_PLATFORM=xcb gw_sh build_dock.tcl
# bitstream: impl/pnr/nestang_dock.fs  (do not commit .fs)
```

PNR completed. HDMI pairs placed as LVCMOS33D on G16/H15, H14/H16, J15/K16,
K14/K15 (same balls as Sipeed `HDMI/src/dk_video.cst`).

## SRAM load (never flash)

```sh
tools/sram_load.sh impl/pnr/nestang_dock.fs
# → openFPGALoader -b tangprimer20k -m …
```

## HDMI: palette then nestest

After SRAM load, `nes2hdmi` shows the BRAM init pattern
(`$readmemb("nes_fb_testpattern_palette.txt")`) until a ROM is parsed and the
PPU overwrites the framebuffer.

The first HDMI check looked like a black panel because the ThinkVision was on
the wrong HDMI switcher input, not because the bitstream was dark. Once
switched, Dock HDMI is a clean NES palette:

- [`hdmi-monitor-palette.jpg`](hdmi-monitor-palette.jpg) — palette, no ROM yet

Stills are one-shot `ffmpeg -f v4l2` JPEGs from `/dev/video0` (webcam MCP
`capture_still`, or ffmpeg directly). Do not hold the camera open.

## What was wrong with ROM load

The in-tree Linux `loader/loader` is the wrong tool for a one-shot bring-up:

1. After `sendNES()` it always enters the gamepad loop. Linux `select()` uses a
   NULL timeout, so it blocks forever (no pad or with a pad).
2. `timeout(1)` then kills the process. With stdout fully buffered (no TTY),
   the `"transmitted"` line never appears, so it looked like the ROM was never
   sent.
3. `loader -v` dumps every packet to stdout and was previously left running
   for minutes, which can leave `UartDemux` mid-packet.
4. It was not the baud or the pins. v0.4 `BAUDRATE=921600`, `FREQ=32_250_000`,
   `CLKS_PER_BIT=34`. `uart_rx`’s 8-bit counter **cannot** do 115200 at this
   FREQ (279 clocks). This glibc has `B921600 == 921600`. CST maps
   `UART_TXD=M11` / `UART_RXD=T13` on the BL702 USB-UART (`ttyUSB1`, not
   `ttyUSB0` JTAG).

Opening `ttyUSB1` first, then SRAM-loading, the FPGA TX is readable at 921600:
`NES_Tang restarting...`, a first `DDR3 initialization failed. Retrying...`,
and after the ROM send **`Game loading done.`**

## Fix: one-shot UART sender

`tools/nestang_uart_load.py` — no gamepad loop, raw 8N1, `-crtscts`, DTR+RTS,
packets with **n ≤ 255** (count byte equals payload length; FPGA `count==0`
means 256 bytes). Protocol from `hw_uart.v` / `nes_tang20k.v`:

```
packet = checksum | addr | count | n data bytes   # sum of all bytes == 0
addr 0x35 = loader reset (write 1, then 0)
addr 0x37 = iNES ROM bytes
```

```sh
# Open UART, SRAM-load (never flash), then send Kevtris nestest.nes
# (fetch nestest separately; do not commit ROMs):
python3 -u tools/nestang_uart_load.py -c /dev/ttyUSB1 -b 921600 \
  --listen 25 --listen-after 2 \
  path/to/nestest.nes
# in parallel, after the port is open:
tools/sram_load.sh impl/pnr/nestang_dock.fs
```

Free ROMs only. No commercial games, no FPGA flash, no SD.

## Result — nestest

ThinkVision after the one-shot load (`ffmpeg` / webcam MCP still):

- [`hdmi-monitor-nestest.jpg`](hdmi-monitor-nestest.jpg) — nestest menu
  (`* Run all tests`, Branch/Flag/Immediate/…, `Start: run test`)

## Alter Ego (Shiru, 2011, freeware NROM)

Zip from [pdroms.de/alter-ego](https://pdroms.de/files/nintendo-nes-famicom/alter-ego)
(`Alter_Ego.nes`, iNES mapper 0, 32 KB PRG + 8 KB CHR, vertical mirroring).
notes.txt: released as freeware, not public domain. Same UART path as nestest
(open `ttyUSB1` first, SRAM-load, then send). After `Game loading done.`, pulse
Start (`addr 0x40`, bit 3) to leave the dark title screen:

```sh
python3 -u tools/nestang_uart_load.py -c /dev/ttyUSB1 -b 921600 \
  --listen 20 --listen-after 2 --joy-after 0x08 \
  path/to/Alter_Ego.nes
```

- [`hdmi-monitor-alter-ego.jpg`](hdmi-monitor-alter-ego.jpg) — first level
  (`HELLO WORLD`, bricks, water). HDMI audio carries Kulor’s music.

HDMI + UART loader + SRAM-only NESTang v0.4 on the Primer 20K Dock is working.
