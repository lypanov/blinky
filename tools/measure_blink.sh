#!/usr/bin/env bash
# Record the Tang Nano 4K LED from a V4L2 camera and measure blink rate.
# Does not program the FPGA. Does not use sudo.
#
# Usage:
#   tools/measure_blink.sh
#   tools/measure_blink.sh --duration 25 --warmup 8
#   tools/measure_blink.sh --video /path/to/clip.mkv   # analyze an existing clip
#   tools/measure_blink.sh --roi x,y,w,h
#   tools/measure_blink.sh --self-test
#
# Writes JSON + brightness.png + roi.png under ~/fpga/blink-measure/<timestamp>/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/usr/bin/python3}"
DEVICE="${DEVICE:-/dev/video0}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"
FPS="${FPS:-30}"
WARMUP="${WARMUP:-8}"
DURATION="${DURATION:-25}"
PIXELFORMAT="${PIXELFORMAT:-MJPG}"   # v4l2 fourcc; ffmpeg uses mjpeg
OUTDIR=""
VIDEO=""
ROI=""
SELF_TEST=0

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --width) WIDTH="$2"; shift 2 ;;
    --height) HEIGHT="$2"; shift 2 ;;
    --fps) FPS="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --pixelformat) PIXELFORMAT="$2"; shift 2 ;;
    --outdir) OUTDIR="$2"; shift 2 ;;
    --video) VIDEO="$2"; shift 2 ;;
    --roi) ROI="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    *) echo "unknown argument: $1" >&2; usage 1 ;;
  esac
done

if [[ ! -x "$PYTHON" ]]; then
  echo "error: need $PYTHON (system matplotlib). mise/pyenv python3 will not work." >&2
  exit 1
fi

if [[ "$SELF_TEST" -eq 1 ]]; then
  exec "$PYTHON" "$ROOT/tools/analyze_blink.py" --self-test
fi

if [[ -z "$OUTDIR" ]]; then
  OUTDIR="${HOME}/fpga/blink-measure/$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$OUTDIR"
LOG="$OUTDIR/capture.log"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not on PATH" >&2; exit 1; }
}
need ffmpeg
need ffprobe

ANALYZER=("$PYTHON" "$ROOT/tools/analyze_blink.py" --outdir "$OUTDIR" --warmup "$WARMUP")
[[ -n "$ROI" ]] && ANALYZER+=(--roi "$ROI")

restore_camera() { :; }

