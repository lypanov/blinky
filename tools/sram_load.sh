#!/usr/bin/env bash
# Load a Gowin bitstream to FPGA SRAM only. Refuses flash programming.
#
# Usage:
#   tools/sram_load.sh <file.fs>
#   tools/sram_load.sh -b tangprimer20k <file.fs>
#   tools/sram_load.sh -b tangprimer20k --busdev 3:78 <file.fs>
#
# On Bee both the Primer 20K (bus 3 dev 78) and the Nano 4K (bus 3 dev 81)
# are FT2232 probes. Pass --busdev so the load cannot land on the other board.
set -euo pipefail

BOARD="tangprimer20k"
BUSDEV=""
FS=""

usage() {
  echo "usage: $0 [-b board] [--busdev bus:dev] <bitstream.fs>" >&2
  echo "always SRAM (-m). never flash." >&2
  exit "${1:-1}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    -b|--board) BOARD="$2"; shift 2 ;;
    --busdev|--busdev-num)
      BUSDEV="$2"
      shift 2
      ;;
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

[[ -n "$FS" ]] || usage 1
[[ -f "$FS" ]] || { echo "error: no such file $FS" >&2; exit 1; }

# Refuse if the path looks like a flash operation slipped in via env.
if [[ "${OPENFPGALOADER_FLASH:-}" == "1" ]]; then
  echo "error: OPENFPGALOADER_FLASH is set; refusing to run" >&2
  exit 1
fi

# Bee's Tang Nano 4K is USB bus 3 device 81. Do not select that probe.
if [[ "$BUSDEV" == "3:81" || "$BUSDEV" == "003:081" ]]; then
  echo "error: bus 3 dev 81 is the Tang Nano 4K. Refusing." >&2
  exit 1
fi

args=(openFPGALoader -b "$BOARD" -m "$FS")
if [[ -n "$BUSDEV" ]]; then
  args=(openFPGALoader --busdev-num "$BUSDEV" -b "$BOARD" -m "$FS")
fi
echo "SRAM load: ${args[*]}"
exec "${args[@]}"
