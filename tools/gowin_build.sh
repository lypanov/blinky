#!/usr/bin/env bash
# Generate CPUMinimalWrapper.v for the current disk image and run Gowin
# syn+PNR. Does not program the FPGA. Bitstream is SRAM-loadable .fs.
#
# Usage:
#   tools/gowin_build.sh                         # Nano 4K NOR disk, square, 1000 ms
#   VIDEO_MODE=flash FPGA_IMAGE=modules tools/gowin_build.sh
#   VIDEO_MODE=off   FPGA_IMAGE=modules tools/gowin_build.sh
#   FPGA_IMAGE=ddr3modules BOARD=primer20k tools/gowin_build.sh  # Dock UART disk, counter text
#   VIDEO_MODE=square FPGA_IMAGE=ddr3modules BOARD=primer20k tools/gowin_build.sh
#   VIDEO_MODE=flash  FPGA_IMAGE=ddr3modules BOARD=primer20k tools/gowin_build.sh
#   VIDEO_MODE=off    FPGA_IMAGE=ddr3modules BOARD=primer20k tools/gowin_build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
cd "$ROOT"

FPGA_IMAGE="${FPGA_IMAGE:-modules}"
BOARD="${BOARD:-nano4k}"
if [[ "$FPGA_IMAGE" != "modules" && "$FPGA_IMAGE" != "ddr3modules" ]]; then
  echo "error: FPGA_IMAGE=$FPGA_IMAGE is retired (modules or ddr3modules)" >&2
  exit 1
fi
# Milliseconds between toggles. 1000 is a full blink of 0.500 Hz.
BLINK3_MAXITER="${BLINK3_MAXITER:-1000}"
# The negative disk removes Blink's collector call. The arm word follows
# the disk checksum, so this is a separate bitstream, not a second disk
# on the same ROM.
NO_COLLECT="${NO_COLLECT:-0}"
LINK_EXTRA=()
NAME_EXTRA=""
if [[ "$NO_COLLECT" == 1 ]]; then
  LINK_EXTRA+=(--no-collect)
  NAME_EXTRA="_nocollect"
