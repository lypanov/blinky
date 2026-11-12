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

python3 "$ROOT/tools/font_glyph.py" --check

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
cp "$DISK" "$ROOT/sim/out/disk_flash.bin"
python3 - "$ROOT/sim/out/disk_uart.bin" "$ROOT/sim/out/disk_flash.bin" << 'PY'
import sys

def core(path):
    data = open(path, "rb").read()
    image = bytearray(data[20 + 1024:])
    alloc = int.from_bytes(image[16:20], "little")
    if not 0 < alloc <= len(image):
        raise SystemExit(f"{path} alloc {alloc:#x} past {len(image)} bytes")
    # Address 28 is the sum of Blink5, which inlines this board's square.
    image[28:32] = b"\0\0\0\0"
    return data, bytes(image[:alloc])

uart, flash = sys.argv[1:]
du, cu = core(uart)
df, cf = core(flash)
if cu != cf:
    raise SystemExit("the boot cores of the two disks differ")
if du == df:
    raise SystemExit("the 4K and Dock disks are the same file")
print(f"[ok] disks differ, boot cores match ({len(cu)} bytes)")
PY

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
  --x-initial 0 --x-assign 0
  -CFLAGS "-std=c++17 -O2 -I$ROOT/sim"
  --Mdir "$ROOT/sim/obj_dir_uart_disk"
  -o uart_disk
)

verilator "${VERILATOR_FLAGS[@]}" \
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

BIN="$ROOT/sim/obj_dir_uart_disk/uart_disk"
# DDR3 trained and UART receive take the NOR read's place. The shared
# tail is magic, build, checksum, core, init, jump, then the inner core.
GOOD=(--expect-status 0x10B --status-seq 1,3,4,5,6,7,8,9,10,11,0x10B)
if (( N % 2 )); then
  echo "error: millisecond wait $N must be even" >&2
  exit 1
fi
PERIOD=$((N * 48375))
echo "[ok] elaborated N=$N ms period=$PERIOD"

"$BIN" --period "$PERIOD" --slack 2048 --edges 3 --min-pc 0x900 "${GOOD[@]}"
echo "[ok] UART disk N=$N period $PERIOD, button released"
# 0x01 is the Dock press byte. The LED stays on, then 0x00 resumes it.
"$BIN" --press --period "$PERIOD" --slack 2048 --edges 1 --min-pc 0x900 \
  --hold-cycles $((PERIOD * 3)) --bit-clocks 210 "${GOOD[@]}"

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

"$BIN" --expect-halt --expect-status 0x06 --status-seq 1,3,4,5,6 \
  +disk="$ROOT/sim/out/disk_bad_build.bin"
"$BIN" --expect-halt --expect-status 0x07 --status-seq 1,3,4,5,6,7 \
  +disk="$ROOT/sim/out/disk_bad_byte.bin"
echo "[ok] UART disk N=$N period $PERIOD, bad build dark, flipped byte dark"
# The list fills the heap before the arm word. Collect runs on the
# fourth on-edge and walks the list again. The three-edge run above is
# the period. This run only has to keep going.
"$BIN" --edges 24 --min-pc 0x900 "${GOOD[@]}"
echo "[ok] UART disk still blinking after Collect walked the list"
# Same third-rise change as the NOR bench. The directory search is the
# long part of the reopen, about 35 ms on the 4K clock and less here.
# 100 ms halves to 50, which covers it.
SWITCH=100
SWITCH_PERIOD=$((SWITCH * 48375))
python3 - "$DISK" "$ROOT/sim/out/disk-rate-switch.bin" "$SWITCH" << 'PY'
import sys
sys.path.insert(0, "tools")
from build_disk_image import set_rate
src, dst, delay = sys.argv[1:]
open(dst, "wb").write(set_rate(open(src, "rb").read(), int(delay)))
print(f"[ok] switch disk {delay} ms")
PY
"$BIN" --period "$SWITCH_PERIOD" --period2 $((SWITCH_PERIOD / 2)) \
  --switch-after 4 --slack 2048 --edges 7 --min-pc 0x900 \
  +disk="$ROOT/sim/out/disk-rate-switch.bin" "${GOOD[@]}"
