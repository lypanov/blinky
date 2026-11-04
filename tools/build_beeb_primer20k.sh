#!/usr/bin/env bash
# Build BeebFpga Model B for the Tang Primer 20K Dock with Gowin gw_sh.
# Does not program the FPGA. Bitstream is SRAM-loadable .fs.
# ROMs are initialised into BSRAM from the submodule's textio image.
# IncludeBootStrap is false, so nothing is read from or written to SPI flash.
#
# Usage (from the blinky repo root):
#   tools/build_beeb_primer20k.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BEEB="$ROOT/retro/beebfpga"
GPRJ="$BEEB/src/gowin/tang_primer20k/tang_primer_20k_nodebugger/tang20k.gprj"
CST="$ROOT/retro/beeb/tang20k_dock.cst"
BUILD="$ROOT/retro/beeb/build"
ROM_BIT="$BEEB/roms/bbcb/os12_mmfs_basic.bit"
PIN="49c63cc1e74bf3062bc948b83219db77c25bedaa"

if [[ -z "${QT_QPA_PLATFORM:-}" || "${QT_QPA_PLATFORM}" == "wayland;xcb" || "${QT_QPA_PLATFORM}" == "wayland" ]]; then
  export QT_QPA_PLATFORM=xcb
fi
if [[ "${QT_QPA_PLATFORM}" == "offscreen" ]]; then
  echo "error: QT_QPA_PLATFORM=offscreen crashes gw_sh; unset it or use xcb" >&2
  exit 1
fi
if ! command -v gw_sh >/dev/null 2>&1; then
  echo "error: gw_sh not on PATH (expect /usr/bin/gw_sh -> /opt/gowin-eda-ide)" >&2
  exit 1
fi
if [[ ! -f "$GPRJ" ]]; then
  echo "error: missing $GPRJ (git submodule update --init retro/beebfpga)" >&2
  exit 1
fi

got="$(git -C "$BEEB" rev-parse HEAD)"
if [[ "$got" != "$PIN" ]]; then
  echo "error: retro/beebfpga is $got, want $PIN" >&2
  exit 1
fi
if [[ ! -f "$ROM_BIT" ]]; then
  echo "error: missing ROM init $ROM_BIT" >&2
  exit 1
fi
lines="$(wc -l < "$ROM_BIT")"
if [[ "$lines" -ne 49152 ]]; then
  echo "error: $ROM_BIT has $lines lines, want 49152 (48 KiB, one byte per line)" >&2
  exit 1
fi

mkdir -p "$BUILD"
# Absolute path so VHDL textio does not depend on gw_sh's working directory.
# The image stays in the submodule. It is not copied into this repo.
python3 - "$BEEB" "$GPRJ" "$CST" "$BUILD" << 'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

beeb, gprj, cst, build = map(Path, sys.argv[1:])
# Upstream tang20k.gprj says version="1", which ElementTree rejects.
xml = gprj.read_text(encoding="utf-8").replace('<?xml version="1"', '<?xml version="1.0"', 1)
root = ET.fromstring(xml)
files = []
for f in root.find("FileList"):
    kind = f.attrib.get("type", "")
    if f.attrib.get("enable", "1") != "1":
        continue
    if kind in ("file.cst", "file.sdc"):
        continue
    src = (gprj.parent / f.attrib["path"]).resolve()
    if not src.is_file():
        # tang20k.gprj still lists mist_scandoubler.vhd and retimer.vhd.
        # Those files are not in commit 49c63cc and nothing instantiates them.
        print(f"skip missing (not in tree): {src}", file=sys.stderr)
        continue
    files.append((kind, src))
# tang20k.gprj at 49c63cc omits files the Model B HDMI build actually
# instantiates, and still lists two scandoubler files that are gone:
#   * linedelay.vhd — scan doubler (IncludeHDMI => IncludeHD)
#   * saa5050_rom.vhd — mode 7 character ROM (IncludeTTxtROM defaults true).
#     The gprj lists saa5050_rom_dual_port.vhd, which nothing instantiates.
extras = [
    beeb / "src/common/scandoubler/linedelay.vhd",
    beeb / "src/common/saa5050_rom.vhd",
    beeb / "src/common/saa5050_rom_uninitialized.vhd",
]
for extra in extras:
    extra = extra.resolve()
    if not extra.is_file():
        raise SystemExit(f"missing {extra}")
