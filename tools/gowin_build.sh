#!/usr/bin/env bash
# Generate CPUMinimalWrapper.v from the Blink3 linked image (or Blink2hw)
# and run Gowin syn+PNR. Does not program the FPGA. Bitstream is SRAM-loadable
# .fs (not flash).
#
# Usage:
#   tools/gowin_build.sh                         # Blink3 Nano 4K, N=262144
#   BLINK3_MAXITER=131072 tools/gowin_build.sh   # Blink3 Nano 4K, half delay
#   BOARD=primer20k tools/gowin_build.sh         # Blink3 Primer 20K Dock
#   FPGA_IMAGE=blink2 tools/gowin_build.sh       # old Blink2hw small IMEM
#   FPGA_IMAGE=hyperram tools/gowin_build.sh     # Nano 4K HyperRAM data port + Blink3
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
cd "$ROOT"

FPGA_IMAGE="${FPGA_IMAGE:-blink3}"
BOARD="${BOARD:-nano4k}"
BLINK3_MAXITER="${BLINK3_MAXITER:-262144}"
if [[ "$FPGA_IMAGE" == "hyperram" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/hyperram.words"
fi
BLINK3_IMEM="${BLINK3_IMEM:-$ROOT/sim/visualizer/imem/blink3.words}"
export FPGA_IMAGE BLINK3_IMEM
GOWIN_TCL="$ROOT/gowin/gowin_build.tcl"

# Gowin GUI Tcl crashes with QT_QPA_PLATFORM=offscreen. Prefer xcb on Bee.
if [[ -z "${QT_QPA_PLATFORM:-}" || "${QT_QPA_PLATFORM}" == "wayland;xcb" || "${QT_QPA_PLATFORM}" == "wayland" ]]; then
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

mhi_hex() {
  python3 -c "print(f'{(0x60000000 | (int($1) >> 16)):08x}')"
}

if [[ "$FPGA_IMAGE" == "hyperram" ]]; then
  if [[ "$BOARD" != "nano4k" && "$BOARD" != "tangnano4k" ]]; then
    echo "error: HyperRAM step 1 loads the Tang Nano 4K only (BOARD=$BOARD)" >&2
    exit 1
  fi
  echo "==> HyperRAM IMEM (prologue at 0x1200, Blink3 body, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_hyperram_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="hyperram_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "blink3" ]]; then
  echo "==> Blink3 IMEM (trampoline at 0, linked image at 0x1000+, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_blink3_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="blink3_n${BLINK3_MAXITER}"
else
  echo "==> Chisel: CPUMinimalWrapper from tests/Blink2hw.code"
  EXPECT_MHI="60000004"
  GOWIN_OUT_NAME="blink2hw_4x"
fi
export GOWIN_OUT_NAME

echo "==> Chisel: CPUMinimalWrapper (FPGA_IMAGE=$FPGA_IMAGE)"
mill chisel-blinky.runMain gcd.CPUSubset0

V="$ROOT/generated/CPUMinimalWrapper.v"
if [[ ! -f "$V" ]]; then
  echo "error: $V was not generated" >&2
  exit 1
fi

echo "==> Checking delay word 0x$EXPECT_MHI in Verilog"
if grep -qi "$EXPECT_MHI" "$V"; then
  echo "    found $EXPECT_MHI in $V"
  grep -ni "$EXPECT_MHI" "$V" | head
else
  echo "error: $EXPECT_MHI not in $V — image did not reach instruction memory" >&2
  grep -ni '6000000' "$V" || true
  exit 1
fi

if [[ "$FPGA_IMAGE" == "blink3" || "$FPGA_IMAGE" == "hyperram" ]]; then
  echo "==> Checking Blink3 trampoline / BL Toggle encodings"
  for word in f7000409 f7000410 f7ffffdc; do
    if grep -qi "$word" "$V"; then
      echo "    found $word"
    else
      echo "error: $word not in $V (trampoline or relocated BL missing)" >&2
      exit 1
    fi
  done
fi

if [[ "$FPGA_IMAGE" == "hyperram" ]]; then
  echo "==> Checking prologue entry MOV R0, 0x1200"
  if grep -qi '40001200' "$V"; then
    echo "    found 40001200"
  else
    echo "error: prologue entry 40001200 not in $V" >&2
    exit 1
  fi
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

case "$BOARD" in
  nano4k|tangnano4k)
    echo "==> Gowin syn+PNR (GW1NSR-LV4CQN48PC6/I5) out=$GOWIN_OUT_NAME"
    mkdir -p "$ROOT/gowin/impl"
    # gw_sh writes impl next to the Tcl unless -d is used; run from gowin/
    cd "$ROOT/gowin"
    gw_sh "$GOWIN_TCL"
    FS="$ROOT/gowin/impl/pnr/${GOWIN_OUT_NAME}.fs"
    SEARCH="$ROOT/gowin/impl"
    LOAD_HINT="tools/sram_load.sh -b tangnano4k $FS"$'\n'"  openFPGALoader -b tangnano4k -m $FS"
    ;;
  primer20k|tangprimer20k)
    echo "==> Gowin syn+PNR (GW2A-LV18PG256C8/I7 Dock) out=$GOWIN_OUT_NAME"
    mkdir -p "$ROOT/gowin/primer20k/impl"
    cd "$ROOT/gowin/primer20k"
    gw_sh "$ROOT/gowin/primer20k/gowin_blink3.tcl"
    FS="$ROOT/gowin/primer20k/impl/pnr/${GOWIN_OUT_NAME}.fs"
    SEARCH="$ROOT/gowin/primer20k/impl"
    LOAD_HINT="tools/sram_load.sh -b tangprimer20k $FS"$'\n'"  openFPGALoader -b tangprimer20k -m $FS"
    ;;
  *)
    echo "error: BOARD=$BOARD (use nano4k or primer20k)" >&2
    exit 1
    ;;
esac

echo "==> Bitstream"
if [[ ! -f "$FS" ]]; then
  echo "error: expected $FS was not produced" >&2
  find "$SEARCH" -name '*.fs' -type f || true
  exit 1
fi
echo "    $FS"
echo ""
echo "SRAM load only (never flash; -m is the default write-sram flag):"
echo "  $LOAD_HINT"
echo "Do NOT pass -f / --write-flash / --external-flash."
