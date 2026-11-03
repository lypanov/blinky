#!/bin/bash
# Legacy WSL copy into a Gowin IDE Documents folder.
# Prefer tools/gowin_build.sh (Bee / Linux Gowin).

set -e

CORE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$CORE/.." && pwd)"
export CHISEL_CPU_PROJECT_ROOT="$CORE"
cd "$REPO"

# Target directory for Gowin IDE
TARGET_DIR="/mnt/c/Gowin/Gowin_V1.9.11_x64/IDE/bin/Documents/blinky-test-1/src"

# Generate Verilog using Mill
echo "Generating CPUSubset0 Verilog..."
mill chisel-blinky.runMain gcd.CPUSubset0

# Check if generation was successful
if [ ! -f "generated/CPUMinimalWrapper.v" ]; then
  echo "Error: Verilog generation failed!"
  exit 1
fi

# Compare with existing file if it exists
if [ -f "$TARGET_DIR/Blinky.v" ]; then
  echo "Comparing with existing file..."
  diff -u "$TARGET_DIR/Blinky.v" "generated/CPUMinimalWrapper.v" || true
else
  echo "No existing file to compare with."
fi

# Copy files to target directory
echo "Copying files to target directory..."
cp "generated/CPUMinimalWrapper.v" "$TARGET_DIR/Blinky.v"
cp "$REPO/nano4k/tang-nano-4k.cst" "$TARGET_DIR/blinky.cst"

echo "Build and deploy completed successfully!"
