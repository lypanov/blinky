#!/usr/bin/env bash
# Build one Nano 4K flash-disk reader image. Does not program the FPGA.
# The bitstream is SRAM-loaded (.fs). Never pass a flash-writing flag.
#
# Usage:
#   tools/gowin_build_spidisk.sh read
#   tools/gowin_build_spidisk.sh neg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHICH="${1:-read}"
case "$WHICH" in
  read) NAME=spi_disk_read ;;
  neg)  NAME=spi_disk_neg ;;
  *)
    echo "error: image must be read or neg" >&2
    exit 1
    ;;
esac

if [[ -z "${DISPLAY:-}" && -S /tmp/.X11-unix/X0 ]]; then
  export DISPLAY=:0
fi
if [[ -z "${QT_QPA_PLATFORM:-}" || "${QT_QPA_PLATFORM}" == "wayland;xcb" || "${QT_QPA_PLATFORM}" == "wayland" ]]; then
  export QT_QPA_PLATFORM=xcb
fi
if [[ "${QT_QPA_PLATFORM}" == "offscreen" ]]; then
  echo "error: QT_QPA_PLATFORM=offscreen crashes gw_sh; unset it or use xcb" >&2
  exit 1
fi
if ! command -v gw_sh >/dev/null 2>&1; then
  echo "error: gw_sh not on PATH" >&2
  exit 1
fi

cp "$ROOT/gowin/spi_disk_cfg_${WHICH}.vh" "$ROOT/gowin/spi_disk_cfg.vh"
export GOWIN_OUT_NAME="$NAME"
echo "==> Gowin syn+PNR disk reader image=$WHICH out=$NAME"
rm -rf "$ROOT/gowin/impl"
mkdir -p "$ROOT/gowin/impl"
cd "$ROOT/gowin"
gw_sh "$ROOT/gowin/gowin_build_spidisk.tcl"
FS="$ROOT/gowin/impl/pnr/${NAME}.fs"
if [[ ! -f "$FS" ]]; then
  echo "error: expected $FS was not produced" >&2
  find "$ROOT/gowin/impl" -name '*.fs' -type f || true
  exit 1
fi
mkdir -p "$ROOT/gowin/spi-fs"
cp -f "$FS" "$ROOT/gowin/spi-fs/${NAME}.fs"
cp -f "$ROOT/gowin/impl/pnr/${NAME}.rpt.txt" "$ROOT/gowin/spi-fs/${NAME}.rpt.txt"
echo "==> Bitstream $ROOT/gowin/spi-fs/${NAME}.fs"
echo "SRAM load only (never flash this file):"
echo "  openFPGALoader --busdev-num 003:081 -b tangnano4k -m $ROOT/gowin/spi-fs/${NAME}.fs"
echo "Do NOT pass -f / --write-flash / --external-flash for this bitstream."
python3 - "$ROOT/gowin/spi-fs/${NAME}.rpt.txt" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
for line in text:
    if "|" in line and any(k in line for k in ("Logic", "CLS", "BSRAM", "Register", "LUT", "ALU")):
        print(line.rstrip())
PY
