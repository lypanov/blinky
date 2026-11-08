#!/usr/bin/env bash
# Icarus sim of the Nano 4K external-SPI pathfinder. No DDR3 model.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The four images publish these half-periods. Fail if a header drifts.
grep -q 'SPI_RATE_A_HALF 9000000' "$ROOT/gowin/spi_flash_rates.vh"
grep -q 'SPI_RATE_B_HALF 5400000' "$ROOT/gowin/spi_flash_rates.vh"
grep -q 'SPI_RATE_C_HALF 3375000' "$ROOT/gowin/spi_flash_rates.vh"
grep -q 'SPI_BUILD_YES 8'"'"'h7B' "$ROOT/gowin/spi_flash_rates.vh"
grep -q 'SPI_BUILD_NO 8'"'"'h7C' "$ROOT/gowin/spi_flash_rates.vh"
grep -q 'SPI_PAGE_ADDR 24'"'"'h3FF000' "$ROOT/gowin/spi_flash_rates.vh"
mkdir -p "$ROOT/sim/out"
iverilog -g2012 -o "$ROOT/sim/out/spi_flash_pathfinder.vvp" \
  "$ROOT/gowin/spi_flash_pathfinder.v" \
  "$ROOT/sim/spi_flash_model.v" \
  "$ROOT/sim/tb_spi_flash_pathfinder.v"
vvp "$ROOT/sim/out/spi_flash_pathfinder.vvp"