inserted = False
ordered = []
for kind, src in files:
    if src.name == "bbc_micro_core.vhd" and not inserted:
        for extra in extras:
            ordered.append(("file.vhdl", extra.resolve()))
        inserted = True
    ordered.append((kind, src))
if not inserted:
    raise SystemExit("bbc_micro_core.vhd not in the project file list")
files = ordered

# Commit 49c63cc updated bbc_micro_core and the Tang Nano 20K top, but
# left tang_primer20k/src/bbc_micro_tang20k.vhd on the old port map
# (clock_32, video_*, hdmi_audio_*, vid_mode, hsync_ref). Patch a copy
# in the build dir. The submodule stays at 49c63cc.
primer = beeb / "src/gowin/tang_primer20k/src/bbc_micro_tang20k.vhd"
text = primer.read_text(encoding="utf-8")
pm_key = "            clock_32       => '0'"
pm_at = text.find(pm_key)
if pm_at < 0:
    raise SystemExit("primer top no longer has the stale clock_32 port map; review the patch")
pm_start = text.rfind("        port map (", 0, pm_at)
pm_end = text.find("            test            => test", pm_at)
if pm_start < 0 or pm_end < 0:
    raise SystemExit("could not locate the bbc_micro port map")
pm_end = text.find(");", pm_end)
if pm_end < 0:
    raise SystemExit("could not locate the end of the bbc_micro port map")
pm_end += 2
text = text[:pm_start] + """        port map (
            -- Patched for bbc_micro_core at 49c63cc. clock_32, clock_96,
            -- video_*, hdmi_audio_*, vid_mode and hsync_ref are gone.
            -- HDMI audio is generated inside the core. VGA is the
            -- scandoubler output (IncludeVGA). CLKDIV for clock_27 is
            -- released below, not by hsync_ref.
            clock_27        => clock_27,
            clock_48        => clock_48,
            clock_avr       => clock_24,
            hard_reset_n    => hard_reset_n,
            powerup_reset_n => powerup_reset_n,
            ps2_kbd_clk     => ps2_clk,
            ps2_kbd_data    => ps2_data,
            ps2_mse_clk     => ps2_mouse_clk,
            ps2_mse_data    => ps2_mouse_data,
            dbg_keyboard_state => dbg_keyboard_state,
            vga_red         => i_VGA_R,
            vga_green       => i_VGA_G,
            vga_blue        => i_VGA_B,
            vga_hsync       => vga_hs,
            vga_vsync       => vga_vs,
            audio_l         => audio_l_legacy,
            audio_r         => audio_r_legacy,
            psg_audio       => psg_audio,
            psg_strobe      => psg_strobe,
            sid_audio       => sid_audio,
            sid_strobe      => sid_strobe,
            m5k_filter_en   => m5k_filter_en,
            m5k_audio_l     => m5k_audio_l,
            m5k_audio_r     => m5k_audio_r,
            m5k_strobe      => m5k_strobe,
            m5k_spdif       => m5k_spdif,
            ext_nOE         => ext_nOE,
            ext_nWE         => ext_nWE,
            ext_nWE_long    => ext_nWE_long,
            ext_nCS         => ext_nCS,
            ext_A           => ext_A,
            ext_A_stb       => ext_A_stb,
            ext_Dout        => ext_Dout,
            ext_Din         => ext_Din,
            SDMISO          => tf_miso,
            SDSS            => tf_cs,
            SDCLK           => tf_sclk,
            SDMOSI          => tf_mosi,
            caps_led        => caps_led,
            shift_led       => shift_led,
            keyb_dip        => keyb_dip,
            ext_keyb_led1   => open,
            ext_keyb_led2   => open,
            ext_keyb_led3   => open,
            ext_keyb_1mhz   => open,
            ext_keyb_en_n   => open,
            ext_keyb_pa     => open,
            ext_keyb_rst_n  => '1',
            ext_keyb_ca2    => '0',
            ext_keyb_pa7    => '0',
            config          => config,
            joystick1       => (others => '1'),
            joystick2       => (others => '1'),
            avr_reset       => not hard_reset_n,
            avr_RxD         => uart_rx,
            avr_TxD         => uart_tx,
            cpu_addr        => open,
            m128_mode       => m128_mode,
            copro_mode      => copro_mode,
            p_spi_ssel      => '0',
            p_spi_sck       => '0',
            p_spi_mosi      => '0',
            p_spi_miso      => open,
            p_irq_b         => open,
            p_nmi_b         => open,
            p_rst_b         => open,
            ext_tube_r_nw   => open,
            ext_tube_nrst   => open,
            ext_tube_ntube  => open,
            ext_tube_phi2   => open,
            ext_tube_a      => open,
            ext_tube_di     => open,
            ext_tube_do     => (others => '0'),
            ext_1mhz_clken  => ext_1mhz_clken,
            ext_1mhz_nrst   => ext_1mhz_nrst,
            ext_1mhz_pgfc_n => ext_1mhz_pgfc_n,
            ext_1mhz_pgfd_n => open,
            ext_1mhz_r_nw   => ext_1mhz_r_nw,
            ext_1mhz_addr   => ext_1mhz_addr,
            ext_1mhz_di     => ext_1mhz_di,
            ext_1mhz_do     => ext_1mhz_do,
            ext_1mhz_irq_n  => open,
            ext_1mhz_nmi_n  => open,
            hdmi_aspect     => hdmi_aspect,
            hdmi_audio_en   => hdmi_audio_en,
            vid_debug       => vid_debug,
            tmds_r          => tmds_r,
            tmds_g          => tmds_g,
            tmds_b          => tmds_b,
            trace_data      => trace_data,
            trace_r_nw      => trace_r_nw,
            trace_sync      => trace_sync,
            trace_rstn      => trace_rstn,
            trace_phi2      => trace_phi2,
            test            => test
        );""" + text[pm_end:]
