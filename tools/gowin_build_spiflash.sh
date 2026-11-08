#!/usr/bin/env bash
# Build one Nano 4K SPI-flash pathfinder image. Does not program the FPGA.
# The bitstream is SRAM-loaded (.fs). Never pass a flash-writing flag.
#
# Usage:
#   tools/gowin_build_spiflash.sh id
#   tools/gowin_build_spiflash.sh write
#   tools/gowin_build_spiflash.sh read
#   tools/gowin_build_spiflash.sh neg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHICH="${1:-id}"
case "$WHICH" in
  id)    NAME=spi_id ;;
  write) NAME=spi_write ;;
  read)  NAME=spi_read ;;
  neg)   NAME=spi_neg ;;
  *)
    echo "error: image must be id, write, read, or neg" >&2
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

cp "$ROOT/gowin/spi_flash_cfg_${WHICH}.vh" "$ROOT/gowin/spi_flash_cfg.vh"
export GOWIN_OUT_NAME="$NAME"
echo "==> Gowin syn+PNR SPI pathfinder image=$WHICH out=$NAME"
rm -rf "$ROOT/gowin/impl"
mkdir -p "$ROOT/gowin/impl"
cd "$ROOT/gowin"
gw_sh "$ROOT/gowin/gowin_build_spiflash.tcl"
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
echo "SRAM load only (never flash):"
echo "  openFPGALoader --busdev-num 003:081 -b tangnano4k -m $ROOT/gowin/spi-fs/${NAME}.fs"
echo "Do NOT pass -f / --write-flash / --external-flash."
python3 - "$ROOT/gowin/spi-fs/${NAME}.rpt.txt" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
want = ("Logic", "Register", "CLS", "BSRAM", "LUT", "ALU")
for line in text:
    if "|" in line and any(line.strip().startswith(w) or f"  {w}" in line[:24] for w in want):
        if any(k in line for k in ("Logic", "CLS", "BSRAM", "Register", "LUT", "ALU")):
            print(line.rstrip())
PY
