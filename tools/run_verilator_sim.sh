#!/usr/bin/env bash
# Prove the two current images. Both boot the same disk.bin.
# The 4K reads it from the NOR model. The Dock reads it from the UART,
# with HyperRAM standing in for DDR3. N=5. The edge is 466*N+780.
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

echo "==> NOR disk boot"
"$ROOT/sim/run_disk_boot.sh" 5
echo "==> UART disk boot"
"$ROOT/sim/run_uart_disk.sh" 5