if [[ -z "$VIDEO" ]]; then
  need v4l2-ctl
  [[ -e "$DEVICE" ]] || { echo "error: $DEVICE does not exist" >&2; exit 1; }

  # Snapshot controls so we can put the camera back. Never leave Manual
  # exposure stuck if the script dies mid-capture.
  orig_ae="$(v4l2-ctl -d "$DEVICE" --get-ctrl=auto_exposure 2>/dev/null | awk -F': ' '{print $2}' || true)"
  orig_ex="$(v4l2-ctl -d "$DEVICE" --get-ctrl=exposure_time_absolute 2>/dev/null | awk -F': ' '{print $2}' || true)"
  orig_edf="$(v4l2-ctl -d "$DEVICE" --get-ctrl=exposure_dynamic_framerate 2>/dev/null | awk -F': ' '{print $2}' || true)"
  orig_awb="$(v4l2-ctl -d "$DEVICE" --get-ctrl=white_balance_automatic 2>/dev/null | awk -F': ' '{print $2}' || true)"
  orig_gain="$(v4l2-ctl -d "$DEVICE" --get-ctrl=gain 2>/dev/null | awk -F': ' '{print $2}' || true)"

  restore_camera() {
    [[ -n "${orig_ae:-}" ]] && v4l2-ctl -d "$DEVICE" --set-ctrl=auto_exposure="$orig_ae" >/dev/null 2>&1 || true
    [[ -n "${orig_edf:-}" ]] && v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_dynamic_framerate="$orig_edf" >/dev/null 2>&1 || true
    [[ -n "${orig_awb:-}" ]] && v4l2-ctl -d "$DEVICE" --set-ctrl=white_balance_automatic="$orig_awb" >/dev/null 2>&1 || true
    [[ -n "${orig_gain:-}" ]] && v4l2-ctl -d "$DEVICE" --set-ctrl=gain="$orig_gain" >/dev/null 2>&1 || true
    # exposure_time_absolute is inactive in auto modes; set it only if we can.
    [[ -n "${orig_ex:-}" ]] && v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_time_absolute="$orig_ex" >/dev/null 2>&1 || true
  }

  lock_exposure() {
    # Menu: 1 = Manual Mode, 3 = Aperture Priority. Disable dynamic fps so
    # the measured rate is not beating against a hunting frame clock.
    v4l2-ctl -d "$DEVICE" --set-ctrl=auto_exposure=1 >>"$LOG" 2>&1 || \
      echo "warning: could not set auto_exposure=1 (Manual)" | tee -a "$LOG" >&2
    if [[ -n "${orig_ex:-}" && "$orig_ex" != "0" ]]; then
      v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_time_absolute="$orig_ex" >>"$LOG" 2>&1 || \
        echo "warning: could not lock exposure_time_absolute=$orig_ex" | tee -a "$LOG" >&2
    else
      v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_time_absolute=166 >>"$LOG" 2>&1 || true
    fi
    v4l2-ctl -d "$DEVICE" --set-ctrl=exposure_dynamic_framerate=0 >>"$LOG" 2>&1 || \
      echo "warning: could not disable exposure_dynamic_framerate" | tee -a "$LOG" >&2
    v4l2-ctl -d "$DEVICE" --set-ctrl=white_balance_automatic=0 >>"$LOG" 2>&1 || true
    if [[ -n "${orig_gain:-}" ]]; then
      v4l2-ctl -d "$DEVICE" --set-ctrl=gain="$orig_gain" >>"$LOG" 2>&1 || true
    fi
  }

  ffmpeg_pid=""
  cleanup() {
    if [[ -n "${ffmpeg_pid:-}" ]] && kill -0 "$ffmpeg_pid" 2>/dev/null; then
      kill "$ffmpeg_pid" 2>/dev/null || true
      wait "$ffmpeg_pid" 2>/dev/null || true
    fi
    restore_camera
  }
  trap cleanup EXIT

  {
    echo "device=$DEVICE ${WIDTH}x${HEIGHT} fps=$FPS pix=$PIXELFORMAT"
    echo "warmup=${WARMUP}s duration=${DURATION}s outdir=$OUTDIR"
    v4l2-ctl -d "$DEVICE" --all || true
  } >>"$LOG" 2>&1

  v4l2-ctl -d "$DEVICE" --set-fmt-video="width=${WIDTH},height=${HEIGHT},pixelformat=${PIXELFORMAT}" >>"$LOG" 2>&1 || \
    echo "warning: could not set ${WIDTH}x${HEIGHT} ${PIXELFORMAT}" | tee -a "$LOG" >&2
  v4l2-ctl -d "$DEVICE" --set-parm="$FPS" >>"$LOG" 2>&1 || \
    echo "warning: could not set parm fps=$FPS" | tee -a "$LOG" >&2
  lock_exposure

  real_fps="$(v4l2-ctl -d "$DEVICE" --get-parm 2>/dev/null | awk '/Frames per second/ {print $4; exit}' || true)"
  echo "camera reports fps=${real_fps:-unknown} (requested $FPS)" | tee -a "$LOG"

  ff_fmt="mjpeg"
  [[ "$PIXELFORMAT" == "YUYV" ]] && ff_fmt="yuyv422"
  TOTAL="$(awk -v w="$WARMUP" -v d="$DURATION" 'BEGIN { printf "%.1f", w + d + 2 }')"
  VIDEO="$OUTDIR/clip.mkv"

  echo "recording ${TOTAL}s from $DEVICE (discard ${WARMUP}s warmup) -> $VIDEO" | tee -a "$LOG"
  # Copy MJPEG when the camera emits it; otherwise let ffmpeg encode.
  encode=(-c:v copy)
  [[ "$ff_fmt" != "mjpeg" ]] && encode=(-c:v mjpeg -q:v 4)

  start_ns="$(date +%s.%N)"
  ffmpeg -hide_banner -y \
    -f v4l2 -thread_queue_size 512 \
    -video_size "${WIDTH}x${HEIGHT}" -framerate "$FPS" -input_format "$ff_fmt" \
    -use_wallclock_as_timestamps 1 \
    -i "$DEVICE" \
    -t "$TOTAL" \
    "${encode[@]}" \
    "$VIDEO" >>"$LOG" 2>&1 &
  ffmpeg_pid=$!

  # ffmpeg's v4l2 open can reset UVC controls; lock again once streaming.
  sleep 2
  lock_exposure || true

  wait "$ffmpeg_pid"
  rc=$?
  ffmpeg_pid=""
  end_ns="$(date +%s.%N)"
  if [[ $rc -ne 0 || ! -s "$VIDEO" ]]; then
    echo "error: ffmpeg capture failed (exit $rc). See $LOG" >&2
    exit 1
  fi
  awk -v s="$start_ns" -v e="$end_ns" 'BEGIN { printf "wall_s=%.3f\n", e - s }' | tee -a "$LOG"
  restore_camera
  trap - EXIT
fi

echo "analyzing $VIDEO" | tee -a "$LOG"
"${ANALYZER[@]}" --video "$VIDEO" | tee "$OUTDIR/result.json.stdout"
echo ""
echo "wrote $OUTDIR"
echo "  json  $OUTDIR/result.json"
echo "  plot  $OUTDIR/brightness.png"
echo "  roi   $OUTDIR/roi.png"
