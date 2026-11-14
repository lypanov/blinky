#!/usr/bin/env bash
# Capture HDMI from the UGREEN stick while a board load runs.
# Open /dev/video0 first, then load, so the stick re-locks when HDMI drops.
#
#   tools/hdmi_capture.sh --board dock --out DIR --frames 1800 -- \
#       tools/load_dock.py BITSTREAM.fs DISK.bin
#   tools/hdmi_capture.sh --board nano --out DIR --frames 1800 -- \
#       tools/load_nano.py --sram-only BITSTREAM.fs
set -euo pipefail

DEVICE="${DEVICE:-/dev/video0}"
BOARD=""
OUTDIR=""
FRAMES=1800

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --board) BOARD="$2"; shift 2 ;;
    --out) OUTDIR="$2"; shift 2 ;;
    --frames) FRAMES="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "unknown argument: $1" >&2; usage 1 ;;
  esac
done
LOAD_CMD=("$@")

case "$BOARD" in
  nano|4k) WIDTH=720; HEIGHT=480 ;;
  dock|20k) WIDTH=1024; HEIGHT=768 ;;
  *) echo "pass --board nano|dock" >&2; usage 1 ;;
esac
if [[ -z "$OUTDIR" ]]; then
  echo "pass --out DIR" >&2; usage 1
fi
if [[ ${#LOAD_CMD[@]} -eq 0 ]]; then
  echo "pass -- then the load command (load_dock.py / load_nano.py)" >&2
  usage 1
fi

mkdir -p "$OUTDIR"
LOG="$OUTDIR/capture.log"
YUYV="$OUTDIR/hdmi.yuyv"

# Drain the stick's last lock (often 5 leftover frames), then the board size at 60.
v4l2-ctl -d "$DEVICE" --set-fmt-video=width=1920,height=1080,pixelformat=MJPG >/dev/null
v4l2-ctl -d "$DEVICE" --set-parm=30 >/dev/null
ffmpeg -hide_banner -loglevel error -y -nostdin \
  -f v4l2 -input_format mjpeg -video_size 1920x1080 -i "$DEVICE" \
  -vframes 4 -f null - || true
v4l2-ctl -d "$DEVICE" --set-fmt-video=width=${WIDTH},height=${HEIGHT},pixelformat=YUYV
v4l2-ctl -d "$DEVICE" --set-parm=60
v4l2-ctl -d "$DEVICE" --get-fmt-video --get-parm > "$OUTDIR/fmt.txt"

date "+REC %F %T %Z" | tee "$LOG"
ffmpeg -hide_banner -y -nostdin \
  -f v4l2 -input_format yuyv422 -video_size "${WIDTH}x${HEIGHT}" -framerate 60 \
  -i "$DEVICE" -vframes "$FRAMES" -f rawvideo "$YUYV" \
  >"$OUTDIR/ffmpeg.log" 2>&1 &
FFPID=$!
trap 'kill "$FFPID" 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
  if grep -q 'Output #0' "$OUTDIR/ffmpeg.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$FFPID" 2>/dev/null; then
    echo "ffmpeg exited before the load" | tee -a "$LOG"
    wait "$FFPID" || true
    exit 1
  fi
  sleep 0.2
done

date "+LOAD_START %F %T %Z" | tee -a "$LOG"
set +e
"${LOAD_CMD[@]}" | tee "$OUTDIR/load.log"
LOAD_RC=${PIPESTATUS[0]}
set -e
date "+LOAD_DONE rc=$LOAD_RC %F %T %Z" | tee -a "$LOG"

wait "$FFPID"
FF_RC=$?
trap - EXIT
echo "FFMPEG_EXIT:$FF_RC" | tee -a "$LOG"
if [[ "$FF_RC" -ne 0 ]]; then
  exit "$FF_RC"
fi
if [[ "$LOAD_RC" -ne 0 ]]; then
  exit "$LOAD_RC"
fi

python3 - "$YUYV" "$WIDTH" "$HEIGHT" <<'PY'
import hashlib, sys
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
w, h = int(sys.argv[2]), int(sys.argv[3])
fb = w * h * 2
n = len(raw) // fb
skip = min(8, n)
hashes, sq = set(), set()
for i in range(skip, n):
    pix = raw[i * fb : (i + 1) * fb]
    hashes.add(hashlib.sha256(pix).hexdigest())
    y = pix[0::2]
    nwhite = 0
    for row in range(20):
        rowb = y[(220 + row) * w + 300 : (220 + row) * w + 320]
        nwhite += sum(1 for p in rowb if p >= 200)
    sq.add(nwhite)
lo, hi = min(sq), max(sq)
print(f"frames {n} skip {skip} unique {len(hashes)} square {lo}..{hi}")
if len(hashes) < 4 or hi < 350 or lo > 20:
    sys.exit("HDMI did not blink (need changing hashes and square 0 then ~400)")
PY
echo "wrote $YUYV"