old_gen = "            IncludeHDMI        => IncludeHDMI,\n            UseOrigKeyboard    => false,"
new_gen = "            IncludeHDMI        => IncludeHDMI,\n            IncludeVGA         => true,\n            UseOrigKeyboard    => false,"
if old_gen not in text:
    raise SystemExit("could not insert IncludeVGA into the core generic map")
text = text.replace(old_gen, new_gen, 1)
old_div = "            RESETN => clkdiv_reset_n,\n            HCLKIN => clock_135,"
new_div = "            RESETN => '1', -- no hsync_ref; free-run like the updated tang20k top\n            HCLKIN => clock_135,"
if old_div not in text:
    raise SystemExit("could not retie clkdiv5 RESETN")
text = text.replace(old_div, new_div, 1)
old_tie = "    vid_debug      <= '0';\n"
new_tie = "    vid_debug      <= '0';\n    hsync_ref      <= '0'; -- port removed from the core; divider no longer waits on it\n"
if old_tie not in text:
    raise SystemExit("could not tie hsync_ref")
text = text.replace(old_tie, new_tie, 1)
# Absolute ROM path. The entity default "../../../.." only resolves when
# gw_sh's cwd is tang_primer_20k_nodebugger. This copy is the top module,
# so the SDC net names (clock_27, bbc_micro/...) stay as upstream wrote them.
old_root = 'PRJ_ROOT           : string  := "../../../..";'
new_root = f'PRJ_ROOT           : string  := "{beeb}";'
if old_root not in text:
    raise SystemExit("could not retarget PRJ_ROOT")
text = text.replace(old_root, new_root, 1)
patched = build / "bbc_micro_tang20k_patched.vhd"
patched.write_text(text, encoding="utf-8")
swapped = False
rewritten = []
for kind, src in files:
    if src.name == "bbc_micro_tang20k.vhd" and "tang_primer20k" in str(src):
        rewritten.append((kind, patched.resolve()))
        swapped = True
    else:
        rewritten.append((kind, src))
if not swapped:
    raise SystemExit("did not find tang_primer20k bbc_micro_tang20k.vhd to replace")
files = rewritten
print(f"patched top: {patched}")

sdc = (gprj.parent / "../src/bbc_micro_tang20k.sdc").resolve()
if not sdc.is_file():
    raise SystemExit(f"missing sdc {sdc}")

