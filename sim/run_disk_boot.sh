#!/usr/bin/env bash
# SPI-disk boot sim. Not the DDR3 bench and not the ROM-only Blink path.
# Usage: sim/run_disk_boot.sh [max-iter]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
N="${1:-5}"
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
  "$ROOT/sim/disk_boot_top.v" \
  "$ROOT/sim/tb_disk_boot.cpp"

BIN="$ROOT/sim/obj_dir_disk/disk_boot"
PERIOD=$((466 * N + 780))
echo "[ok] elaborated N=$N period=$PERIOD  binary sim/obj_dir_disk/disk_boot"
"$BIN" --period "$PERIOD" --edges 3
echo "[ok] NOR disk N=$N period $PERIOD"
