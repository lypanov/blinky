#!/usr/bin/env bash
# Run Blink3 (Oberon RISC5 on CPUSubset0) in Verilator with a small N and
# check that each LED edge is 15N+18 cycles. Does not load or flash an FPGA.
#
#   tools/run_blink3_period.sh        # N=5, predicted 93 cycles/edge
#   tools/run_blink3_period.sh 8      # N=8, predicted 138 cycles/edge
#
# N=5 is wired into the visualizer as ?p=blink3n5. The hardware image stays
# maxIterations=262144 (MHI); this only patches the sim IMEM.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/.local/bin:${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
cd "$ROOT"

N="${1:-5}"
TOGGLES="${TOGGLES:-6}"
PREDICT="$(python3 -c 'import sys; sys.path.insert(0,"sim"); from imem_layout import blink3_cycles_per_edge; print(blink3_cycles_per_edge(int(sys.argv[1])))' "$N")"
CYCLES="${CYCLES:-$(( PREDICT * (TOGGLES + 2) + 4000 ))}"

OUT="$ROOT/sim/out"
DOCS="$ROOT/docs/sim-bee"
mkdir -p "$OUT" "$DOCS" "$ROOT/generated" "$ROOT/sim/visualizer/traces"

WORDS="$OUT/blink3_n${N}.words"
python3 "$ROOT/sim/build_blink3_imem.py" --max-iter "$N" --out "$WORDS"

echo "[blink3] generating Verilog for N=$N (predicted ${PREDICT} cycles/edge)"
# Path is relative to the repo root. CPUSimTop also accepts an absolute BLINK3_IMEM.
( cd "$ROOT" && BLINK3_IMEM="sim/out/blink3_n${N}.words" SIM_IMAGE=blink3 mill chisel-blinky.runMain gcd.CPUSimTop )

VFILE="$ROOT/generated/CPUSimTopBlink3_n${N}.v"
cp -f "$ROOT/generated/CPUSimTopBlink3.v" "$VFILE"
# Drop the canonical Verilog so `make -C sim run-blink3` rebuilds the
# hardware-delay image instead of reusing this small-N netlist.
rm -f "$ROOT/generated/CPUSimTopBlink3.v"

MDIR="$ROOT/sim/obj_dir_blink3_n${N}"
echo "[blink3] verilating into $MDIR"
verilator --cc --exe --build --trace-fst \
	--top-module CPUSimTop \
	--timescale 1ns/1ps \
	-DPRINTF_COND=0 \
	-Wno-fatal \
	-Wno-WIDTH -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
	-Wno-UNUSED -Wno-UNDRIVEN -Wno-PINMISSING \
	-CFLAGS "-std=c++17 -O2" \
	--Mdir "$MDIR" \
	-o cpu_sim \
	"$VFILE" "$ROOT/sim/tb_blink2.cpp"

echo "[blink3] simulating up to $CYCLES cycles or $TOGGLES LED edges"
"$MDIR/cpu_sim" \
	--program blink3 \
	--cycles "$CYCLES" \
	--toggles "$TOGGLES" \
	--reset 4 \
	--fst "$OUT/blink3_n${N}.fst" \
	--led "$OUT/blink3_n${N}_toggles.csv" \
	--wave "$OUT/blink3_n${N}_wave.csv" \
	--trace "$OUT/blink3_n${N}_trace.json"

python3 "$ROOT/sim/annotate_trace.py" \
	--image blink3 \
	--imem "$WORDS" \
	--trace "$OUT/blink3_n${N}_trace.json" \
	--wave "$OUT/blink3_n${N}_wave.csv" \
	--program "$OUT/blink3_n${N}_program.json" \
	--out "$OUT/blink3_n${N}_annotated.json" \
	--visualizer "$ROOT/sim/visualizer/traces/blink3_n${N}.json"
cp -f "$OUT/blink3_n${N}_program.json" "$ROOT/sim/visualizer/traces/blink3_n${N}_program.json"

python3 "$ROOT/sim/plot_led.py" \
	--csv "$OUT/blink3_n${N}_wave.csv" \
	--toggles "$OUT/blink3_n${N}_toggles.csv" \
	--png "$DOCS/blink3_led_n${N}.png" \
	--title "Blink3 LED   N=${N}   Verilator CPUSubset0" \
	--predict "$PREDICT" \
	--note "Edge period is 15*${N}+18 = ${PREDICT} cycles. At 27 MHz that is one edge; a full blink (on+off) is two edges. Hardware Blink3 keeps N=262144."

python3 "$ROOT/sim/check_blink3_period.py" \
	--n "$N" \
	--toggles "$OUT/blink3_n${N}_toggles.csv" \
	--out "$DOCS/blink3_n${N}.txt"

echo "[blink3] waveform $DOCS/blink3_led_n${N}.png"
echo "[blink3] visualizer trace sim/visualizer/traces/blink3_n${N}.json"
echo "[blink3] open http://127.0.0.1:\${PORT:-8765}/?p=blink3n5&led=1"
echo "[blink3] 8765 may already be an older visualizer; PORT=8767 tools/run_visualizer.sh"