wrapper = build / "bbc_micro_tang20k_bee.vhd"
# PRJ_ROOT is concatenated with MOS_NAME inside mem_tang_primer_20k.
prj = str(beeb)
wrapper.write_text(f"""-- Generated by tools/build_beeb_primer20k.sh. Do not commit.
-- Top for the Bee Dock build. IncludeBootStrap is false: the 48 KiB
-- ROM image is read at synthesis (VHDL textio) into BSRAM init.
-- Nothing in this configuration writes SPI flash.
library ieee;
use ieee.std_logic_1164.all;

entity bbc_micro_tang20k_bee is
    port (
        sys_clk         : in    std_logic;
        btn1_n          : in    std_logic;
        btn2_n          : in    std_logic;
        btn3_n          : in    std_logic;
        led             : out   std_logic_vector (5 downto 0);
        ws2812_din      : out   std_logic;
        ps2_clk         : inout std_logic;
        ps2_data        : inout std_logic;
        ps2_mouse_clk   : inout std_logic;
        ps2_mouse_data  : inout std_logic;
        tf_miso         : in    std_logic;
        tf_cs           : out   std_logic;
        tf_sclk         : out   std_logic;
        tf_mosi         : out   std_logic;
        uart_rx         : in    std_logic;
        uart_tx         : out   std_logic;
        tmds_clk_p      : out   std_logic;
        tmds_clk_n      : out   std_logic;
        tmds_d_p        : out   std_logic_vector(2 downto 0);
        tmds_d_n        : out   std_logic_vector(2 downto 0);
        vga_r           : out   std_logic;
        vga_b           : out   std_logic;
        vga_g           : out   std_logic;
        vga_hs          : out   std_logic;
        vga_vs          : out   std_logic;
        i2s_bclk        : out   std_logic;
        i2s_lrclk       : out   std_logic;
        i2s_din         : out   std_logic;
        pa_en           : out   std_logic;
        flash_cs        : out   std_logic;
        flash_si        : out   std_logic;
        flash_ck        : out   std_logic;
        flash_so        : in    std_logic
    );
end entity;

architecture rtl of bbc_micro_tang20k_bee is
begin
    u_bbc : entity work.bbc_micro_tang20k
        generic map (
            IncludeMaster         => false,
            IncludeBeeb           => true,
            IncludeMixerResampler => false,
            IncludeBootStrap      => false,
            IncludeMonitor        => false,
            IncludeICEDebugger    => false,
            SIM                   => false,
            PRJ_ROOT              => "{prj}",
            MOS_NAME              => "/roms/bbcb/os12_mmfs_basic.bit"
        )
        port map (
            sys_clk        => sys_clk,
            btn1_n         => btn1_n,
            btn2_n         => btn2_n,
            btn3_n         => btn3_n,
            led            => led,
            ws2812_din     => ws2812_din,
            ps2_clk        => ps2_clk,
            ps2_data       => ps2_data,
            ps2_mouse_clk  => ps2_mouse_clk,
            ps2_mouse_data => ps2_mouse_data,
            tf_miso        => tf_miso,
            tf_cs          => tf_cs,
            tf_sclk        => tf_sclk,
            tf_mosi        => tf_mosi,
            uart_rx        => uart_rx,
            uart_tx        => uart_tx,
            tmds_clk_p     => tmds_clk_p,
            tmds_clk_n     => tmds_clk_n,
            tmds_d_p       => tmds_d_p,
            tmds_d_n       => tmds_d_n,
            vga_r          => vga_r,
            vga_b          => vga_b,
            vga_g          => vga_g,
            vga_hs         => vga_hs,
            vga_vs         => vga_vs,
            i2s_bclk       => i2s_bclk,
            i2s_lrclk      => i2s_lrclk,
            i2s_din        => i2s_din,
            pa_en          => pa_en,
            flash_cs       => flash_cs,
            flash_si       => flash_si,
            flash_ck       => flash_ck,
            flash_so       => flash_so
        );
end architecture;
""")

type_map = {"file.vhdl": "vhdl", "file.verilog": "verilog"}
lines = [
    "# Generated by tools/build_beeb_primer20k.sh. Do not commit.",
    "# Gowin 1.9.12 gw_sh. Device gw2a18c-011 = GW2A-LV18PG256C8/I7.",
    "# SRAM bitstream only. IncludeBootStrap=false. Do not program flash.",
    "set_device -name GW2A-18C GW2A-LV18PG256C8/I7",
]
for kind, src in files:
    lines.append(f'add_file -type {type_map[kind]} "{src}"')
