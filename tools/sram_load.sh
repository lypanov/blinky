#!/usr/bin/env bash
# Load a Gowin bitstream to FPGA SRAM only. Refuses flash programming.
#
# Usage:
#   tools/sram_load.sh -b tangnano4k <file.fs>
#   tools/sram_load.sh -b tangprimer20k <file.fs>
set -euo pipefail

BOARD=""
FS=""

usage() {
  echo "usage: $0 -b board <bitstream.fs>" >&2
  echo "board is required: tangnano4k or tangprimer20k" >&2
  echo "always SRAM (-m). never flash." >&2
  exit "${1:-1}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    -b|--board) BOARD="$2"; shift 2 ;;
    -f|--write-flash|--external-flash|--flash)
      echo "error: flash programming is forbidden. SRAM only (-m)." >&2
      exit 1
      ;;
    -m) shift ;;
    -*) echo "error: unknown flag $1 (refusing anything that is not SRAM)" >&2; usage 1 ;;
    *)
      if [[ -n "$FS" ]]; then
        echo "error: extra argument $1" >&2
        usage 1
      fi
      FS="$1"
      shift
      ;;
  esac
done

[[ -n "$BOARD" ]] || { echo "error: -b board is required" >&2; usage 1; }
[[ -n "$FS" ]] || usage 1
[[ -f "$FS" ]] || { echo "error: no such file $FS" >&2; exit 1; }

# Refuse if the path looks like a flash operation slipped in via env.
if [[ "${OPENFPGALOADER_FLASH:-}" == "1" ]]; then
  echo "error: OPENFPGALOADER_FLASH is set; refusing to run" >&2
  exit 1
fi

echo "SRAM load: openFPGALoader -b $BOARD -m $FS"
exec openFPGALoader -b "$BOARD" -m "$FS"
