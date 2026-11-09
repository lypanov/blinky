#!/usr/bin/env bash
# SRAM-load a bitstream onto the Tang Primer 20K Dock on Bee.
# The 20K is USB bus 3 device 78 (FT2232 on the Dock, via the hub).
# The Tang Nano 4K is bus 3 device 81. This script never opens it.
#
#   tools/beeb_sram_load.sh retro/beeb/build/impl/pnr/tang20k.fs
#   tools/beeb_sram_load.sh gowin/primer20k/impl/pnr/blink3_n262144.fs
#
# Always openFPGALoader -m. Refuses -f and any bus other than 3:78.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUSDEV="3:78"
BOARD="tangprimer20k"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "usage: $0 <bitstream.fs>"
  echo "SRAM only, Primer 20K, USB $BUSDEV. Never flash. Never the Nano 4K."
  exit 0
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <bitstream.fs>" >&2
  exit 1
fi

FS="$1"
case "$FS" in
  -f|--write-flash|--external-flash|--flash)
    echo "error: flash programming is forbidden" >&2
    exit 1
    ;;
esac
if [[ "$FS" == *tangnano4k* || "$FS" == *nano4k* ]]; then
  echo "error: refusing a Nano 4K bitstream" >&2
  exit 1
fi
if [[ "${OPENFPGALOADER_FLASH:-}" == "1" ]]; then
  echo "error: OPENFPGALOADER_FLASH is set; refusing to run" >&2
  exit 1
fi

# Reject a caller who exported a different cable. The 4K is 3:81.
if [[ -n "${OPENFPGALOADER_BUSDEV:-}" && "${OPENFPGALOADER_BUSDEV}" != "$BUSDEV" ]]; then
  echo "error: OPENFPGALOADER_BUSDEV=${OPENFPGALOADER_BUSDEV} is not $BUSDEV" >&2
  exit 1
fi

echo "Detect (read-only IDCODE) on bus $BUSDEV before SRAM load"
detect="$(openFPGALoader --busdev-num "$BUSDEV" --detect 2>&1)" || {
  echo "$detect" >&2
  echo "error: detect failed on $BUSDEV; not loading" >&2
  exit 1
}
echo "$detect"
if ! grep -q "GW2A" <<<"$detect"; then
  echo "error: $BUSDEV is not a GW2A (Primer 20K). Not loading." >&2
  exit 1
fi
if grep -q "GW1N" <<<"$detect"; then
  echo "error: $BUSDEV looks like the Nano 4K (GW1N). Not loading." >&2
  exit 1
fi

exec "$ROOT/tools/sram_load.sh" -b "$BOARD" --busdev "$BUSDEV" "$FS"