# Top is the patched bbc_micro_tang20k, not the wrapper. A wrapper would
# push every SDC path down one level (u_bbc/clock_27) and Gowin then
# rejects the upstream constraints before place.
lines.append(f'add_file -type cst "{cst.resolve()}"')
lines.append(f'add_file -type sdc "{sdc}"')
lines += [
    "set_option -top_module bbc_micro_tang20k",
    "set_option -vhdl_std vhd2008",
    "set_option -verilog_std v2001",
    "set_option -synthesis_tool gowinsynthesis",
    "set_option -output_base_name tang20k",
    "set_option -place_option 0",
    # mem_tang_primer_20k reads 49152 lines. Default loop limit is 2000.
    # Upstream tang20k_process_config.json sets GwSyn_Loop_Limit 200000.
    "set_option -looplimit 200000",
    "set_option -bit_incl_bsram_init 1",
    "set_option -timing_driven 1",
    "set_option -correct_hold_violation 1",
    "set_option -cst_warn_to_error 1",
    "set_option -use_done_as_gpio 1",
    "set_option -use_ready_as_gpio 1",
    "set_option -use_sspi_as_gpio 1",
    # Flash balls are user IO held idle. JTAG SRAM load does not use them.
    "set_option -use_mspi_as_gpio 1",
    "set_option -use_jtag_as_gpio 0",
    "run all",
    "",
]
(build / "tang20k_bee.tcl").write_text("\n".join(lines))
print(f"sources: {len(files)} (top bbc_micro_tang20k, patched)")
PY

echo "==> Gowin syn+PNR (GW2A-LV18PG256C8/I7) cwd=$BUILD"
cd "$BUILD"
gw_sh "$BUILD/tang20k_bee.tcl"

FS="$BUILD/impl/pnr/tang20k.fs"
VG="$BUILD/impl/gwsynthesis/tang20k.vg"
if [[ ! -f "$FS" ]]; then
  echo "error: bitstream was not produced" >&2
  find "$BUILD/impl" -name '*.fs' -type f || true
  exit 1
fi

echo "==> Checking BSRAM init matches the 48 KiB ROM image"
python3 - "$VG" "$ROM_BIT" << 'PY'
import re
import sys
from pathlib import Path

vg = Path(sys.argv[1]).read_text(errors="replace")
expect = bytes(int(line, 2) for line in Path(sys.argv[2]).read_text().splitlines())
# Gowin packs the byte-wide ROM as 1-bit SP primitives:
# r_mem_rom_<block>_<bit>, 16 Ki addresses per block, LSB of each
# 256-bit INIT word is the lowest address. Omitted INIT words are zero.
starts = [(m.start(), m.group(1)) for m in re.finditer(r"^  SP (r_mem_rom\S+) \(", vg, re.M)]
if len(starts) != 24:
    raise SystemExit(f"error: expected 24 ROM SP primitives, found {len(starts)}")
mem = bytearray(49152)
for i, (pos, name) in enumerate(starts):
    end = starts[i + 1][0] if i + 1 < len(starts) else pos + 20000
    chunk = vg[pos:end]
    m = re.search(r"r_mem_rom_(\d+)_(\d+)_s", name)
    blk, bit = int(m.group(1)), int(m.group(2))
    for im in re.finditer(r"INIT_RAM_([0-9A-Fa-f]+)=256'h([0-9A-Fa-f]+)", chunk):
        val = int(im.group(2), 16)
        base = blk * 16384 + int(im.group(1), 16) * 256
        for addr_off in range(256):
            addr = base + addr_off
            if addr < 49152 and (val >> addr_off) & 1:
                mem[addr] |= 1 << bit
if bytes(mem) != expect:
    raise SystemExit("error: BSRAM init does not match os12_mmfs_basic.bit")
banner = bytes(mem[772:784])
if banner != b"BBC Computer":
    raise SystemExit(f"error: OS banner is {banner!r}")
print("    49152 ROM bytes match, including 'BBC Computer'")
PY

echo ""
echo "Bitstream (gitignored, SRAM-loadable, do not flash):"
echo "  $FS"
echo "Load later with:"
echo "  tools/beeb_sram_load.sh $FS"
echo "Do NOT pass -f / --write-flash / --external-flash."
echo "Do NOT target JTAG bus 3 dev 81 (Tang Nano 4K)."
