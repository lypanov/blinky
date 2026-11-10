#!/usr/bin/env bash
# One frame at a chosen CPU cycle, compared with a host-drawn picture.
# Flash and square on both boards, and the Dock counter. The digits
# are the four registers. Nano is 1 CPU clock per 2 pixel clocks.
# Dock is 43 CPU clocks per 48 pixel clocks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/sim/out/frames"
mkdir -p "$OUT"

build() {
  local name="$1"
  shift
  verilator --cc --exe --build \
    -DVIDEO_SIM \
    "$@" \
    --top-module video \
    -Wno-fatal -Wno-UNUSED \
    --Mdir "$ROOT/sim/obj_dir_frame_${name}" \
    -o "frame_${name}" \
    "$ROOT/gowin/video.v" \
    "$ROOT/sim/tb_frame.cpp"
}

build flash -CFLAGS "-std=c++17 -O2"
build sq -DVIDEO_SQUARE -DFRAME_CHECK -CFLAGS "-std=c++17 -O2 -DFRAME_SQUARE"
build tx -DVIDEO_SQUARE -DVIDEO_TEXT -DFRAME_CHECK \
  -CFLAGS "-std=c++17 -O2 -DFRAME_SQUARE -DFRAME_TEXT"

# Capture cycle, then the level changes that are already in force.
# Arm rises at CPU cycle 2. The on-store and the LED rise at 64.
# Blank, when asked, rises at 128. The off picture is cycle 32.
grab() {
  local bin="$1" board="$2" cycle="$3" dest="$4"
  shift 4
  "$bin" --board "$board" --cycle "$cycle" --out "$dest" "$@"
}

FLASH="$ROOT/sim/obj_dir_frame_flash/frame_flash"
SQ="$ROOT/sim/obj_dir_frame_sq/frame_sq"
TX="$ROOT/sim/obj_dir_frame_tx/frame_tx"
PY=(python3 "$ROOT/tools/frame_expect.py")

for board in nano dock; do
  grab "$FLASH" "$board" 32 "$OUT/${board}-flash-off.ppm"
  grab "$FLASH" "$board" 200 "$OUT/${board}-flash-on.ppm" --led-cycle 64
  grab "$SQ" "$board" 32 "$OUT/${board}-square-off.ppm"
  grab "$SQ" "$board" 200 "$OUT/${board}-square-on.ppm" --led-cycle 64 --store-cycle 64
  grab "$SQ" "$board" 200 "$OUT/${board}-square-blank.ppm" \
    --led-cycle 64 --store-cycle 64 --blank-cycle 128
done
# The 4K build stops at square, so the same on-store draws no digits.
grab "$SQ" nano 200 "$OUT/nano-counter.ppm" --led-cycle 64 --store-cycle 64
grab "$TX" dock 32 "$OUT/dock-counter-off.ppm"
grab "$TX" dock 200 "$OUT/dock-counter-on.ppm" --led-cycle 64 --store-cycle 64
grab "$TX" dock 200 "$OUT/dock-counter-blank.ppm" \
  --led-cycle 64 --store-cycle 64 --blank-cycle 128

cmp -s "$OUT/nano-flash-on.ppm" "$OUT/dock-flash-on.ppm"
cmp -s "$OUT/nano-flash-off.ppm" "$OUT/dock-flash-off.ppm"
cmp -s "$OUT/nano-square-on.ppm" "$OUT/dock-square-on.ppm"
cmp -s "$OUT/nano-square-off.ppm" "$OUT/dock-square-off.ppm"
cmp -s "$OUT/nano-counter.ppm" "$OUT/nano-square-on.ppm"

check() {
  "${PY[@]}" --got "$1" --kind "$2" "${@:3}"
}

for board in nano dock; do
  check "$OUT/${board}-flash-off.ppm" flash
  check "$OUT/${board}-flash-on.ppm" flash --flash-white
  check "$OUT/${board}-square-off.ppm" square
  check "$OUT/${board}-square-on.ppm" square --square
  check "$OUT/${board}-square-blank.ppm" square --square --blank
done
check "$OUT/nano-counter.ppm" square --square
check "$OUT/dock-counter-off.ppm" text --count 0
check "$OUT/dock-counter-on.ppm" text --count 1 --square
check "$OUT/dock-counter-blank.ppm" text --count 1 --square --blank

# A wrong expected picture must fail. The digits are one count high,
# and the flash field is black where the capture is white.
check "$OUT/dock-counter-on.ppm" text --count 2 --square --must-differ
check "$OUT/nano-flash-on.ppm" flash --must-differ

echo "ok frame check"
