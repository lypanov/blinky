#!/usr/bin/env bash
# Generate CPUMinimalWrapper.v from Blink2hw.code and run Gowin syn+PNR.
# Does not program the FPGA. Bitstream is SRAM-loadable .fs (not flash).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
cd "$ROOT"

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

echo "==> Chisel: CPUMinimalWrapper from tests/Blink2hw.code"
mill chisel-blinky.runMain gcd.CPUSubset0

V="$ROOT/generated/CPUMinimalWrapper.v"
if [[ ! -f "$V" ]]; then
  echo "error: $V was not generated" >&2
  exit 1
fi

echo "==> Checking 4x delay word 0x60000002 (MHI R0,0x2 = 131072) in Verilog"
if grep -q '60000002' "$V"; then
  echo "    found 60000002 in $V"
  grep -n '60000002' "$V" | head
else
  echo "error: 60000002 not in $V — Blink2hw.code patch did not reach instruction memory" >&2
  grep -n '6000000' "$V" || true
  exit 1
fi
if grep -q '60000008' "$V"; then
  echo "error: old 1 Hz word 60000008 still present in $V" >&2
  exit 1
fi

echo "==> Gowin_SP instances (expect 2)"
inst="$(grep -c 'Gowin_SP' "$V" || true)"
echo "    Gowin_SP mentions in wrapper: $inst"

# Gowin synthesis does not always define SYNTHESIS; Chisel $fwrite is gated on it.
mkdir -p "$ROOT/gowin/src"
{
  echo '`define SYNTHESIS'
  echo '`define PRINTF_COND 0'
  cat "$V"
} > "$ROOT/gowin/src/CPUMinimalWrapper.v"

echo "==> Gowin syn+PNR (GW1NSR-LV4CQN48PC6/I5)"
mkdir -p "$ROOT/gowin/impl"
# gw_sh writes impl next to the Tcl unless -d is used; run from gowin/
cd "$ROOT/gowin"
gw_sh "$ROOT/gowin/gowin_build.tcl"

echo "==> Bitstream"
mapfile -t FS < <(find "$ROOT/gowin" -name '*.fs' -type f | sort)
if [[ ${#FS[@]} -eq 0 ]]; then
  echo "error: no .fs bitstream produced" >&2
  exit 1
fi
for f in "${FS[@]}"; do
  echo "    $f"
done
echo ""
echo "SRAM load only (never flash; -m is the default write-sram flag):"
echo "  openFPGALoader -b tangnano4k -m ${FS[-1]}"
echo "Do NOT pass -f / --write-flash / --external-flash."
