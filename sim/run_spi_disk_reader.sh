#!/usr/bin/env bash
# Icarus sim of the Nano 4K flash-disk reader. No DDR3 model.
# Builds disk.bin, then reads that file from a small SPI NOR model.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/sim/out"

grep -q 'DISK_MAGIC       32'"'"'h314B5344' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'DISK_VERSION     32'"'"'h00000001' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'DISK_BUILD       32'"'"'h000000D1' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'DISK_BUILD_NEG   32'"'"'h000000D2' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'DISK_BASE        24'"'"'h200000' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'DISK_BLINK_HALF  6750000' "$ROOT/gowin/spi_disk_rates.vh"
grep -q 'MAGIC = 0x314B5344' "$ROOT/tools/build_disk_image.py"
grep -q 'BUILD = 0xD1' "$ROOT/tools/build_disk_image.py"
grep -q 'FLASH_BASE = 0x200000' "$ROOT/tools/build_disk_image.py"

python3 "$ROOT/tools/build_disk_image.py" --out "$ROOT/sim/out/disk.bin"

iverilog -g2012 -I "$ROOT/gowin" -o "$ROOT/sim/out/spi_disk_reader.vvp" \
  "$ROOT/gowin/spi_flash_pathfinder.v" \
  "$ROOT/gowin/spi_disk_reader.v" \
  "$ROOT/sim/spi_disk_model.v" \
  "$ROOT/sim/tb_spi_disk_reader.v"
vvp "$ROOT/sim/out/spi_disk_reader.vvp"
