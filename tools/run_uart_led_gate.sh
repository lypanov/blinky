#!/usr/bin/env bash
# Verilator proof that a UART press byte forces the Blink3 LED pin off
# without stalling the CPU, and a release byte resumes in phase.
# Does not load or flash an FPGA and does not open a serial device.
#
#   tools/run_uart_led_gate.sh
#
# N=5 so several 15N+18 edges fit around one 115200-baud frame
# (234 cycles/bit at 27 MHz, 2340 cycles for an 8N1 byte).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/.local/bin:${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
cd "$ROOT"

N="${N:-5}"
PRESS_AT="${PRESS_AT:-500}"
RELEASE_AT="${RELEASE_AT:-4200}"
CYCLES="${CYCLES:-7800}"
PREDICT="$(python3 -c 'import sys; sys.path.insert(0,"sim"); from imem_layout import blink3_cycles_per_edge; print(blink3_cycles_per_edge(int(sys.argv[1])))' "$N")"

OUT="$ROOT/sim/out"
DOCS="$ROOT/docs/uart-led-gate"
mkdir -p "$OUT" "$DOCS" "$ROOT/generated" "$ROOT/sim/visualizer/traces"

WORDS="$OUT/uart_gate_n${N}.words"
python3 "$ROOT/sim/build_blink3_imem.py" --max-iter "$N" --out "$WORDS"

echo "[uart-gate] Verilog N=$N (CPU edge ${PREDICT} cycles), press@${PRESS_AT} release@${RELEASE_AT}"
( cd "$ROOT" && BLINK3_IMEM="sim/out/uart_gate_n${N}.words" SIM_IMAGE=blink3 mill chisel-blinky.runMain gcd.CPUSimTop )

VFILE="$ROOT/generated/CPUSimTopUartGate.v"
cp -f "$ROOT/generated/CPUSimTopBlink3.v" "$VFILE"
rm -f "$ROOT/generated/CPUSimTopBlink3.v"

MDIR="$ROOT/sim/obj_dir_uart_gate"
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

"$MDIR/cpu_sim" \
	--program blink3 \
	--cycles "$CYCLES" \
	--toggles 0 \
	--reset 4 \
	--fst "$OUT/uart_gate_n${N}.fst" \
	--led "$OUT/uart_gate_n${N}_toggles.csv" \
	--wave "$OUT/uart_gate_n${N}_wave.csv" \
	--trace "$OUT/uart_gate_n${N}_trace.json" \
	--uart-press "$PRESS_AT" \
	--uart-release "$RELEASE_AT"

python3 "$ROOT/sim/annotate_trace.py" \
	--image blink3 \
	--imem "$WORDS" \
	--trace "$OUT/uart_gate_n${N}_trace.json" \
	--wave "$OUT/uart_gate_n${N}_wave.csv" \
	--program "$OUT/uart_gate_n${N}_program.json" \
	--out "$OUT/uart_gate_n${N}_annotated.json" \
	--visualizer "$ROOT/sim/visualizer/traces/uartgate.json"
cp -f "$OUT/uart_gate_n${N}_program.json" "$ROOT/sim/visualizer/traces/uartgate_program.json"

python3 "$ROOT/sim/plot_uart_gate.py" \
	--csv "$OUT/uart_gate_n${N}_wave.csv" \
	--png "$DOCS/uart_gate_n${N}.png" \
	--title "Blink3 LED pin vs CPU register   N=${N}   UART 0x01 / 0x00" \
	--note "Shaded band is the press latch. Pin is forced 0; CPU edges stay ${PREDICT} cycles (15*${N}+18). Release makes the pin follow the register again."

python3 "$ROOT/sim/check_uart_gate.py" \
	--wave "$OUT/uart_gate_n${N}_wave.csv" \
	--n "$N" \
	--out "$DOCS/uart_gate_n${N}.txt" \
	--visualizer "$ROOT/sim/visualizer/traces/uartgate.json"

echo "[uart-gate] $DOCS/uart_gate_n${N}.png"

# Active-low button held across many 93-cycle CPU edges. UART stays idle.
BTN_DOWN="${BTN_DOWN:-400}"
BTN_UP="${BTN_UP:-2000}"
BTN_CYCLES="${BTN_CYCLES:-2800}"
echo "[uart-gate] button hold ${BTN_DOWN}..${BTN_UP}"
"$MDIR/cpu_sim" \
	--program blink3 \
	--cycles "$BTN_CYCLES" \
	--toggles 0 \
	--reset 4 \
	--fst "$OUT/btn_gate_n${N}.fst" \
	--led "$OUT/btn_gate_n${N}_toggles.csv" \
	--wave "$OUT/btn_gate_n${N}_wave.csv" \
	--trace "$OUT/btn_gate_n${N}_trace.json" \
	--btn-down "$BTN_DOWN" \
	--btn-up "$BTN_UP"

python3 "$ROOT/sim/plot_uart_gate.py" \
	--csv "$OUT/btn_gate_n${N}_wave.csv" \
	--png "$DOCS/btn_gate_n${N}.png" \
	--title "Blink3 LED pin vs CPU register   N=${N}   button held low" \
	--note "Shaded band is S1 held (active-low, 2-flop sync). Pin is forced 0; CPU edges stay ${PREDICT} cycles. Release makes the pin follow the register again."

python3 "$ROOT/sim/check_uart_gate.py" \
	--wave "$OUT/btn_gate_n${N}_wave.csv" \
	--n "$N" \
	--out "$DOCS/btn_gate_n${N}.txt"

echo "[uart-gate] $DOCS/btn_gate_n${N}.png"
echo "[uart-gate] visualizer http://127.0.0.1:\${PORT:-8765}/?p=uartgate&gate=off"
