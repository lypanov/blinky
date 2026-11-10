#!/usr/bin/env bash
# Dock UART disk boot, on the HyperRAM stand-in. Not the Micron PHY.
# The argument is the millisecond wait. The Dock counter averages
# 24187.5 cpu clocks per ms. Even N is N*24187.5 cpu clocks, times 2
# bridge clocks: N*48375 bridge cycles between edges.
# Usage: sim/run_uart_disk.sh [milliseconds]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
N="${1:-2}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
export PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"

MAP="$ROOT/sim/visualizer/imem/core.map"
WORDS="$ROOT/sim/visualizer/imem/modules.words"
DISK="$ROOT/sim/out/disk.bin"
mkdir -p "$ROOT/sim/out"

python3 "$ROOT/sim/link_inner.py" \
  --uart-disk \
  --max-iter "$N" \
  --out "$WORDS"
cp "$DISK" "$ROOT/sim/out/disk_uart.bin"
cp "$MAP" "$ROOT/sim/out/core_uart.map"

python3 "$ROOT/sim/link_inner.py" \
  --flash-boot \
  --max-iter "$N" \
  --out "$ROOT/sim/out/flash_boot.words"
cmp "$DISK" "$ROOT/sim/out/disk_uart.bin"
echo "[ok] UART disk bytes match the 4K flash disk"

cp "$ROOT/sim/out/core_uart.map" "$MAP"
cp "$ROOT/sim/out/disk_uart.bin" "$DISK"
python3 "$ROOT/sim/link_inner.py" \
  --uart-disk \
  --max-iter "$N" \
  --out "$WORDS"
cmp "$DISK" "$ROOT/sim/out/disk_uart.bin"

if ! SIM_IMAGE=modules mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "error: CPUSimTop elaboration failed" >&2
  exit 1
fi

VERILATOR_FLAGS=(
  --cc --exe --build
  --top-module uart_disk_top
  --timescale 1ns/1ps
  -DPRINTF_COND=0
  -Wno-fatal
  -Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND
  -Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING
  -CFLAGS "-std=c++17 -O2"
  --Mdir "$ROOT/sim/obj_dir_uart_disk"
  -o uart_disk
)

verilator "${VERILATOR_FLAGS[@]}" \
  "$ROOT/generated/CPUSimTopHyper.v" \
  "$ROOT/generated/InstrRom.v" \
  "$ROOT/sim/HyperRamUserModel.v" \
  "$ROOT/sim/CpuClock2.v" \
  "$ROOT/gowin/KeepBit.v" \
  "$ROOT/sim/LUT2.v" \
  "$ROOT/gowin/uart_word_rx.v" \
  "$ROOT/gowin/button_gate.v" \
  "$ROOT/sim/uart_disk_top.v" \
  "$ROOT/sim/tb_uart_disk.cpp"

BIN="$ROOT/sim/obj_dir_uart_disk/uart_disk"
if (( N % 2 )); then
  echo "error: millisecond wait $N must be even" >&2
  exit 1
fi
PERIOD=$((N * 48375))
echo "[ok] elaborated N=$N ms period=$PERIOD"

"$BIN" --period "$PERIOD" --slack 2048 --edges 3 --min-pc 0x900
echo "[ok] UART disk N=$N period $PERIOD, button released"
# 0x01 is the Dock press byte. The LED stays on, then 0x00 resumes it.
"$BIN" --press --period "$PERIOD" --slack 2048 --edges 1 --min-pc 0x900 \
  --hold-cycles $((PERIOD * 3)) --bit-clocks 210

python3 - "$DISK" "$ROOT/sim/out/disk_bad_build.bin" "$ROOT/sim/out/disk_bad_byte.bin" << 'PY'
import sys
good, bad_build, bad_byte = sys.argv[1:]
data = bytearray(open(good, "rb").read())
data[8] ^= 0x01
open(bad_build, "wb").write(data)
data = bytearray(open(good, "rb").read())
data[40] ^= 0x01
open(bad_byte, "wb").write(data)
PY

"$BIN" --expect-halt +disk="$ROOT/sim/out/disk_bad_build.bin"
"$BIN" --expect-halt +disk="$ROOT/sim/out/disk_bad_byte.bin"
echo "[ok] UART disk N=$N period $PERIOD, bad build dark, flipped byte dark"
