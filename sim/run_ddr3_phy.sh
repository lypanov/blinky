#!/usr/bin/env bash
# Icarus + Micron ddr3.v + Gowin gw2a prim_sim against ddr3_controller.
# Does not build a bitstream and does not load either FPGA.
# Exit 0 only when the bench prints PHY_SCORE pass.
set -u
cd "$(dirname "$0")/.."

export PATH="${HOME}/.local/bin:${PATH}"

PRIM="${GOWIN_PRIM_SIM:-/opt/gowin-eda-ide/simlib/gw2a/prim_sim.v}"
if [[ ! -f "$PRIM" ]]; then
  echo "FAIL missing Gowin prim_sim ($PRIM)" >&2
  echo "Set GOWIN_PRIM_SIM to gw2a/prim_sim.v from the Gowin IDE." >&2
  exit 1
fi
if ! command -v iverilog >/dev/null || ! command -v vvp >/dev/null; then
  echo "FAIL iverilog or vvp is not on PATH" >&2
  exit 1
fi

mkdir -p sim/obj_dir
OUT=sim/obj_dir/ddr3_phy.vvp
LOG=sim/obj_dir/ddr3_phy.log

echo "iverilog $(iverilog -V 2>&1 | head -1)"
if ! iverilog -g2012 -s tb_ddr3_phy -o "$OUT" \
  -D SIM -D den1024Mb -D sg25 -D x16 \
  -I sim/micron \
  sim/ddr3_phy/tb_ddr3_phy.v \
  sim/micron/ddr3.v \
  gowin/primer20k/ddr3/ddr3_controller.v \
  "$PRIM"; then
  echo "FAIL iverilog" >&2
  exit 1
fi

# Private sparse-memory files. The model defaults to /tmp/%m, and a
# second bench would share those files.
mkdir -p /tmp/ddr3-phy-model
if ! stdbuf -oL -eL vvp "$OUT" +model_data+/tmp/ddr3-phy-model >"$LOG" 2>&1; then
  echo "FAIL vvp" >&2
  tail -40 "$LOG" >&2
  exit 1
fi

# Show the bench lines. The Micron model stays in the log.
grep -E '^(CALIB|READ |FAIL |PHY_|MEM |CMD |HIT |ALIAS |Entering |Write leveling|wstep=|All initialization)' "$LOG" || true

fail=0
if ! grep -q '^PHY_SCORE pass$' "$LOG"; then
  echo "PHY_SCORE fail" >&2
  fail=1
fi
# Any Micron ERROR fails the run, including init. A byte match does
# not hide one. Warnings from the shortened reset and CKE stay in
# the log and do not pass the run by themselves.
if awk '/ERROR:/ {found=1} END {exit !found}' "$LOG"; then
  echo "FAIL Micron ERROR" >&2
  awk '/ERROR:/ {print}' "$LOG" | head -20 >&2
  fail=1
fi
if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "PHY_SCORE pass"
