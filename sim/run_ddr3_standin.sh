#!/usr/bin/env bash
# The step images this script proved (ddr3, fixup, reader, stored BL,
# P/D chain, ModDesc, Files) are retired. The Dock image is the UART
# disk, proved by sim/run_uart_disk.sh. A Micron blink is not started
# from here.
echo "the DDR3 stand-in step images are retired; run sim/run_uart_disk.sh" >&2
exit 1
