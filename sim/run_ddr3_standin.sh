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
# The LANE0_STEP=9 LANE1_STEP=9 Dock sample is not this hit, and neither
# is the step-sweep table (54F854F7 / AFF7AFF7 / 0C0D0D9D). Both lanes at
# step 10 are two rows of that table and they disagree.
run "$EYE" +ddr3_center=9 +ddr3_lane0=9 +ddr3_lane1=9
# Absolute-step image: codes 9 and 10 are both offset +1, and the
# step is read. Dock image: centers are lane 0 = 11 and lane 1 = 7.
# Lane 0 at 10 with lane 1 at 7 is one below. Steps 11 and 7 are the pass.
run "$EYE" +ddr3_place_fetch
run "$EYE" +ddr3_place_fetch +ddr3_lane0=9 +ddr3_lane1=9
# Code 8 is not 9 or 10, so it is not forced onto that line.
run "$EYE" +ddr3_place_fetch +ddr3_lane0=8 +ddr3_lane1=8
run "$EYE" +ddr3_fetch_eye +ddr3_lane0=10 +ddr3_lane1=7
run "$EYE" +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
run "$EYE" +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=6
run "$EYE" +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=8
# Cold prologue, both lanes programmed to step 10 after reset.
# Lane 0 is the even-word alias. Lane 1 stays on the column except DQ5
# (bit 13 of the mask). DQ1 (odd-clear bit 1) still clears the high
# half of an odd column. That is R5 DFAADFAA / R9 20532036, not the
# whole-column AAAAAAAA of +ddr3_center=9.
run "$EYE" +ddr3_pin_even=20FF +ddr3_odd_clear=2
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
# Cold prologue after a controller reset, both lanes at step 10.
# Pin mask 20FF is DQ0-DQ7 and DQ13 on the even-word alias. Odd-clear
# bit 1 lets a 0 on DQ1 clear the high half of the odd word.
CPU ddr3rsc --cycles 40000 --edges 0 --pc 1390 \
  --r5 dfaadfaa --r9 20532036 --mask f0 \
  +ddr3_pin_even=20FF +ddr3_odd_clear=2
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

# Stored BL. The fetch is outside the delay loop, so the period stays
# 576*N+788 once the eye is hit. The first edge is 648 pclk later than
# the reader image. The Dock image's eye is programmed steps 11 and 7
# (+ddr3_fetch_eye). The model reads those steps. It has no write-level
# edge: the lane-0 edge was 000D on one build and 000C on the next.
python3 sim/build_fetchbl_imem.py --mov-iter 5 --pad 2048 \
  --out sim/obj_dir/ddr3fetch_n5.words
python3 sim/build_fetchbl_imem.py --mov-iter 8 --pad 2048 \
  --out sim/obj_dir/ddr3fetch_n8.words
python3 sim/build_fetchbl_imem.py --mov-iter 32 --pad 2048 \
  --out sim/obj_dir/ddr3fetch_n32.words
python3 sim/build_fetchbl_imem.py --mov-iter 5 --pad 2048 --break-slot 32 \
  --out sim/obj_dir/ddr3fetch_b32.words
python3 sim/build_fetchbl_imem.py --mov-iter 5 --pad 2048 --break-slot 33 \
  --out sim/obj_dir/ddr3fetch_b33.words

elaborate ddr3fetch sim/obj_dir/ddr3fetch_n5.words
# Absolute-step image. The step is read: 10 and 9 are both offset +1.
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 aaaaaaaa --r9 55555536 --mask f0 \
  +ddr3_place_fetch
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 aaaaaaaa --r9 55555536 --mask f0 \
  +ddr3_place_fetch +ddr3_lane0=9 +ddr3_lane1=9
# Dock centers are 11 and 7. Steps 000A and 0007 are lane 0 one below.
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 00550054 --r9 ffaaff8c --mask f0 \
  +ddr3_fetch_eye +ddr3_lane0=10 +ddr3_lane1=7
# Earlier image, pin split. Not offset 0, and not this program.
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 dfffdfff --r9 1ffe1fe1 --mask f0 \
  +ddr3_fetch_split
# Lane 1 one below its center. Not the even-word alias.
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 550054ff --r9 aaffaae1 --mask f0 \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=6
# Lane 1 one above its center: the even-word alias. Step 8, not step 6.
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 aaffaaff --r9 550054e1 --mask f0 \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=8
# The Dock program: lane 0 = 11, lane 1 = 7. The fetch is outside the
# delay loop, so the period and the first edge stay where they were.
CPU ddr3fetch --cycles 80000 --edges 2 --period 3668 --first 33550 \
  --r5 00000000 --r9 ffffffe1 --mask 3ffffffffff --pc 101c \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3fetch_n8.words
CPU ddr3fetch --cycles 80000 --edges 2 --period 5396 --first 35278 \
  --r5 00000000 --r9 ffffffe1 --mask 3ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3fetch_n32.words
CPU ddr3fetch --cycles 120000 --edges 2 --period 19220 --first 49102 \
  --r5 00000000 --r9 ffffffe1 --mask 3ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
# Slot 32 wrong: the compare holds and the BL is never fetched.
write_hex sim/obj_dir/ddr3fetch_b32.words
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1cd8 \
  --r5 00000000 --r9 ffffffe1 --mask ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
