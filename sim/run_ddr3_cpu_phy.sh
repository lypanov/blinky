#!/usr/bin/env bash
# The Micron bench still ties the disk port off, so it cannot boot the
# UART disk that the Dock runs. The images it used to elaborate are
# retired. Do not start this run. A real DDR3 failure (calibration,
# write eye, controller, or Micron protocol) is what would bring a
# disk-fed bench back.
echo "the Micron CPU bench cannot boot the UART disk; it is not the proof" >&2
exit 1
