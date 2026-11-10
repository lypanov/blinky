#!/usr/bin/env bash
# Symbol and timing check for flash, square, and text. No CPU, no DDR3, no board.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 "$ROOT/tools/font8x8.py" --check
verilator --cc --exe --build \
  -DVIDEO_SIM \
  --top-module video \
  -Wno-fatal -Wno-UNUSED \
  --Mdir "$ROOT/sim/obj_dir_video" \
  -o video_sym \
  "$ROOT/gowin/video.v" \
  "$ROOT/sim/tb_video.cpp"
"$ROOT/sim/obj_dir_video/video_sym"

verilator --cc --exe --build \
  -DVIDEO_SIM -DVIDEO_SQUARE \
  --top-module video \
  -Wno-fatal -Wno-UNUSED \
  --Mdir "$ROOT/sim/obj_dir_video_sq" \
  -o video_sq \
  "$ROOT/gowin/video.v" \
  "$ROOT/sim/tb_video_square.cpp"
"$ROOT/sim/obj_dir_video_sq/video_sq"

verilator --cc --exe --build \
  -DVIDEO_SIM -DVIDEO_SQUARE -DVIDEO_TEXT \
  --top-module video \
  -Wno-fatal -Wno-UNUSED \
  --Mdir "$ROOT/sim/obj_dir_video_tx" \
  -o video_tx \
  "$ROOT/gowin/video.v" \
  "$ROOT/sim/tb_video_text.cpp"
"$ROOT/sim/obj_dir_video_tx/video_tx"
