#!/usr/bin/env bash
# DDR3 CPU image (N=5) through ddr3_controller + Micron ddr3.v + gw2a prim_sim.
# IMAGE=ddr3moddesc (default) is the step-6 module table.
# IMAGE=ddr3files is the step-7 Files table. IMAGE=ddr3modules is the
# step-8 Modules reset path. The period check is the delay loop, which
# these images enter only after a zero compare.
# Does not instantiate Ddr3UserModel and does not load either FPGA.
# Exit 0 only when the bench prints PHY_SCORE pass and the log has no
# Micron ERROR.
set -u
cd "$(dirname "$0")/.."

export PATH="${HOME}/.local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$(pwd)"
unset SIM_IMAGE DDR3_PHY BLINK3_IMEM

PRIM_SRC="${GOWIN_PRIM_SIM:-/opt/gowin-eda-ide/simlib/gw2a/prim_sim.v}"
if [[ ! -f "$PRIM_SRC" ]]; then
  echo "FAIL missing Gowin prim_sim ($PRIM_SRC)" >&2
  exit 1
fi
if ! command -v iverilog >/dev/null || ! command -v vvp >/dev/null; then
  echo "FAIL iverilog or vvp is not on PATH" >&2
  exit 1
fi
if ! command -v mill >/dev/null; then
  echo "FAIL mill is not on PATH" >&2
  exit 1
fi

IMAGE="${IMAGE:-ddr3moddesc}"
case "$IMAGE" in
  ddr3modules) BUILD=sim/link_inner.py ;;
  ddr3files) BUILD=sim/build_files_imem.py ;;
  ddr3moddesc) BUILD=sim/build_moddesc_imem.py ;;
  *)
    echo "FAIL image $IMAGE (ddr3moddesc, ddr3files, or ddr3modules)" >&2
    exit 1
    ;;
esac

mkdir -p sim/obj_dir
WORDS=sim/obj_dir/${IMAGE}_n5.words
echo "words $WORDS"
python3 "$BUILD" --mov-iter 5 --pad 2048 --out "$WORDS"

echo "elaborate $IMAGE"
if ! SIM_IMAGE="$IMAGE" DDR3_PHY=micron BLINK3_IMEM="$WORDS" \
    mill chisel-blinky.runMain gcd.CPUSimTop; then
  echo "FAIL elaborate" >&2
  exit 1
fi

# Same DQS transport-delay patch as run_ddr3_phy.sh.
PRIM=sim/obj_dir/prim_sim_fastdqs.v
python3 sim/patch_prim_dqs.py "$PRIM_SRC" "$PRIM"
OUT=sim/obj_dir/ddr3_cpu_phy.vvp
LOG=sim/obj_dir/ddr3_cpu_phy.log
echo "iverilog $(iverilog -V 2>&1 | head -1)"
ROM_V=(generated/InstrRom.v)
if ! iverilog -g2012 -s tb_ddr3_cpu_phy -o "$OUT" \
  -D SIM -D den1024Mb -D sg25 -D x16 -DPRINTF_COND=0 \
  -I sim/micron \
  sim/ddr3_phy/tb_ddr3_cpu_phy.v \
  sim/micron/ddr3.v \
  gowin/primer20k/ddr3/ddr3_controller.v \
  generated/CPUSimTopDdr3.v \
  "${ROM_V[@]}" \
  sim/CpuClock.v \
  "$PRIM"; then
  echo "FAIL iverilog" >&2
  exit 1
fi

mkdir -p /tmp/ddr3-cpu-phy-model
# Files and Modules leave R9 at 0. ModDesc leaves the module number 8.
R9_ARG=()
if [[ "$IMAGE" == "ddr3files" || "$IMAGE" == "ddr3modules" ]]; then
  R9_ARG+=(+expect_r9=0)
fi
if ! stdbuf -oL -eL vvp "$OUT" +model_data+/tmp/ddr3-cpu-phy-model "${R9_ARG[@]}" "$@" >"$LOG" 2>&1; then
  echo "FAIL vvp" >&2
  tail -40 "$LOG" >&2
  exit 1
fi

if grep -q '^ERROR:' "$LOG"; then
  echo "FAIL Micron ERROR" >&2
  grep '^ERROR:' "$LOG" | head -20 >&2
  exit 1
fi
if grep -q '^PHY_SCORE pass$' "$LOG"; then
  echo "PHY_SCORE pass"
  exit 0
fi
echo "FAIL PHY_SCORE" >&2
grep -E '^(CALIB|END|PHY_SCORE|LED|READ|RUN) ' "$LOG" | tail -30 >&2
exit 1
