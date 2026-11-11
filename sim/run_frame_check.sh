#!/usr/bin/env bash
# One frame at a chosen CPU cycle, compared with a host-drawn picture.
# Flash and square on both boards, and the Dock counter. The digits
# are the four registers. The Nano is 720×480, 1 CPU clock per 2
# pixel clocks. The Dock is 1024×768, 215 CPU clocks per 576 pixel
# clocks (24.1875 MHz and 64.8 MHz).
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
build flash_dock -DVIDEO_DOCK -CFLAGS "-std=c++17 -O2 -DVIDEO_DOCK"
build sq_dock -DVIDEO_DOCK -DVIDEO_SQUARE -DFRAME_CHECK \
  -CFLAGS "-std=c++17 -O2 -DFRAME_SQUARE -DVIDEO_DOCK"
build tx -DVIDEO_DOCK -DVIDEO_SQUARE -DVIDEO_TEXT -DFRAME_CHECK \
  -CFLAGS "-std=c++17 -O2 -DFRAME_SQUARE -DFRAME_TEXT -DVIDEO_DOCK"

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
FLASH_DOCK="$ROOT/sim/obj_dir_frame_flash_dock/frame_flash_dock"
SQ_DOCK="$ROOT/sim/obj_dir_frame_sq_dock/frame_sq_dock"
TX="$ROOT/sim/obj_dir_frame_tx/frame_tx"
PY=(python3 "$ROOT/tools/frame_expect.py")
NANO_SIZE=(--width 720 --height 480)
DOCK_SIZE=(--width 1024 --height 768)

grab "$FLASH" nano 32 "$OUT/nano-flash-off.ppm"
grab "$FLASH" nano 200 "$OUT/nano-flash-on.ppm" --led-cycle 64
grab "$SQ" nano 32 "$OUT/nano-square-off.ppm" --status-cycle 2 --status-word 0x1A5
grab "$SQ" nano 200 "$OUT/nano-square-on.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x1A5
grab "$SQ" nano 200 "$OUT/nano-square-blank.ppm" \
  --led-cycle 64 --store-cycle 64 --blank-cycle 128 --status-cycle 2 --status-word 0x1A5
# 0xA5 with the square store still armed. Bit 8 is clear, so the
# blocks show and the square does not.
grab "$SQ" nano 200 "$OUT/nano-status-a5.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0xA5
grab "$FLASH_DOCK" dock 32 "$OUT/dock-flash-off.ppm"
grab "$FLASH_DOCK" dock 200 "$OUT/dock-flash-on.ppm" --led-cycle 64
grab "$SQ_DOCK" dock 32 "$OUT/dock-square-off.ppm" --status-cycle 2 --status-word 0x1A5
grab "$SQ_DOCK" dock 200 "$OUT/dock-square-on.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x1A5
grab "$SQ_DOCK" dock 200 "$OUT/dock-square-blank.ppm" \
  --led-cycle 64 --store-cycle 64 --blank-cycle 128 --status-cycle 2 --status-word 0x1A5
grab "$SQ_DOCK" dock 200 "$OUT/dock-status-a5.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0xA5
# The 4K build stops at square, so the same on-store draws no digits.
grab "$SQ" nano 200 "$OUT/nano-counter.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x1A5
grab "$TX" dock 32 "$OUT/dock-counter-off.ppm" --status-cycle 2 --status-word 0x1A5
grab "$TX" dock 200 "$OUT/dock-counter-on.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x1A5
grab "$TX" dock 200 "$OUT/dock-counter-blank.ppm" \
  --led-cycle 64 --store-cycle 64 --blank-cycle 128 --status-cycle 2 --status-word 0x1A5
grab "$TX" dock 200 "$OUT/dock-status-a5-text.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0xA5
# Index trap: bit 7 and bit 0. Bit 8 stays clear, so the square stays off.
grab "$SQ" nano 200 "$OUT/nano-status-81.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x81
grab "$SQ_DOCK" dock 200 "$OUT/dock-status-81.ppm" \
  --led-cycle 64 --store-cycle 64 --status-cycle 2 --status-word 0x81

cmp -s "$OUT/nano-counter.ppm" "$OUT/nano-square-on.ppm"

check() {
  "${PY[@]}" --got "$1" --kind "$2" "${@:3}"
}

check "$OUT/nano-flash-off.ppm" flash "${NANO_SIZE[@]}"
check "$OUT/nano-flash-on.ppm" flash --flash-white "${NANO_SIZE[@]}"
check "$OUT/nano-square-off.ppm" square "${NANO_SIZE[@]}"
check "$OUT/nano-square-on.ppm" square --square "${NANO_SIZE[@]}"
check "$OUT/nano-square-blank.ppm" square --square --blank "${NANO_SIZE[@]}"
check "$OUT/dock-flash-off.ppm" flash "${DOCK_SIZE[@]}"
check "$OUT/dock-flash-on.ppm" flash --flash-white "${DOCK_SIZE[@]}"
check "$OUT/dock-square-off.ppm" square "${DOCK_SIZE[@]}"
check "$OUT/dock-square-on.ppm" square --square "${DOCK_SIZE[@]}"
check "$OUT/dock-square-blank.ppm" square --square --blank "${DOCK_SIZE[@]}"
check "$OUT/nano-status-a5.ppm" status --byte 0xA5 "${NANO_SIZE[@]}"
check "$OUT/dock-status-a5.ppm" status --byte 0xA5 "${DOCK_SIZE[@]}"
check "$OUT/dock-status-a5-text.ppm" status --byte 0xA5 "${DOCK_SIZE[@]}"
check "$OUT/nano-status-a5.ppm" status --byte 0x5A --must-differ "${NANO_SIZE[@]}"
check "$OUT/nano-status-81.ppm" status --byte 0x81 "${NANO_SIZE[@]}"
check "$OUT/dock-status-81.ppm" status --byte 0x81 "${DOCK_SIZE[@]}"
check "$OUT/nano-status-81.ppm" status --byte 0xA5 --must-differ "${NANO_SIZE[@]}"
check "$OUT/nano-counter.ppm" square --square "${NANO_SIZE[@]}"
# The bitmap is the whole picture. The digit glyphs stay off it.
check "$OUT/dock-counter-off.ppm" square "${DOCK_SIZE[@]}"
check "$OUT/dock-counter-on.ppm" square --square "${DOCK_SIZE[@]}"
check "$OUT/dock-counter-blank.ppm" square --square --blank "${DOCK_SIZE[@]}"

# A wrong expected picture must fail. The digits are one count high,
# and the flash field is black where the capture is white.
check "$OUT/dock-counter-on.ppm" text --count 2 --square --must-differ "${DOCK_SIZE[@]}"
check "$OUT/nano-flash-on.ppm" flash --must-differ "${NANO_SIZE[@]}"

echo "ok frame check"
