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
#   FPGA_IMAGE=fixup tools/gowin_build.sh        # HyperRAM plus the step-2 ALU prologue
#   FPGA_IMAGE=rsc tools/gowin_build.sh          # HyperRAM plus LDB/STB and the .rsc reader
#   FPGA_IMAGE=fetchbl tools/gowin_build.sh      # HyperRAM plus one BL fetched back from a store
#   FPGA_IMAGE=pdchain tools/gowin_build.sh      # HyperRAM plus device P-chain and D-chain fixups
#   FPGA_IMAGE=moddesc tools/gowin_build.sh      # HyperRAM plus ModDesc, the module table, and a procedure call
#   FPGA_IMAGE=files tools/gowin_build.sh        # HyperRAM plus Files, two .rsc images, and Load of Blink5
#   FPGA_IMAGE=modules tools/gowin_build.sh      # HyperRAM plus Modules.Init on the reset path, then Load of Blink5
#   FPGA_IMAGE=ddr3 BOARD=primer20k tools/gowin_build.sh  # Primer 20K DDR3 data port + Blink3
#   FPGA_IMAGE=ddr3fixup BOARD=primer20k tools/gowin_build.sh  # that port plus the step-2 ALU
#   FPGA_IMAGE=ddr3rsc BOARD=primer20k tools/gowin_build.sh    # that port plus LDB/STB and the .rsc reader
#   FPGA_IMAGE=ddr3fetch BOARD=primer20k tools/gowin_build.sh  # that port plus one BL fetched back from a store
#   FPGA_IMAGE=ddr3pd BOARD=primer20k tools/gowin_build.sh     # that port plus the P-chain and D-chain fixups
#   FPGA_IMAGE=ddr3moddesc BOARD=primer20k tools/gowin_build.sh  # that port plus ModDesc and a procedure call
#   FPGA_IMAGE=ddr3files BOARD=primer20k tools/gowin_build.sh    # that port plus Files, two .rsc images, and Load of Blink5
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
if [[ "$FPGA_IMAGE" == "fixup" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/fixup.words"
fi
if [[ "$FPGA_IMAGE" == "rsc" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/rsc.words"
fi
if [[ "$FPGA_IMAGE" == "fetchbl" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/fetchbl.words"
fi
if [[ "$FPGA_IMAGE" == "pdchain" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/pdchain.words"
fi
if [[ "$FPGA_IMAGE" == "moddesc" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/moddesc.words"
fi
if [[ "$FPGA_IMAGE" == "files" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/files.words"
fi
if [[ "$FPGA_IMAGE" == "modules" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/modules.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3fixup" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3fixup.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3rsc" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3rsc.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3fetch" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3fetch.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3pd" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3pd.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3moddesc" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3moddesc.words"
fi
if [[ "$FPGA_IMAGE" == "ddr3files" && -z "${BLINK3_IMEM:-}" ]]; then
  BLINK3_IMEM="$ROOT/sim/visualizer/imem/ddr3files.words"
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

if [[ "$FPGA_IMAGE" == "hyperram" || "$FPGA_IMAGE" == "fixup" || "$FPGA_IMAGE" == "rsc" || "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "pdchain" || "$FPGA_IMAGE" == "moddesc" || "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "modules" ]]; then
  if [[ "$BOARD" != "nano4k" && "$BOARD" != "tangnano4k" ]]; then
    echo "error: HyperRAM images load the Tang Nano 4K only (BOARD=$BOARD)" >&2
    exit 1
  fi
fi
if [[ "$FPGA_IMAGE" == "modules" ]]; then
  echo "==> Modules IMEM (Init with a 4 KB reserve, then Load of Blink5, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_modules_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="modules_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "files" ]]; then
  echo "==> Files IMEM (two .rsc images and Load of Blink5, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_files_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="files_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "moddesc" ]]; then
  echo "==> ModDesc IMEM (module table and procedure call, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_moddesc_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="moddesc_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "pdchain" ]]; then
  echo "==> P/D-chain IMEM (device fixups, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_pdchain_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="pdchain_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "fetchbl" ]]; then
  echo "==> Fetch-BL IMEM (stored BL at 0x1F00, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_fetchbl_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="fetchbl_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "rsc" ]]; then
  echo "==> RSC IMEM (HyperRAM prologue, ALU, byte reader at 0x1800, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_rsc_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="rsc_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "fixup" ]]; then
  echo "==> Fixup IMEM (HyperRAM prologue, ALU prologue at 0x1400, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_fixup_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="fixup_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "hyperram" ]]; then
  echo "==> HyperRAM IMEM (prologue at 0x1200, Blink3 body, maxIterations=$BLINK3_MAXITER)"
  python3 "$ROOT/sim/build_hyperram_imem.py" \
    --max-iter "$BLINK3_MAXITER" \
    --pad 2048 \
    --out "$BLINK3_IMEM"
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="hyperram_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/gowin_build_hyperram.tcl"
elif [[ "$FPGA_IMAGE" == "ddr3" || "$FPGA_IMAGE" == "ddr3fixup" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" || "$FPGA_IMAGE" == "ddr3pd" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "ddr3files" ]]; then
  if [[ "$BOARD" != "primer20k" && "$BOARD" != "tangprimer20k" ]]; then
    echo "error: the DDR3 data port loads the Tang Primer 20K only (BOARD=$BOARD)" >&2
    exit 1
  fi
  if [[ "$FPGA_IMAGE" == "ddr3files" ]]; then
    echo "==> DDR3 Files IMEM (prologue, two .rsc images, Load of Blink5, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_files_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  elif [[ "$FPGA_IMAGE" == "ddr3moddesc" ]]; then
    echo "==> DDR3 ModDesc IMEM (prologue, module table, procedure call, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_moddesc_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  elif [[ "$FPGA_IMAGE" == "ddr3pd" ]]; then
    echo "==> DDR3 P/D-chain IMEM (prologue, device chains, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_pdchain_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  elif [[ "$FPGA_IMAGE" == "ddr3fetch" ]]; then
    echo "==> DDR3 stored-BL IMEM (prologue, ALU, reader, fetch at 0x1F00, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_fetchbl_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  elif [[ "$FPGA_IMAGE" == "ddr3rsc" ]]; then
    echo "==> DDR3 reader IMEM (prologue, ALU, bytes at 0x1800, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_rsc_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  elif [[ "$FPGA_IMAGE" == "ddr3fixup" ]]; then
    echo "==> DDR3 fixup IMEM (prologue, ALU at 0x1400, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_fixup_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  else
    echo "==> DDR3 IMEM (prologue at 0x1200, Blink3 body, maxIterations=$BLINK3_MAXITER)"
    python3 "$ROOT/sim/build_hyperram_imem.py" \
      --max-iter "$BLINK3_MAXITER" \
      --pad 2048 \
      --out "$BLINK3_IMEM"
  fi
  EXPECT_MHI="$(mhi_hex "$BLINK3_MAXITER")"
  GOWIN_OUT_NAME="${FPGA_IMAGE}_n${BLINK3_MAXITER}"
  GOWIN_TCL="$ROOT/gowin/primer20k/gowin_ddr3.tcl"
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

echo "==> Checking delay word 0x$EXPECT_MHI in the instruction ROM"
if grep -qi "$EXPECT_MHI" "$IMEM_HEX"; then
  echo "    found $EXPECT_MHI in $IMEM_HEX"
else
  echo "error: $EXPECT_MHI not in $IMEM_HEX — image did not reach instruction memory" >&2
  exit 1
fi

if [[ "$FPGA_IMAGE" == "pdchain" || "$FPGA_IMAGE" == "ddr3pd" ]]; then
  echo "==> Checking Blink3 trampoline and the unfixed BL placeholder"
  for word in f7000409 f7000410; do
    if grep -qi "$word" "$IMEM_HEX"; then
      echo "    found $word"
    else
      echo "error: $word not in $IMEM_HEX (trampoline missing)" >&2
      exit 1
    fi
  done
  # Word index 0x108C/4 is line 1060. The ROM must be the placeholder.
  bl="$(sed -n '1060p' "$IMEM_HEX")"
  if [[ "$bl" == "f7102011" ]]; then
    echo "    ROM 0x108C is the placeholder ($bl)"
  else
    echo "error: ROM 0x108C is $bl, expected the placeholder f7102011" >&2
    exit 1
  fi
  if grep -qi 'f7ffffdc' "$IMEM_HEX"; then
    echo "error: fixed BL f7ffffdc is in the ROM; the device walk would not be the proof" >&2
    exit 1
  fi
elif [[ "$FPGA_IMAGE" == "moddesc" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "ddr3files" || "$FPGA_IMAGE" == "modules" ]]; then
  echo "==> Checking the procedure-variable call and the unfixed BL placeholder"
  if grep -qi 'd7000001' "$IMEM_HEX"; then
    echo "    found d7000001"
  else
    echo "error: BLR R1 (d7000001) not in $IMEM_HEX" >&2
    exit 1
  fi
  bl="$(sed -n '1060p' "$IMEM_HEX")"
  if [[ "$bl" == "f7102011" ]]; then
    echo "    ROM 0x108C is the placeholder ($bl)"
  else
    echo "error: ROM 0x108C is $bl, expected the placeholder f7102011" >&2
    exit 1
  fi
  if grep -qi 'f7ffffdc' "$IMEM_HEX"; then
    echo "error: fixed BL f7ffffdc is in the ROM; the device walk would not be the proof" >&2
    exit 1
  fi
  if grep -qi 'f7000409' "$IMEM_HEX"; then
    echo "error: address 0 is still the Blink3 trampoline; a zero procedure variable could blink" >&2
    exit 1
  fi
  if [[ "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "ddr3files" || "$FPGA_IMAGE" == "modules" ]]; then
    echo "==> Checking Load's BT R1 and the Blink5 name word"
    for word in c7000001 61006e69; do
      if grep -qi "$word" "$IMEM_HEX"; then
        echo "    found $word"
      else
        echo "error: $word not in $IMEM_HEX" >&2
        exit 1
      fi
    done
  fi
  if [[ "$FPGA_IMAGE" == "modules" ]]; then
    echo "==> Checking reset enters the Modules body"
    entry="$(sed -n '40p' "$IMEM_HEX")"
    if [[ "$entry" == "400006c0" ]]; then
      echo "    ROM 0x9C is the modules body ($entry)"
    else
      echo "error: ROM 0x9C is $entry, expected 400006c0" >&2
      exit 1
    fi
    if grep -qi '40001200' "$IMEM_HEX"; then
      echo "    body still has the prologue MOV 40001200"
    else
      echo "error: prologue MOV 40001200 missing from the modules body" >&2
      exit 1
    fi
  fi
elif [[ "$FPGA_IMAGE" == "blink3" || "$FPGA_IMAGE" == "hyperram" || "$FPGA_IMAGE" == "fixup" || "$FPGA_IMAGE" == "rsc" || "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "ddr3" || "$FPGA_IMAGE" == "ddr3fixup" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" ]]; then
  echo "==> Checking Blink3 trampoline / BL Toggle encodings"
  for word in f7000409 f7000410 f7ffffdc; do
    if grep -qi "$word" "$IMEM_HEX"; then
      echo "    found $word"
    else
      echo "error: $word not in $IMEM_HEX (trampoline or relocated BL missing)" >&2
      exit 1
    fi
  done
fi

if [[ "$FPGA_IMAGE" == "hyperram" || "$FPGA_IMAGE" == "fixup" || "$FPGA_IMAGE" == "rsc" || "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "pdchain" || "$FPGA_IMAGE" == "moddesc" || "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "modules" || "$FPGA_IMAGE" == "ddr3" || "$FPGA_IMAGE" == "ddr3fixup" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" || "$FPGA_IMAGE" == "ddr3pd" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "ddr3files" ]]; then
  echo "==> Checking prologue entry MOV R0, 0x1200"
  if grep -qi '40001200' "$IMEM_HEX"; then
    echo "    found 40001200"
  else
    echo "error: prologue entry 40001200 not in $IMEM_HEX" >&2
    exit 1
  fi
fi
if [[ "$FPGA_IMAGE" == "fixup" || "$FPGA_IMAGE" == "ddr3fixup" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" || "$FPGA_IMAGE" == "ddr3pd" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "ddr3files" || "$FPGA_IMAGE" == "rsc" || "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "pdchain" || "$FPGA_IMAGE" == "moddesc" || "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "modules" ]]; then
  echo "==> Checking sign-extended MOV R1, -1"
  if grep -qi '5100ffff' "$IMEM_HEX"; then
    echo "    found 5100ffff"
  else
    echo "error: sign-extended MOV 5100ffff not in $IMEM_HEX" >&2
    exit 1
  fi
fi
if [[ "$FPGA_IMAGE" == "rsc" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" || "$FPGA_IMAGE" == "ddr3pd" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "ddr3files" || "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "pdchain" || "$FPGA_IMAGE" == "moddesc" || "$FPGA_IMAGE" == "files" || "$FPGA_IMAGE" == "modules" ]]; then
  echo "==> Checking LDB R1, [R3] and STB R1, [R3]"
  for word in 91300000 b1300000; do
    if grep -qi "$word" "$IMEM_HEX"; then
      echo "    found $word"
    else
      echo "error: $word not in $IMEM_HEX (byte op missing)" >&2
      exit 1
    fi
  done
fi
if [[ "$FPGA_IMAGE" == "fetchbl" || "$FPGA_IMAGE" == "ddr3fetch" ]]; then
  echo "==> Checking MHI of the BL prefix and the ROM hold at 0x1F00"
  if grep -qi '6400f700' "$IMEM_HEX"; then
    echo "    found 6400f700"
  else
    echo "error: 6400f700 not in $IMEM_HEX (FixP prefix missing)" >&2
    exit 1
  fi
  # Word index 0x1F00/4 is line 1985. It must be the hold ADD, not the BL.
  hold="$(sed -n '1985p' "$IMEM_HEX")"
  if [[ "$hold" == "41180001" ]]; then
    echo "    ROM 0x1F00 is the hold ($hold)"
  else
    echo "error: ROM 0x1F00 is $hold, expected the hold ADD 41180001" >&2
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
    if [[ "$FPGA_IMAGE" == "ddr3" || "$FPGA_IMAGE" == "ddr3fixup" || "$FPGA_IMAGE" == "ddr3rsc" || "$FPGA_IMAGE" == "ddr3fetch" || "$FPGA_IMAGE" == "ddr3pd" || "$FPGA_IMAGE" == "ddr3moddesc" || "$FPGA_IMAGE" == "ddr3files" ]]; then
      # DDR3_READER is the cold sweep. DDR3_FETCH, DDR3_PD,
      # DDR3_MODDESC, and DDR3_FILES only select the UART field. The
      # write delay is the trained eye.
      if [[ "$FPGA_IMAGE" == "ddr3files" ]]; then
        printf '%s\n' '// Files image. The write delay is the trained eye.' '`define DDR3_FILES' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      elif [[ "$FPGA_IMAGE" == "ddr3moddesc" ]]; then
        printf '%s\n' '// ModDesc image. The write delay is the trained eye.' '`define DDR3_MODDESC' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      elif [[ "$FPGA_IMAGE" == "ddr3pd" ]]; then
        printf '%s\n' '// P/D-chain image. The write delay is the trained eye.' '`define DDR3_PD' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      elif [[ "$FPGA_IMAGE" == "ddr3fetch" ]]; then
        printf '%s\n' '`define DDR3_FETCH' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      elif [[ "$FPGA_IMAGE" == "ddr3rsc" ]]; then
        printf '%s\n' '`define DDR3_READER' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      else
        printf '%s\n' '// prologue and ALU: trained write eye, no fixed step' > "$ROOT/gowin/primer20k/ddr3_eye.vh"
      fi
      gw_sh "$ROOT/gowin/primer20k/gowin_ddr3.tcl"
    else
      gw_sh "$ROOT/gowin/primer20k/gowin_blink3.tcl"
    fi
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
