#!/usr/bin/env bash
# Build the Primer 20K Dock wiki blinky with Gowin syn+PNR.
# Does not program the FPGA. Bitstream is SRAM-loadable .fs (not flash).
#
# Usage:
#   tools/gowin_build_primer20k.sh            # 1 Hz (wiki COUNT_VALUE=13499999)
#   COUNT_VALUE=6749999 tools/gowin_build_primer20k.sh   # 2 Hz
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIMER="$REPO/primer20k"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"

if [[ -z "${QT_QPA_PLATFORM:-}" ]]; then
  export QT_QPA_PLATFORM=xcb
fi
if [[ "${QT_QPA_PLATFORM}" == "offscreen" ]]; then
  echo "error: QT_QPA_PLATFORM=offscreen crashes gw_sh; unset it or use xcb" >&2
  exit 1
fi
if ! command -v gw_sh >/dev/null 2>&1; then
  echo "error: gw_sh not on PATH (expect /usr/bin/gw_sh -> /opt/gowin-eda-ide)" >&2
  exit 1
fi

COUNT_VALUE="${COUNT_VALUE:-13499999}"
SRC="$PRIMER/gowin/led.v"
if [[ ! -f "$SRC" ]]; then
  echo "error: missing $SRC" >&2
  exit 1
fi

# Prepend `define so the wiki default can be overridden without editing led.v.
GEN="$PRIMER/gowin/led_build.v"
{
  echo "\`define COUNT_VALUE ${COUNT_VALUE}"
  cat "$SRC"
} > "$GEN"

echo "==> Gowin syn+PNR (GW2A-LV18PG256C8/I7) COUNT_VALUE=${COUNT_VALUE}"
cd "$PRIMER/gowin"
gw_sh "$PRIMER/gowin/gowin_build.tcl"

FS="$PRIMER/gowin/impl/pnr/primer20k_blink.fs"
if [[ ! -f "$FS" ]]; then
  mapfile -t FOUND < <(find "$PRIMER/gowin" -name '*.fs' -type f | sort)
  if [[ ${#FOUND[@]} -eq 0 ]]; then
    echo "error: no .fs bitstream produced" >&2
    exit 1
  fi
  FS="${FOUND[-1]}"
fi

echo "==> Bitstream  $FS"
echo "    COUNT_VALUE=${COUNT_VALUE}"
echo ""
echo "SRAM load only (never flash):"
echo "  tools/sram_load.sh -b tangprimer20k $FS"
echo "  openFPGALoader -b tangprimer20k -m $FS"
echo "Do NOT pass -f / --write-flash / --external-flash."
