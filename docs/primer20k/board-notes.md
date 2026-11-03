# Tang Primer 20K Dock — board notes (Bee, 3 Nov 2026)

FPGA: **GW2A-LV18PG256C8/I7** (GW2A-18C) on the SODIMM core, Dock carrier.
Crystal: **27 MHz on H11**.

**HARD RULE:** load bitstreams to SRAM only. Never write the FPGA flash, even
if the Dock already has a factory image in flash.

```sh
openFPGALoader -b tangprimer20k -m <bitstream.fs>
```

Do **not** pass `-f`, `--write-flash`, or `--external-flash`.

## Detection on Bee (verified)

| Check | Result |
|---|---|
| `lsusb` | `0403:6010` Future Technology Devices International FT2232C/D/H Dual UART/FIFO IC |
| Serial | `/dev/serial/by-id/usb-SIPEED_JTAG_Debugger_FactoryAIOT_Pro-if00-port0` → `ttyUSB0` (JTAG), `…-if01-port0` → `ttyUSB1` (UART) |
| `openFPGALoader --detect` | `idcode 0x81b`, manufacturer Gowin, family GW2A, model GW2A(R)-18(C), irlength 8 |
| udev | `/etc/udev/rules.d/99-tang-nano.rules` already has `ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010", MODE="0666"`. No change needed. |
| Webcam | Logitech QuickCam at `/dev/video0`, pointed at the Dock. Image is low quality — measure blink **frequency** only. |

The Dock debugger is the onboard **BL702**, enumerated as FT2232 `0403:6010`.
openFPGALoader board name: `tangprimer20k`.

JTAG is up, so the core is enabled. Webcam shows a red 5-position DIP near the
USB-C debug port. Board silkscreen revision was **not** read off the PCB.

## LED example used here