# Slot 33 wrong: the BL runs, then the link compare holds.
write_hex sim/obj_dir/ddr3fetch_b33.words
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1c20 \
  --r5 00000000 --r9 ffffffe1 --mask 1ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
# The pin split is the earlier reader place, not this route.
write_hex sim/obj_dir/ddr3fetch_n5.words
CPU ddr3fetch --cycles 80000 --edges 0 --pc 1390 \
  --r5 dfaadfaa --r9 20532036 --mask f0 \
  +ddr3_pin_even=20FF +ddr3_odd_clear=2

# Same words, fetched from ROM. The data compare passes. The CPU sits
# on the hold at 0x1F00 and R15 is still the reset value, so slot 33
# fails and the LED stays dark.
say "elaborate ddr3fetch FETCH_STORED=0"
if ! FETCH_STORED=0 SIM_IMAGE=ddr3fetch \
    BLINK3_IMEM=sim/obj_dir/ddr3fetch_n5.words \
    mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "FAIL elaborate ddr3fetch FETCH_STORED=0" >&2
  exit 1
fi
build ddr3fetch-rom verilator "${VFLAGS[@]}" -DPRINTF_COND=0 \
  --top-module CPUSimTop --Mdir sim/obj_dir/ddr3_cpu_ddr3fetch_rom -o ddr3_cpu \
  -CFLAGS "-std=c++17 -O2" \
  generated/CPUSimTopDdr3.v generated/InstrRom.v \
  sim/CpuClock.v sim/Ddr3UserModel.v sim/tb_ddr3_cpu.cpp
write_hex sim/obj_dir/ddr3fetch_n5.words
run sim/obj_dir/ddr3_cpu_ddr3fetch_rom/ddr3_cpu --cycles 80000 --edges 0 \
  --pc 1f00 --r5 00000000 --r9 ffffffe1 --mask 1ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7

# P/D chain on the same DDR3 port. The eye is the accepted fetch pair.
# The chain runs outside the delay loop, so the period stays 576*N+788.
# First edge is 38626 at N=5 (5076 cycles after the stored-BL image).
# Bare +ddr3_fetch_eye leaves the lanes at 10 and holds in the prologue.
python3 sim/build_pdchain_imem.py --mov-iter 5 --pad 2048 \
  --out sim/obj_dir/ddr3pd_n5.words
python3 sim/build_pdchain_imem.py --mov-iter 8 --pad 2048 \
  --out sim/obj_dir/ddr3pd_n8.words
python3 sim/build_pdchain_imem.py --mov-iter 32 --pad 2048 \
  --out sim/obj_dir/ddr3pd_n32.words
python3 sim/build_pdchain_imem.py --mov-iter 5 --pad 2048 --break-slot 32 \
  --out sim/obj_dir/ddr3pd_b32.words
elaborate ddr3pd sim/obj_dir/ddr3pd_n5.words
write_hex sim/obj_dir/ddr3pd_n5.words
CPU ddr3pd --cycles 80000 --edges 0 --pc 1390 \
  --r5 00544054 --r9 00a9c18c --mask 30 \
  +ddr3_fetch_eye
CPU ddr3pd --cycles 120000 --edges 2 --period 3668 --first 38626 \
  --pc 101c --r5 00000000 --r9 00000008 --mask 1fffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3pd_n8.words
CPU ddr3pd --cycles 100000 --edges 2 --period 5396 --first 40354 \
  --pc 101c --r5 00000000 --r9 00000008 --mask 1fffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3pd_n32.words
CPU ddr3pd --cycles 160000 --edges 2 --period 19220 --first 54178 \
  --pc 101c --r5 00000000 --r9 00000008 --mask 1fffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3pd_b32.words
CPU ddr3pd --cycles 80000 --edges 0 --pc 1d8c \
  --r5 00000000 --r9 00000008 --mask 1effffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7
write_hex sim/obj_dir/ddr3pd_n5.words
say "elaborate ddr3pd CHAIN_FIX=0"
if ! CHAIN_FIX=0 SIM_IMAGE=ddr3pd \
    BLINK3_IMEM=sim/obj_dir/ddr3pd_n5.words \
    mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "FAIL elaborate ddr3pd CHAIN_FIX=0" >&2
  exit 1
fi
build ddr3pd-rom verilator "${VFLAGS[@]}" -DPRINTF_COND=0 \
  --top-module CPUSimTop --Mdir sim/obj_dir/ddr3_cpu_ddr3pd_rom -o ddr3_cpu \
  -CFLAGS "-std=c++17 -O2" \
  generated/CPUSimTopDdr3.v generated/InstrRom.v \
  sim/CpuClock.v sim/Ddr3UserModel.v sim/tb_ddr3_cpu.cpp
write_hex sim/obj_dir/ddr3pd_n5.words
run sim/obj_dir/ddr3_cpu_ddr3pd_rom/ddr3_cpu --cycles 80000 --edges 0 \
  --pc 1d8c --r5 fffffff4 --r9 00000008 --mask ffffffffff \
  +ddr3_fetch_eye +ddr3_lane0=11 +ddr3_lane1=7

if [[ "$FAIL" -ne 0 ]]; then
  echo "stand-in mismatches" >&2
  exit 1
fi
echo "stand-in matches"
