#!/usr/bin/env bash
# SPI-disk boot sim. Not the DDR3 bench and not the ROM-only Blink path.
# The argument is the millisecond wait. Hardware is 1000. The 4K
# counter ticks every 13500 cpu clocks, and the CPU is half this
# bridge clock, so an edge is N*27000 bridge cycles.
# Usage: sim/run_disk_boot.sh [milliseconds]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
N="${1:-2}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"

python3 "$ROOT/sim/link_inner.py" \
  --flash-boot \
  --max-iter "$N" \
  --out "$ROOT/sim/visualizer/imem/modules.words"

if ! SIM_IMAGE=modules mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "error: CPUSimTop elaboration failed" >&2
  exit 1
fi

VERILATOR_FLAGS=(
  --cc --exe --build
  --top-module disk_boot_top
  --timescale 1ns/1ps
  -DPRINTF_COND=0
  -Wno-fatal
  -Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND
  -Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING
  -CFLAGS "-std=c++17 -O2"
  --Mdir "$ROOT/sim/obj_dir_disk"
  -o disk_boot
)

verilator "${VERILATOR_FLAGS[@]}" \
  "$ROOT/generated/CPUSimTopHyper.v" \
  "$ROOT/generated/InstrRom.v" \
  "$ROOT/generated/HwMul.v" \
  "$ROOT/sim/HyperRamUserModel.v" \
  "$ROOT/sim/CpuClock2.v" \
  "$ROOT/gowin/KeepBit.v" \
  "$ROOT/sim/LUT2.v" \
  "$ROOT/sim/spi_disk_model.v" \
  "$ROOT/gowin/button_gate.v" \
  "$ROOT/sim/disk_boot_top.v" \
  "$ROOT/sim/tb_disk_boot.cpp"

BIN="$ROOT/sim/obj_dir_disk/disk_boot"
if (( N % 2 )); then
  echo "error: millisecond wait $N must be even" >&2
  exit 1
fi
# 13500 cpu clocks/ms * 2 bridge clocks per cpu clock.
# Blink polls Time, so one edge can miss the tick by a poll. 2048
# bridge clocks covers that poll. The gaps still add up inside it.
PERIOD=$((N * 27000))
echo "[ok] elaborated N=$N ms period=$PERIOD  binary sim/obj_dir_disk/disk_boot"
"$BIN" --period "$PERIOD" --slack 2048 --edges 3
echo "[ok] NOR disk N=$N period $PERIOD"
# S1 held across three edges. The LED stays on, then the period resumes.
"$BIN" --press --period "$PERIOD" --slack 2048 --edges 1 --hold-cycles $((PERIOD * 3))
echo "[ok] NOR disk N=$N paused while the button was held"
# Twelve on-edges is past the eighth, where the heap would have run out.
# Collect runs on the fourth on-edge and stretches that half. The
# three-edge run above is the period. This run only has to keep going.
"$BIN" --edges 24
echo "[ok] NOR disk still blinking after the heap would have run out"
# Reopening the file searches the directory, which is still a disk read.
# That read is about 35 ms, so a 1 ms half would queue a burst. A 100 ms
# file halves to 50 ms, and the copy finishes inside the half. The third
# rising edge is edge 5. The four gaps before it are 100 ms. The next
# two are 50 ms. Edge 7 is the fourth rise, where Collect runs, so this
# run stops on that edge.
SWITCH=100
SWITCH_PERIOD=$((SWITCH * 27000))
python3 - "$ROOT/sim/out/disk.bin" "$ROOT/sim/out/disk-rate-switch.bin" "$SWITCH" << 'PY'
import sys
sys.path.insert(0, "tools")
from build_disk_image import set_rate
src, dst, delay = sys.argv[1:]
open(dst, "wb").write(set_rate(open(src, "rb").read(), int(delay)))
print(f"[ok] switch disk {delay} ms")
PY
cp "$ROOT/sim/out/disk.bin" "$ROOT/sim/out/disk-rate-base.bin"
cp "$ROOT/sim/out/disk-rate-switch.bin" "$ROOT/sim/out/disk.bin"
"$BIN" --period "$SWITCH_PERIOD" --period2 $((SWITCH_PERIOD / 2)) \
  --switch-after 4 --slack 2048 --edges 7
echo "[ok] NOR disk halves 100 ms after the third rise"
cp "$ROOT/sim/out/disk-rate-base.bin" "$ROOT/sim/out/disk.bin"

# A second delay, same elaborated image. The file's next word is the
# negation, so the checksum and the arm word stay put.
ALT=$((N + 2))
ALT_PERIOD=$((ALT * 27000))
python3 - "$ROOT/sim/out/disk.bin" "$ROOT/sim/out/disk-rate-alt.bin" "$ALT" << 'PY'
import struct
import sys
sys.path.insert(0, "tools")
from build_disk_image import checksum, set_rate
src_path, dst_path, delay = sys.argv[1:]
delay = int(delay)
src = open(src_path, "rb").read()
alt = set_rate(src, delay)
needle = struct.pack("<ii", delay, -delay)
at = alt.find(needle)
diffs = [i for i, (a, b) in enumerate(zip(src, alt)) if a != b]
if (
    len(src) != len(alt) or at < 0 or not diffs
    or any(i < at or i >= at + 8 for i in diffs)
):
    raise SystemExit(f"rate disks differ in {len(diffs)} bytes, lengths {len(src)} {len(alt)}")
if checksum(src[20:]) != checksum(alt[20:]):
    raise SystemExit("rate disks have different checksums")
open(dst_path, "wb").write(alt)
print(f"[ok] second rate {delay} ms differs in {len(diffs)} rate bytes, checksum held")
PY
cp "$ROOT/sim/out/disk.bin" "$ROOT/sim/out/disk-rate-base.bin"
cp "$ROOT/sim/out/disk-rate-alt.bin" "$ROOT/sim/out/disk.bin"
"$BIN" --period "$ALT_PERIOD" --slack 2048 --edges 3
echo "[ok] NOR disk N=$ALT period $ALT_PERIOD, same image"
cp "$ROOT/sim/out/disk-rate-base.bin" "$ROOT/sim/out/disk.bin"

python3 "$ROOT/sim/link_inner.py" \
  --flash-boot \
  --no-collect \
  --max-iter "$N" \
  --out "$ROOT/sim/visualizer/imem/modules.words"
if ! SIM_IMAGE=modules mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "error: CPUSimTop elaboration failed" >&2
  exit 1
fi
verilator "${VERILATOR_FLAGS[@]}" \
  "$ROOT/generated/CPUSimTopHyper.v" \
  "$ROOT/generated/InstrRom.v" \
  "$ROOT/generated/HwMul.v" \
  "$ROOT/sim/HyperRamUserModel.v" \
  "$ROOT/sim/CpuClock2.v" \
  "$ROOT/gowin/KeepBit.v" \
  "$ROOT/sim/LUT2.v" \
  "$ROOT/sim/spi_disk_model.v" \
  "$ROOT/gowin/button_gate.v" \
  "$ROOT/sim/disk_boot_top.v" \
  "$ROOT/sim/tb_disk_boot.cpp"
"$BIN" --exhaust-rises 8
echo "[ok] NOR disk goes dark at rise 8 without the collector"
