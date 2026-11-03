#!/usr/bin/env bash
# Phase 1: generate CPUSimTop Verilog (Blink2test, short sim delay),
# Verilate, run, dump FST + LED log + waveform PNG.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
cd "$ROOT"

if ! command -v mill >/dev/null 2>&1; then
  echo "error: mill not on PATH (need Mill 0.12.x). Install: https://mill-build.org/" >&2
  exit 1
fi
if ! command -v verilator >/dev/null 2>&1; then
  echo "error: verilator not on PATH. Arch: pacman -S verilator   macOS: brew install verilator" >&2
  exit 1
fi

make -C sim sim "$@"
echo ""
echo "GTKWave:"
echo "  gtkwave -S $ROOT/sim/gtkwave_led.tcl $ROOT/sim/out/blink2.fst $ROOT/sim/gtkwave_led.gtkw"