echo "[ok] UART disk halves 100 ms after the third rise"

ALT=$((N + 2))
ALT_PERIOD=$((ALT * 48375))
python3 - "$DISK" "$ROOT/sim/out/disk-rate-alt.bin" "$ALT" << 'PY'
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
"$BIN" --period "$ALT_PERIOD" --slack 2048 --edges 3 --min-pc 0x900 \
  +disk="$ROOT/sim/out/disk-rate-alt.bin" "${GOOD[@]}"
echo "[ok] UART disk N=$ALT period $ALT_PERIOD, same image"

python3 "$ROOT/sim/link_inner.py" \
  --uart-disk \
  --index-trap \
  --max-iter "$N" \
  --out "$ROOT/sim/out/index-trap-uart.words"
cp "$DISK" "$ROOT/sim/out/disk-index-trap-uart.bin"
python3 "$ROOT/sim/link_inner.py" \
  --flash-boot \
  --index-trap \
  --max-iter "$N" \
  --out "$ROOT/sim/out/index-trap-flash.words"
python3 - "$DISK" "$ROOT/sim/out/disk-index-trap-uart.bin" << 'PY'
import sys

def core(path):
    data = open(path, "rb").read()
    image = bytearray(data[20 + 1024:])
    alloc = int.from_bytes(image[16:20], "little")
    if not 0 < alloc <= len(image):
        raise SystemExit(f"{path} alloc {alloc:#x}")
    image[28:32] = b"\0\0\0\0"
    return data, bytes(image[:alloc])

flash, uart = sys.argv[1:]
df, cf = core(flash)
du, cu = core(uart)
if cf != cu:
    raise SystemExit("index-trap boot cores differ")
if df == du:
    raise SystemExit("index-trap disks are the same file")
print(f"[ok] index-trap disks differ, boot cores match ({len(cf)} bytes)")
PY
"$BIN" --expect-halt --expect-no-arm --expect-status 0x81 --min-pc 0x900 \
  --status-seq 1,3,4,5,6,7,8,9,10,11,0x81 \
  +disk="$ROOT/sim/out/disk-index-trap-uart.bin"
echo "[ok] UART disk index trap is 81H, the arm word stays unstored, the LED stays dark"

python3 "$ROOT/sim/link_inner.py" \
  --uart-disk \
  --bad-font \
  --max-iter "$N" \
  --out "$ROOT/sim/out/bad-font-uart.words"
cp "$DISK" "$ROOT/sim/out/disk-bad-font-uart.bin"
"$BIN" --expect-halt --expect-no-arm --expect-status 0x81 --min-pc 0x900 \
  --status-seq 1,3,4,5,6,7,8,9,10,11,0x81 \
  +disk="$ROOT/sim/out/disk-bad-font-uart.bin"
echo "[ok] UART disk damaged font is 81H, the arm word stays unstored, the LED stays dark"

python3 "$ROOT/sim/link_inner.py" \
  --uart-disk \
  --short-heap \
  --max-iter "$N" \
  --out "$WORDS"
cp "$DISK" "$ROOT/sim/out/disk_uart_neg.bin"
cp "$MAP" "$ROOT/sim/out/core_uart_neg.map"
python3 "$ROOT/sim/link_inner.py" \
  --flash-boot \
  --short-heap \
  --max-iter "$N" \
  --out "$ROOT/sim/out/flash_boot_neg.words"
cmp "$ROOT/sim/out/disk_uart_neg.bin" "$ROOT/sim/out/disk_uart.bin"
cmp "$DISK" "$ROOT/sim/out/disk_flash.bin"
echo "[ok] short-heap ROM keeps each board's full disk"
cp "$ROOT/sim/out/core_uart_neg.map" "$MAP"
cp "$ROOT/sim/out/disk_uart_neg.bin" "$DISK"
if ! SIM_IMAGE=modules mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "error: CPUSimTop elaboration failed" >&2
  exit 1
fi
verilator "${VERILATOR_FLAGS[@]}" \
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
"$BIN" --expect-halt --expect-no-arm --min-pc 0x900 "${GOOD[@]}"
echo "[ok] UART disk one record short halts with the LED dark"
