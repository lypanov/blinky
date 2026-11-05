#!/usr/bin/env bash
# Verilator checks for the DDR3 command-port stand-in (sim/Ddr3UserModel.v).
# Builds no bitstream and does not load either FPGA.
set -u
cd "$(dirname "$0")/.."

FAIL=0
VFLAGS=(
  --cc --exe --build
  -Wno-fatal -Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND
  -Wno-UNUSED -Wno-UNDRIVEN -Wno-BLKSEQ
)

say() { printf '\n== %s\n' "$*"; }

build() {
  say "build $1"
  if ! "${@:2}"; then
    echo "FAIL build $1" >&2
    exit 1
  fi
}

run() {
  say "$*"
  if ! "$@"; then
    echo "FAIL $*" >&2
    FAIL=1
  fi
}

write_hex() {
  cp "$1" generated/imem_inline.hex
}

build eye verilator "${VFLAGS[@]}" \
  --top-module Ddr3UserModel \
  --Mdir sim/obj_dir/ddr3_eye -o ddr3_eye \
  sim/Ddr3UserModel.v sim/tb_ddr3_eye.cpp

EYE=sim/obj_dir/ddr3_eye/ddr3_eye
run "$EYE"
run "$EYE" +ddr3_center=9
run "$EYE" +ddr3_center=9 +ddr3_lane0=9
# Programmed step equal to the center: every pin on the addressed column.
# The LANE0_STEP=9 LANE1_STEP=9 Dock sample is not this hit.
run "$EYE" +ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9
run "$EYE" +ddr3_lane0=9 +ddr3_lane1=9
run "$EYE" +ddr3_lane1=9
run "$EYE" +ddr3_lane0=9
run "$EYE" +ddr3_lane0=11 +ddr3_lane1=11
run "$EYE" +ddr3_nohold
run "$EYE" +ddr3_nowload
run "$EYE" +ddr3_dm_all
run "$EYE" +ddr3_dm_lane0
run "$EYE" +ddr3_dm_lane1
run "$EYE" +ddr3_lane1=12
run "$EYE" +ddr3_corrupt

build port verilator "${VFLAGS[@]}" \
  --top-module ddr3_port_test_top \
  --Mdir sim/obj_dir/ddr3_port -o ddr3_port \
  sim/ddr3_port_test_top.v gowin/primer20k/ddr3_port_test.v \
  sim/Ddr3UserModel.v sim/tb_ddr3_port_test.cpp

PORT=sim/obj_dir/ddr3_port/ddr3_port
run "$PORT"
run "$PORT" +ddr3_corrupt
run "$PORT" +ddr3_late

python3 sim/build_hyperram_imem.py --mov-iter 5 --pad 2048 \
  --out sim/obj_dir/ddr3_n5.words
python3 sim/build_fixup_imem.py --mov-iter 5 --pad 2048 \
  --out sim/obj_dir/ddr3fixup_n5.words
python3 sim/build_rsc_imem.py --mov-iter 5 --pad 2048 \
  --out sim/obj_dir/ddr3rsc_n5.words
python3 sim/build_rsc_imem.py --mov-iter 32 --pad 2048 \
  --out sim/obj_dir/ddr3rsc_n32.words
python3 sim/build_rsc_imem.py --mov-iter 5 --pad 2048 --break-slot 30 \
  --out sim/obj_dir/ddr3rsc_break30.words

elaborate() {
  local image=$1
  local words=$2
  say "elaborate $image"
  if ! SIM_IMAGE="$image" BLINK3_IMEM="$words" \
      mill chisel-blinky.runMain gcd.CPUSimTop; then
    echo "FAIL elaborate $image" >&2
    exit 1
  fi
  local mdir="sim/obj_dir/ddr3_cpu_${image}"
  mkdir -p "$mdir"
  build "$image" verilator "${VFLAGS[@]}" -DPRINTF_COND=0 \
    --top-module CPUSimTop --Mdir "$mdir" -o ddr3_cpu \
    -CFLAGS "-std=c++17 -O2" \
    generated/CPUSimTopDdr3.v generated/InstrRom.v \
    sim/CpuClock.v sim/Ddr3UserModel.v sim/tb_ddr3_cpu.cpp
}

