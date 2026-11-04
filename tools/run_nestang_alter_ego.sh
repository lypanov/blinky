#!/usr/bin/env bash
# Run the NESTang Verilator sim that already lives on Bee (~/fpga/nestang,
# nand2mario/nestang master) with Shiru's Alter Ego. NESTang is GPL and stays
# in that tree — this script does not copy its sources, and it does not load
# or flash an FPGA.
#
# The Bee tree carries local sim patches (see docs/sim-bee/README.md):
#   src/mappers/generic.sv   drop duplicate prg_allow (Verilator)
#   verilator/Makefile       -Wno-WIDTHTRUNC, idempotent rom copy
#   verilator/sim_main.cpp   headless PPM dump, -o dir, -j Start pulse
#   src/nestang_top.sv       sim_joy input (bit 3 = Start) under VERILATOR
#   src/game_data.v          INES_SIZE + $readmemh path for the chosen ROM
#
# Alter Ego's title stays on PRESS START until Start. The proof run on Bee
# pulsed Start twice (frames 40–64, then 150–194). Bit 3 is the same bit the
# Primer 20K UART loader uses.
#
#   tools/run_nestang_alter_ego.sh
#   ROM=~/fpga/nestang-v04/games/Alter_Ego.nes FRAMES=320 JOY=40:25 JOY2=150:45 \
#     tools/run_nestang_alter_ego.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NESTANG="${NESTANG_ROOT:-${HOME}/fpga/nestang}"
ROM="${ROM:-${1:-${HOME}/fpga/nestang-v04/games/Alter_Ego.nes}}"
OUT="${OUT:-${HOME}/fpga/nestang-shots}"
FRAMES="${FRAMES:-320}"
# 3 Nov nes15 run: 20000000 steps -> 27 frames, ~740741 steps/frame.
STEPS="${STEPS:-$(( FRAMES * 750000 ))}"
EVERY="${EVERY:-5}"
# START or START:HOLD. JOY2 is a second Start pulse.
JOY="${JOY:-40:25}"
JOY2="${JOY2:-150:45}"

if [[ ! -f "$ROM" ]]; then
	echo "ROM not found: $ROM" >&2
	exit 1
fi
if [[ ! -f "$NESTANG/src/nestang_top.sv" ]]; then
	echo "NESTang tree not found: $NESTANG" >&2
	exit 1
fi
if ! grep -q 'sim_joy' "$NESTANG/src/nestang_top.sv"; then
	echo "NESTang is missing the local sim_joy port (Start button). See docs/sim-bee/README.md" >&2
	exit 1
fi

SIZE="$(wc -c < "$ROM" | tr -d ' ')"
HEX="$NESTANG/src/roms/alter_ego.hex"
echo "[nestang] $ROM ($SIZE bytes) -> $HEX"
python3 - "$ROM" "$HEX" "$NESTANG/src/game_data.v" "$SIZE" << 'PY'
import pathlib, sys
rom, hex_path, game_data, size = sys.argv[1:]
size = int(size)
data = pathlib.Path(rom).read_bytes()
if len(data) != size:
    raise SystemExit(f"size mismatch {len(data)} != {size}")
if data[:4] != b"NES\x1a":
    raise SystemExit("not an iNES ROM")
hex_text = "".join(f"{b:02x}\n" for b in data)
hex_file = pathlib.Path(hex_path)
if not hex_file.exists() or hex_file.read_text() != hex_text:
    hex_file.write_text(hex_text)
    print(f"[nestang] wrote {hex_path}")
else:
    print(f"[nestang] {hex_path} already matches")
text = pathlib.Path(game_data).read_text()
# Point the compiled-in loader at this hex file. The hex itself is not committed.
old_lines = []
new = []
for line in text.splitlines(keepends=True):
    if line.startswith("localparam INES_SIZE"):
        new.append(f"localparam INES_SIZE = {size};\n")
    elif 'initial $readmemh("roms/' in line and not line.lstrip().startswith("//"):
        new.append('initial $readmemh("roms/alter_ego.hex", INES);\n')
    else:
        new.append(line)
new_text = "".join(new)
gd = pathlib.Path(game_data)
if gd.read_text() != new_text:
    gd.write_text(new_text)
    print(f"[nestang] updated game_data.v INES_SIZE={size}")
else:
    print(f"[nestang] game_data.v already INES_SIZE={size}")
PY

# Keep the generated hex out of the NESTang repo if a local exclude is in use.
EXCLUDE="$NESTANG/.git/info/exclude"
if [[ -f "$EXCLUDE" ]] && ! grep -qxF 'src/roms/alter_ego.hex' "$EXCLUDE"; then
	echo 'src/roms/alter_ego.hex' >> "$EXCLUDE"
fi

mkdir -p "$OUT"
echo "[nestang] building Verilator sim (no FPGA)"
make -C "$NESTANG/verilator" -j"$(nproc)" build

echo "[nestang] $STEPS steps (~$FRAMES frames), Start=-j $JOY ${JOY2:+then $JOY2}, shots=$OUT"
(
	cd "$NESTANG/verilator/obj_dir"
	args=(-c "$STEPS" -o "$OUT" -e "$EVERY" -j "$JOY")
	if [[ -n "${JOY2:-}" ]]; then
		args+=(-j "$JOY2")
	fi
	./Vnestang_top "${args[@]}" < /dev/null
) | tee "$OUT/sim.log"

python3 - "$OUT" << 'PY'
import pathlib, sys
out = pathlib.Path(sys.argv[1])
frames = sorted(out.glob("frame_*.ppm"))
print(f"[nestang] {len(frames)} ppm frames in {out}")
if not frames:
    raise SystemExit("no screenshots")
import subprocess
for ppm in frames:
    png = ppm.with_suffix(".png")
    if png.exists() and png.stat().st_mtime >= ppm.stat().st_mtime:
        continue
    subprocess.check_call(["convert", str(ppm), "-filter", "point", "-resize", "200%", str(png)])
print("[nestang] pngs written next to the ppms (2x, nearest)")
PY

echo "[nestang] log: $OUT/sim.log"
echo "[nestang] do not commit alter_ego.hex or the ppm/png dumps"
