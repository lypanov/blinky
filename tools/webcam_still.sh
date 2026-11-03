#!/usr/bin/env bash
# Grab one still from the Logitech QuickCam. Image only, never video.
set -euo pipefail
DEVICE="${DEVICE:-/dev/video0}"
OUT="${1:?usage: webcam_still.sh <out.jpg>}"
mkdir -p "$(dirname "$OUT")"
ffmpeg -hide_banner -loglevel error -y \
  -f v4l2 -video_size 640x480 -i "$DEVICE" \
  -frames:v 1 "$OUT"
ls -l "$OUT"
