#!/usr/bin/env bash
# Item 37. The heap fill and the one-record-short ROM.
# Not the button, the rate switch, the bad disk, or the index trap.
# Usage: sim/run_heap_limit.sh [milliseconds]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
N="${1:-2}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
if (( N % 2 )); then
  echo "error: millisecond wait $N must be even" >&2
  exit 1
fi

link() {
  python3 "$ROOT/sim/link_inner.py" "$@" --max-iter "$N"
}

elaborate() {
  if ! SIM_IMAGE=modules mill chisel-blinky.runMain gcd.CPUSimTop; then
    echo "error: CPUSimTop elaboration failed" >&2
    exit 1
  fi
}

build_nor() {
  verilator \
    --cc --exe --build \
    --top-module disk_boot_top \
    --timescale 1ns/1ps \
    -DPRINTF_COND=0 \
    -Wno-fatal \
    -Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
    -Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING \
    -CFLAGS "-std=c++17 -O2" \
    --Mdir "$ROOT/sim/obj_dir_disk" \
    -o disk_boot \
    "$ROOT/generated/CPUSimTopHyper.v" \
    "$ROOT/generated/InstrRom.v" \
    "$ROOT/generated/HwMul.v" \
    "$ROOT/generated/FpSnap.v" \
    "$ROOT/sim/HyperRamUserModel.v" \
    "$ROOT/sim/CpuClock2.v" \
    "$ROOT/gowin/KeepBit.v" \
    "$ROOT/sim/LUT2.v" \
    "$ROOT/sim/spi_disk_model.v" \
    "$ROOT/gowin/button_gate.v" \
    "$ROOT/sim/disk_boot_top.v" \
    "$ROOT/sim/tb_disk_boot.cpp"
}

build_uart() {
  verilator \
    --cc --exe --build \
    --top-module uart_disk_top \
    --timescale 1ns/1ps \
    -DPRINTF_COND=0 \
    -Wno-fatal \
    -Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
    -Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING \
    -CFLAGS "-std=c++17 -O2" \
    --Mdir "$ROOT/sim/obj_dir_uart_disk" \
    -o uart_disk \
    "$ROOT/generated/CPUSimTopHyper.v" \
    "$ROOT/generated/InstrRom.v" \
    "$ROOT/generated/HwMul.v" \
    "$ROOT/generated/FpSnap.v" \
    "$ROOT/sim/HyperRamUserModel.v" \
    "$ROOT/sim/CpuClock2.v" \
    "$ROOT/gowin/KeepBit.v" \
    "$ROOT/sim/LUT2.v" \
    "$ROOT/gowin/uart_word_rx.v" \
    "$ROOT/gowin/button_gate.v" \
    "$ROOT/sim/uart_disk_top.v" \
    "$ROOT/sim/tb_uart_disk.cpp"
}

WORDS="$ROOT/sim/visualizer/imem/modules.words"
DISK="$ROOT/sim/out/disk.bin"
mkdir -p "$ROOT/sim/out"

link --flash-boot --out "$WORDS"
cp "$DISK" "$ROOT/sim/out/disk-full.bin"
NOR_PERIOD=$((N * 27000))
NOR_GOOD=(--expect-status 0x10B --status-seq 1,2,5,6,7,8,9,10,11,0x10B)
elaborate
build_nor
NOR="$ROOT/sim/obj_dir_disk/disk_boot"
"$NOR" --period "$NOR_PERIOD" --slack 2048 --edges 3 "${NOR_GOOD[@]}"
echo "[ok] NOR disk N=$N period $NOR_PERIOD, heap filled"
"$NOR" --edges 24 "${NOR_GOOD[@]}"
echo "[ok] NOR disk still blinking after Collect walked the list"

link --flash-boot --short-heap --out "$WORDS"
cmp "$DISK" "$ROOT/sim/out/disk-full.bin"
echo "[ok] short-heap NOR ROM keeps the full disk"
elaborate
build_nor
"$NOR" --expect-halt --expect-no-arm "${NOR_GOOD[@]}"
echo "[ok] NOR disk one record short halts with the LED dark"

link --uart-disk --out "$WORDS"
cp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
link --flash-boot --out "$ROOT/sim/out/flash-full.words"
cmp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
echo "[ok] UART disk bytes match the NOR disk"
# The NOR link just overwrote the ROM words. Put the UART ROM back.
link --uart-disk --out "$WORDS"
cmp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
UART_PERIOD=$((N * 48375))
UART_GOOD=(--expect-status 0x10B --status-seq 1,3,4,5,6,7,8,9,10,11,0x10B)
elaborate
build_uart
UART="$ROOT/sim/obj_dir_uart_disk/uart_disk"
"$UART" --period "$UART_PERIOD" --slack 2048 --edges 3 --min-pc 0x900 "${UART_GOOD[@]}"
echo "[ok] UART disk N=$N period $UART_PERIOD, heap filled"
"$UART" --edges 24 --min-pc 0x900 "${UART_GOOD[@]}"
echo "[ok] UART disk still blinking after Collect walked the list"

link --uart-disk --short-heap --out "$WORDS"
cmp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
link --flash-boot --short-heap --out "$ROOT/sim/out/flash-short.words"
cmp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
echo "[ok] short-heap UART disk matches the full disk and the NOR short ROM's disk"
link --uart-disk --short-heap --out "$WORDS"
cmp "$DISK" "$ROOT/sim/out/disk-uart-full.bin"
elaborate
build_uart
"$UART" --expect-halt --expect-no-arm --min-pc 0x900 "${UART_GOOD[@]}"
echo "[ok] UART disk one record short halts with the LED dark"