fi
if [[ "$FPGA_IMAGE" == "modules" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/modules.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3modules" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3modules.words"
fi
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

if [[ "$FPGA_IMAGE" == "modules" ]]; then
  if [[ "$BOARD" != "nano4k" && "$BOARD" != "tangnano4k" ]]; then
    echo "error: the NOR disk image loads the Tang Nano 4K only (BOARD=$BOARD)" >&2
    exit 1
  fi
  unset SECTOR_ROM
  echo "==> Modules IMEM (NOR disk bootstrap, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/link_inner.py" \
    --max-iter "$BLINK3_MAXITER" \
    --flash-boot \
    "${LINK_EXTRA[@]}" \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(printf '%08x' "$(awk -F= '$1=="delay_word"{print $2}' "$ROOT/sim/visualizer/imem/core.map")")"
  GOWIN_OUT_NAME="modules_n${BLINK3_MAXITER}${NAME_EXTRA}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
else
  if [[ "$BOARD" != "primer20k" && "$BOARD" != "tangprimer20k" ]]; then
    echo "error: the UART disk image loads the Tang Primer 20K only (BOARD=$BOARD)" >&2
    exit 1
  fi
  unset SECTOR_ROM
  echo "==> DDR3 Modules IMEM (UART disk bootstrap, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/link_inner.py" \
    --max-iter "$BLINK3_MAXITER" \
    --uart-disk \
    "${LINK_EXTRA[@]}" \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(printf '%08x' "$(awk -F= '$1=="delay_word"{print $2}' "$ROOT/sim/visualizer/imem/core.map")")"
  GOWIN_OUT_NAME="ddr3modules_n${BLINK3_MAXITER}${NAME_EXTRA}"
  GOWIN_TCL="$ROOT/gowin/primer20k/gowin_ddr3.tcl"
fi
export GOWIN_OUT_NAME

echo "==> Chisel: CPUMinimalWrapper (FPGA_IMAGE=$FPGA_IMAGE)"
mill chisel-blinky.runMain gcd.CPUSubset0

V="$ROOT/generated/CPUMinimalWrapper.v"
IMEM_HEX="$ROOT/generated/imem_inline.hex"
if [[ ! -f "$V" ]]; then
  echo "error: $V was not generated" >&2
  exit 1
fi
if [[ ! -f "$IMEM_HEX" ]]; then
  echo "error: $IMEM_HEX was not generated" >&2
  exit 1
fi
if ! grep -q 'InstrRom' "$V"; then
  echo "error: InstrRom is not instantiated in $V" >&2
  exit 1
fi

# The Logger is the 4K cut. DDR3 elaborations keep it. The Dock
# training UART is ddr3_uart_tx and is not this module. Both tops
# still connect io_uart_rx / io_uart_tx.
if [[ "$FPGA_IMAGE" == ddr3* ]]; then
  if ! grep -q '^module Logger' "$V"; then
    echo "error: Dock elaboration dropped the Logger" >&2
    exit 1
  fi
else
  if grep -q '^module Logger' "$V"; then
    echo "error: $FPGA_IMAGE elaboration still contains the Logger" >&2
    exit 1
  fi
fi
if ! grep -q 'io_uart_tx' "$V" || ! grep -q 'io_uart_rx' "$V"; then
  echo "error: wrapper UART pins were removed" >&2
  exit 1
fi

echo "==> Checking delay word 0x$EXPECT_MHI in the disk"
python3 - "$ROOT/sim/visualizer/imem/core.map" "$EXPECT_MHI" "$ROOT/sim/out/disk.bin" << 'PY'
import sys
map_path, delay, disk_path = sys.argv[1:]
meta = {}
for line in open(map_path):
    key, value = line.strip().split("=")
    meta[key] = int(value, 0)
blob = open(disk_path, "rb").read()
needle = bytes.fromhex(delay)[::-1]
if needle not in blob:
    raise SystemExit(f"delay word {delay} is not in the disk")
print(f"    disk contains {delay}")
PY

echo "==> Checking the bootstrap at ROM[0]"
entry="$(sed -n '1p' "$IMEM_HEX")"
lines="$(wc -l < "$IMEM_HEX")"
if [[ "$entry" == "40000000" ]]; then
  echo "    ROM[0] is MOV R0, 0 ($entry)"
else
  echo "error: ROM[0] is $entry, expected the bootstrap MOV R0, 0" >&2
  exit 1
fi
if [[ "$lines" -eq 512 ]]; then
  echo "    ROM is 512 words"
else
  echo "error: ROM is $lines words, expected 512" >&2
  exit 1
fi
if grep -qi 'c7000001' "$IMEM_HEX"; then
  echo "    bootstrap branches with B R1"
else
  echo "error: bootstrap B R1 is not in the ROM" >&2
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
# KeepBit is hand-written. gowin/src is the generated tree, so copy it in
# for the Verilator line that still names that path.
cp "$ROOT/gowin/KeepBit.v" "$ROOT/gowin/src/KeepBit.v"

case "$BOARD" in
  nano4k|tangnano4k)
    if [[ -z "${VIDEO_MODE:-}" ]]; then
      VIDEO_MODE=off
      if [[ "$FPGA_IMAGE" == "modules" ]]; then
        VIDEO_MODE=square
      fi
    fi
    case "$VIDEO_MODE" in
      off) ;;
      flash|square)
        if [[ "$FPGA_IMAGE" != "modules" ]]; then
          echo "error: $VIDEO_MODE video is the modules image only (FPGA_IMAGE=$FPGA_IMAGE)" >&2
          exit 1
        fi
        ;;
      text)
        echo "error: VIDEO_MODE=text is the Dock image" >&2
        exit 1
        ;;
      *)
        echo "error: VIDEO_MODE=$VIDEO_MODE" >&2
        exit 1
        ;;
    esac
    export VIDEO_MODE
    echo "==> VIDEO_MODE=$VIDEO_MODE"
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
    if [[ -z "${VIDEO_MODE:-}" ]]; then
      VIDEO_MODE=off
      if [[ "$FPGA_IMAGE" == "ddr3modules" ]]; then
        VIDEO_MODE=text
      fi
    fi
    case "$VIDEO_MODE" in
      off) ;;
      flash|square|text)
        if [[ "$FPGA_IMAGE" != "ddr3modules" ]]; then
          echo "error: $VIDEO_MODE video is the ddr3modules image only (FPGA_IMAGE=$FPGA_IMAGE)" >&2
          exit 1
        fi
        ;;
      *)
        echo "error: VIDEO_MODE=$VIDEO_MODE" >&2
        exit 1
        ;;
    esac
    export VIDEO_MODE
    echo "==> VIDEO_MODE=$VIDEO_MODE"
    echo "==> Gowin syn+PNR (GW2A-LV18PG256C8/I7 Dock) out=$GOWIN_OUT_NAME"
    mkdir -p "$ROOT/gowin/primer20k/impl"
    cd "$ROOT/gowin/primer20k"
    printf '%s\n' '// Modules image. The write delay is the trained eye.' '`define DDR3_MODULES' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
    # The 1-port register-file modules netlist blinks with route_option 2.
    # route_option 1 leaves the user LED dark and the training line at
    # ..0080 with F=4B.
    DDR3_ROUTE_OPTION="${DDR3_ROUTE_OPTION:-2}" gw_sh "$ROOT/gowin/primer20k/gowin_ddr3.tcl"
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
