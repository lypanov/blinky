#!/usr/bin/env bash
# Verilator of the button sampler at both board clocks. No CPU, no DDR3.
# The level is bit 0 of -60. It does not force the LED pin.
# --div 117 is the Nano 4K cpu_clk (13.5 MHz / 115200).
# --div 210 is the Dock cpu_clk (24.1875 MHz / 115200).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

build() {
  local div="$1"
  local name="$2"
  local mdir="$ROOT/sim/obj_dir_gate_${div}"
  verilator --cc --exe --build \
    -GCLKS_PER_BIT="${div}" \
    --top-module button_gate \
    -Wno-fatal -Wno-UNUSED \
    --Mdir "$mdir" \
    -o "gate_${div}" \
    "$ROOT/gowin/button_gate.v" \
    "$ROOT/sim/tb_button_gate.cpp"
  "$mdir/gate_${div}" --div "$div" --name "$name"
}

build 117 nano4k
build 210 dock
