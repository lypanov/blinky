# NESTang on Primer 20K Dock (Bee, 3 Nov 2026)

Followed [setup_primer](https://nand2mario.github.io/nestang-doc/setup_primer/):
**NESTang 0.4** is the last release that targets this board. Current `master`
dropped Primer 20K. ROM load is the **UART loader**, not FPGA flash and not SD.

## Build (Gowin 1.9.12.04 on Bee)

Source: git worktree `/home/lypanov/fpga/nestang-v04` at tag `v0.4`.
Tcl: `build_dock.tcl` (Dock CST, top `NES_Tang20k`, GW2A-LV18PG256C8/I7).

```sh
QT_QPA_PLATFORM=xcb gw_sh build_dock.tcl
# bitstream: impl/pnr/nestang_dock.fs
```

PNR completed. HDMI pairs placed as LVCMOS33D on G16/H15, H14/H16, J15/K16,
K14/K15 (same balls as Sipeed `HDMI/src/dk_video.cst`). Netlist has 3× OSER10
and 4× ELVDS_OBUF.

## SRAM load (never flash)

```sh
openFPGALoader -b tangprimer20k -m impl/pnr/nestang_dock.fs
```

This was done. Do not pass `-f`.

## Free test ROM

`nestest.nes` (Kevtris CPU test ROM, freely redistributable, not a commercial
game) via the in-tree Linux loader:

```sh
make -C loader
./loader/loader -c /dev/ttyUSB1 -b 921600 games/nestest.nes
```

v0.4 default baud is 921600. FPGA UART is BL702 `M11`/`T13` → `ttyUSB1`.
The loader then waits for a gamepad; that is expected. No FPGA flash and no
SD card are required.

FPGA UART TX was silent at 921600 and 115200, so DDR3-init prints were not
confirmed from Bee.

## HDMI check (webcam on the ThinkVision)

`/dev/video0` was moved to the HDMI monitor. After SRAM-loading NESTang, the
panel is **black** (backlight off / no-signal look):

- [`hdmi-monitor-nestang.jpg`](hdmi-monitor-nestang.jpg)
- [`hdmi-monitor-after-sram.jpg`](hdmi-monitor-after-sram.jpg)

Sipeed’s known-good Dock HDMI example (`TangPrimer-20K-example/HDMI/dk_video.fs`)
was also SRAM-loaded. Same black panel:

- [`hdmi-monitor-sipeed-example.jpg`](hdmi-monitor-sipeed-example.jpg)

So this is not unique to NESTang: the ThinkVision is not displaying the Dock
HDMI output. Likely the monitor is asleep, powered off, or on another input
(the PC’s DisplayPort). The Dock HDMI cable was plugged in on the board side.

**Alex (~30 s):** wake the ThinkVision and select the HDMI input the Primer 20K
Dock is on. NESTang is left in **SRAM** for that check. A working v0.4 Dock
image should show a NES palette; after `nestest.nes` it should show the test
menu. Do not flash.