Sipeed wiki Dock blinky ([examples/led.html](https://wiki.sipeed.com/hardware/en/tang/tang-primer-20k/examples/led.html)):

- Clock `H11`, LED `L14`, `LVCMOS33`
- Counter `COUNT_VALUE = 13_499_999` at 27 MHz → flip every 0.5 s → **1 Hz** full period
- Wiki Verilog does **not** invert the pin. Dock user LEDs are **active-low**
  (anode to 3V3 via 510R), so FPGA `0` = lit. Frequency is the same either way.

Do **not** use `Lite-bottom_test_project` constraints. Those are for the Lite
carrier and clash with the Dock BL702 UART on **T13**.

## User LEDs (active-low)

| Net (schematic) | Ball | Bank | Dual-purpose | Notes |
|---|---|---|---|---|
| Orange_LED0 | **C13** | 3 | DONE | `set_option -use_done_as_gpio 1` |
| Orange_LED1 | **A13** | 3 | READY | `set_option -use_ready_as_gpio 1` |
| Orange_LED2 | **N16** | 1 | | V3708 silk had LED2/LED3 swapped (see wiki) |
| Orange_LED3 | **N14** | 1 | | |
| Orange_LED4 | **L14** | 1 | | Wiki blink example pin |
| Orange_LED5 | **L16** | 1 | | |

Onboard WS2812 data is **T9** (not a user LED).

LED index order in CST files is **not consistent** across sources (Litex vs
HDMI demo vs schematic Orange_LED0–5). Treat balls as authoritative, not
`led[n]` names.

Not FPGA-controlled: BL702 status LEDs, USB PHY power LED, 5 V power LED.

## Clock, reset, buttons, DIP

| Signal | Ball | IO_TYPE | Notes |
|---|---|---|---|
| 27 MHz oscillator | **H11** | LVCMOS33 | GCLK-capable, bank 0 |
| Key S1 / FPGA_RST | **T10** | LVCMOS33 | Active-low. SSPI pin → `use_sspi_as_gpio 1`. Shared with SOM reset supervisor. |
| Key S2 | **T3** | LVCMOS15 | Bank 4, 1.5 V, active-low |
| Key S3 | **T2** | LVCMOS15 | Bank 4, 1.5 V, active-low |
| Key S4 | **D7** | LVCMOS15 | Bank 4, 1.5 V, active-low. On Dock **V3714+** this is reconfigure. |
| Key S5 | **C7** | LVCMOS15 | Bank 4, 1.5 V, active-low |

DIP SW3 (active-high when ON):

| Position | Ball | Notes |
|---|---|---|
| SW1 | **B10** | RECONFIG_N. On Docks **older than V3714**, DIP1 must be **down** to enable the core (otherwise LED0/LED1 stay on and JTAG fails). V3714+ does not use DIP1 for reconfigure. Keep SW1 from holding RECONFIG_N low at boot. |
| SW2–SW5 | E9, E8, T4, T5 | Bank 4, 1.5 V |

## UART / JTAG (avoid for user IO)

| Signal | Ball | Notes |
|---|---|---|
| FPGA_TX → PC | **M11** | BL702 UART1_RX. `IO_TYPE=LVCMOS33` |
| FPGA_RX ← PC | **T13** | BL702 UART1_TX |
| TCK TMS TDI TDO | A7 B8 A6 C6 | Dedicated JTAG. Never `use_jtag_as_gpio`. |

Second USB-C is the **USB3317** user PHY, not the debugger.

## HDMI / DVI-TX (Dock J3)

Pairs are TMDS, AC-coupled. Sipeed HDMI example (`TangPrimer-20K-example/HDMI/src/dk_video.cst`)
and NESTang v0.4 `nestang_dock.cst` agree:

| Signal | P / N balls |
|---|---|
| TMDS clock | G16 / H15 |
| TMDS data 0 | H14 / H16 |
| TMDS data 1 | J15 / K16 |
| TMDS data 2 | K14 / K15 |

Sipeed CST uses combined `IO_LOC "O_tmds_clk_p" G16,H15;` (true LVDS pair).
NESTang v0.4 lists P and N separately. HPD/CEC/DDC: J11, L12, F14, F16.

## PMOD / GPIO headers

Dock has four 2×6 PMODs. They share pins with LCD / camera / mic — one use at a time.

| Header | Shared with | Pins (ball) |
|---|---|---|
| PMOD J14 (MIC) | Mic array, WS2812 | P6, R8, P8, T9 / T6, T7, T8, P9. **T9 = WS2812** |
| PMOD J12 (TVP / camera data) | DVP D0–D7 | P11, R11, M15, J16 / T11, T12, M14, J14 |
| PMOD J6 (RGB) | RGB LCD B/HS/VS/DE | E15, A15, A14, C12 / D14, B14, B13, B12 |
| PMOD J5 (LCD) | RGB LCD R/G | B11, D11, N7, N8 / A11, N6, N9, L9 |

**Later Pi UART (unverified on hardware):** PMOD2 (J12) **M15 / M14** are the
candidates (bank 1, 3.3 V documented). J16 / J14 (bank 0) are the fallback.
Do not steal M11 / T13 (BL702 UART).

## Pins to leave alone

| Function | Balls |
|---|---|
| BL702 UART | M11, T13 |
| JTAG | A7, C6, A6, B8 |
| Config SPI flash (MSPI boot) | M9, L10, P10, R10 — do not `use_mspi_as_gpio` for blinky |
| microSD | N10, R14, N11, M8, M7, M10 |

Bank 0, 1, 7 default VCCIO is 3.3 V (wiki). Bank 4 is 1.5 V (DDR3 + keys S2–S5).

## NESTang on this Dock

Current NESTang `master` dropped Primer 20K. Official Primer setup
([nestang-doc/setup_primer](https://nand2mario.github.io/nestang-doc/setup_primer/))
is **NESTang 0.4**. ROM load is the UART `loader`, not FPGA flash and not SD.

- Bitstream: `nestang-dock.fs` (Dock HDMI), SRAM-load only
- ROM: UART loader (`loader.exe` / Linux `loader/`), never write FPGA flash
- If a later NESTang release requires flashing the bitstream or putting the ROM
  in SPI flash, **stop** and report

## Unverified (do not treat as measured)

From The Researcher (3 Nov 2026) and remaining gaps:

- **Bank 2 / 3 VCCIO** — wiki states banks 0, 1, 7 are 3.3 V; bank 4 is 1.5 V.
  Bank 2/3 voltage was not meter-checked. terenceang pinout claims 3.3 V from
  the Dock/SOM schematic; still unverified on this board.
- **Sipeed schematic PDF** at `dl.sipeed.com/shareURL/TANG/Primer_20K/02_Schematic`
  was not opened here. Pin table above is from wiki + example CSTs + schematic-derived
  secondary notes, not a first-hand PDF read.
- **Silkscreen LED order** vs Orange_LED0–5 / LED4–LED9. Index names disagree
  across Litex, HDMI demo, and NESTang CST comments. Balls are used instead.
- **PMOD2 sharing with TVP/camera** — assumed from pin lists; not scoped on the
  bench. Using M15/M14 for a Pi UART would occupy camera data pins.
- **Board silkscreen revision** (V3708 / V3713 / V3714). DIP1 behaviour depends
  on this. JTAG works, so the core is enabled, but the printed rev was not read.
- **LED polarity** was not scoped; active-low is from schematic notes
  (anode to 3V3 via 510R). Webcam cannot identify which LED is which.
- **PMOD2 M15/M14 as Pi UART** — candidate only, not loopback-tested.
- **HDMI to the ThinkVision** — webcam stills after SRAM-loading both NESTang
  v0.4 and Sipeed’s Dock HDMI example show a black panel. Board-side HDMI
  cable is plugged in; monitor input / sleep was not changed from Bee. See
  [`nestang.md`](nestang.md).

## Sources

1. Sipeed wiki — [Tang Primer 20K](https://wiki.sipeed.com/hardware/en/tang/tang-primer-20k/primer-20k.html),
   [start / Dock gotchas](https://wiki.sipeed.com/hardware/en/tang/tang-primer-20k/start.html)
   (DIP1 / V3714, V3708 LED2/LED3 silk),
   [Dock blink LED](https://wiki.sipeed.com/hardware/en/tang/tang-primer-20k/examples/led.html)
   (H11, L14, 13_499_999, SRAM vs flash programming).
2. [sipeed/TangPrimer-20K-example](https://github.com/sipeed/TangPrimer-20K-example)
   README pin tables (clk H11, reset T10, UART M11/T13, HDMI, PMOD-adjacent LCD/camera/mic)
   and `HDMI/src/dk_video.cst` (TMDS pairs, O_led L16/L14/N14/N16).
3. LiteX `sipeed_tang_primer_20k.cst` — led0–5 = L16, L14, N14, N16, A13, C13
   (index order differs from schematic Orange_LED0–5).
4. NESTang v0.4 `src/nestang_dock.cst` — Dock HDMI, UART M11/T13, LED L16/L14 plus PMOD2 balls.
5. NESTang Primer setup: <https://nand2mario.github.io/nestang-doc/setup_primer/>
   and in-tree `doc/primer20k.md` (v0.4, UART loader, Dock already has HDMI).
6. The Researcher notes, 3 Nov 2026 (`tang-primer-20k-dock-pinout-2026-11-03.md`):
   clock, LED balls, wiki blink, Lite CST clash on T13, DIP1, PMOD2 UART candidates,
   list of unverified items.
7. Bee, this session: `lsusb`, `openFPGALoader --detect`, udev rule, webcam still.