CPU() {
  local image=$1
  shift
  run "sim/obj_dir/ddr3_cpu_${image}/ddr3_cpu" "$@"
}

elaborate ddr3 sim/obj_dir/ddr3_n5.words
CPU ddr3 --cycles 80000 --edges 2 --period 3668 --first 22634 \
  --r5 ffffffff --r9 ffffffe1 --mask ff

elaborate ddr3fixup sim/obj_dir/ddr3fixup_n5.words
CPU ddr3fixup --cycles 80000 --edges 2 --period 3668 --first 25434 \
  --r5 ffffffff --r9 ffffffe1 --mask fffffff

elaborate ddr3rsc sim/obj_dir/ddr3rsc_n5.words
# ALU place (center 10). The reader program passes here. The reader
# bitstream does not have this place; see +ddr3_center=9 below.
CPU ddr3rsc --cycles 80000 --edges 2 --period 3668 --first 32902 \
  --r5 00000000 --r9 ffffffe1 --mask ffffffffff
# Reader place. Lane 0 is still the forced step 10. That step is one
# above the data eye, and lane 1 sits in the same beat.
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 aaaaaaaa --r9 55555536 --mask f0 \
  +ddr3_center=9
# Same place, lane 0 programmed down onto the eye. Lane 1 stays aliased.
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 aaffaaff --r9 550054e1 --mask f0 \
  +ddr3_center=9 +ddr3_lane0=9
# Programmed step equal to the center. Same whole-pin hit as the ALU
# place: every DQ pin on the addressed column. Not the reader bitstream
# that forces both lanes to 9. That Dock line is R5 AFF0B9CF / R9
# 450FEFF1 / mask 50, and no column rule here produces it.
CPU ddr3rsc --cycles 80000 --edges 2 --period 3668 --first 32902 \
  --r5 00000000 --r9 ffffffe1 --mask ffffffffff \
  +ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9
# ALU place: one step below the eye, then one step above it.
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 55555554 --r9 aaaaaa8c --mask f0 \
  +ddr3_lane0=9 +ddr3_lane1=9
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 550054ff --r9 aaffaae1 --mask f0 \
  +ddr3_lane1=9
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 00550054 --r9 ffaaff8c --mask f0 \
  +ddr3_lane0=9
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 aaaaaaaa --r9 55555536 --mask f0 \
  +ddr3_lane0=11 +ddr3_lane1=11
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 aaaaaaaa --r9 55555536 --mask a0 \
  +ddr3_nohold
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1b44 \
  --r5 ffffffbf --r9 ffffffe1 --mask fffffff \
  +ddr3_nowload
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 00000000 --r9 00000000 --mask 0 \
  +ddr3_corrupt
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 55555554 --r9 aaaaaa8c --mask c0 \
  +ddr3_dm_all
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 00ff00ff --r9 1ee11ee1 --mask 30 \
  +ddr3_dm_lane0
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 ff00ff00 --r9 e11ee100 --mask 0 \
  +ddr3_dm_lane1

write_hex sim/obj_dir/ddr3rsc_n32.words
CPU ddr3rsc --cycles 120000 --edges 2 --period 19220 --first 48454 \
  --r9 ffffffe1 --mask ffffffffff
# Same whole-pin hit at N=32. Not the step-9 Dock sample.
CPU ddr3rsc --cycles 120000 --edges 2 --period 19220 --first 48454 \
  --r9 ffffffe1 --mask ffffffffff \
  +ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9

write_hex sim/obj_dir/ddr3rsc_break30.words
CPU ddr3rsc --cycles 80000 --edges 0 --pc 1b44 \
  --r5 00000000 --r9 ffffffe1 --mask bfffffffff

write_hex sim/obj_dir/ddr3rsc_n5.words

if [[ "$FAIL" -ne 0 ]]; then
  echo "stand-in mismatches" >&2
  exit 1
fi
echo "stand-in matches"
