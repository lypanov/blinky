#!/usr/bin/env bash
# ddr3pd (N=5) through ddr3_controller + Micron ddr3.v + gw2a prim_sim.
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

mkdir -p sim/obj_dir
WORDS=sim/obj_dir/ddr3pd_n5.words
echo "words $WORDS"
python3 sim/build_pdchain_imem.py --mov-iter 5 --pad 2048 --out "$WORDS"

echo "elaborate ddr3pd"
if ! SIM_IMAGE=ddr3pd DDR3_PHY=micron BLINK3_IMEM="$WORDS" \
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
if ! iverilog -g2012 -s tb_ddr3_cpu_phy -o "$OUT" \
  -D SIM -D den1024Mb -D sg25 -D x16 -DPRINTF_COND=0 \
  -I sim/micron \
  sim/ddr3_phy/tb_ddr3_cpu_phy.v \
  sim/micron/ddr3.v \
  gowin/primer20k/ddr3/ddr3_controller.v \
  generated/CPUSimTopDdr3.v \
  generated/InstrRom.v \
  sim/CpuClock.v \
  "$PRIM"; then
  echo "FAIL iverilog" >&2
  exit 1
fi

mkdir -p /tmp/ddr3-cpu-phy-model
if ! stdbuf -oL -eL vvp "$OUT" +model_data+/tmp/ddr3-cpu-phy-model "$@" >"$LOG" 2>&1; then
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
