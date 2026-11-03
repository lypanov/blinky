#!/usr/bin/env bash
# Generate CPUMinimalWrapper.v from Blink2hw.code and run Gowin syn+PNR.
# Does not program the FPGA. Bitstream is SRAM-loadable .fs (not flash).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$REPO/core"
NANO="$REPO/nano4k"
export CHISEL_CPU_PROJECT_ROOT="$CORE"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
cd "$REPO"

# Gowin GUI Tcl crashes with QT_QPA_PLATFORM=offscreen. Prefer xcb on Bee.
if [[ -z "${QT_QPA_PLATFORM:-}" ]]; then
  export QT_QPA_PLATFORM=xcb
fi
if [[ "${QT_QPA_PLATFORM}" == "offscreen" ]]; then
  echo "error: QT_QPA_PLATFORM=offscreen crashes gw_sh; unset it or use xcb" >&2
  exit 1
fi

if ! command -v mill >/dev/null 2>&1; then
  echo "error: mill not on PATH" >&2
  exit 1
fi
if ! command -v gw_sh >/dev/null 2>&1; then
  echo "error: gw_sh not on PATH (expect /usr/bin/gw_sh -> /opt/gowin-eda-ide)" >&2
  exit 1
fi

echo "==> Chisel: CPUMinimalWrapper from core/tests/Blink2hw.code"
mill chisel-blinky.runMain gcd.CPUSubset0

V="$REPO/generated/CPUMinimalWrapper.v"
if [[ ! -f "$V" ]]; then
  echo "error: $V was not generated" >&2
  exit 1
fi

echo "==> Checking 2x delay word 0x60000004 (MHI R0,0x4 = 262144) in Verilog"
if grep -q '60000004' "$V"; then
  echo "    found 60000004 in $V"
  grep -n '60000004' "$V" | head
else
  echo "error: 60000004 not in $V — Blink2hw.code patch did not reach instruction memory" >&2
  grep -n '6000000' "$V" || true
  exit 1
fi
if grep -qE '6000000[28]' "$V"; then
  echo "error: old delay word 60000002 or 60000008 still present in $V" >&2
  exit 1
fi

echo "==> Gowin_SP instances (expect 2)"
inst="$(grep -c 'Gowin_SP' "$V" || true)"
echo "    Gowin_SP mentions in wrapper: $inst"

# Gowin synthesis does not always define SYNTHESIS; Chisel $fwrite is gated on it.
mkdir -p "$NANO/gowin/src"
{
  echo '`define SYNTHESIS'
  echo '`define PRINTF_COND 0'
  cat "$V"
} > "$NANO/gowin/src/CPUMinimalWrapper.v"

echo "==> Gowin syn+PNR (GW1NSR-LV4CQN48PC6/I5)"
mkdir -p "$NANO/gowin/impl"
# gw_sh writes impl next to the Tcl unless -d is used; run from nano4k/gowin/
cd "$NANO/gowin"
gw_sh "$NANO/gowin/gowin_build.tcl"

echo "==> Bitstream"
mapfile -t FS < <(find "$NANO/gowin" -name '*.fs' -type f | sort)
if [[ ${#FS[@]} -eq 0 ]]; then
  echo "error: no .fs bitstream produced" >&2
  exit 1
fi
for f in "${FS[@]}"; do
  echo "    $f"
done
echo ""
echo "SRAM load only (never flash; -m is the default write-sram flag):"
echo "  tools/sram_load.sh -b tangnano4k ${FS[-1]}"
echo "  openFPGALoader -b tangnano4k -m ${FS[-1]}"
echo "Do NOT pass -f / --write-flash / --external-flash."
