#!/bin/bash

# Exit on error
set -e

# Target directory for Gowin IDE
TARGET_DIR="/mnt/c/Gowin/Gowin_V1.9.11_x64/IDE/bin/Documents/blinky-test-1/src"

# Generate Verilog using Mill
echo "Generating Verilog..."
mill chisel-blinky.runMain gcd.Blinky

# Check if generation was successful
if [ ! -f "generated/Blinky.v" ]; then
  echo "Error: Verilog generation failed!"
  exit 1
fi

# Compare with existing file if it exists
if [ -f "$TARGET_DIR/Blinky.v" ]; then
  echo "Comparing with existing file..."
  diff -u "$TARGET_DIR/Blinky.v" "generated/Blinky.v" || true
else
  echo "No existing file to compare with."
fi

# Copy files to target directory
echo "Copying files to target directory..."
cp "generated/Blinky.v" "$TARGET_DIR/"
cp "tang-nano-4k.cst" "$TARGET_DIR/blinky.cst"

echo "Build and deploy completed successfully!"