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
