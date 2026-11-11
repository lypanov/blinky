#!/usr/bin/env bash
# Write the disk image to the Nano 4K external NOR and read it back.
# The only flash write is this data file, at 0x200000. Never a bitstream,
# never the Primer, never an address below 0x200000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:-$ROOT/sim/out/disk.bin}"
BOARD="${BOARD:-tangnano4k}"
OFFSET=0x200000
LIMIT=$((0x400000))
OUT="${OUT:-$ROOT/sim/out}"
# The Nano 4K is USB port 3-3.3. The device number moves when the cable
# is replugged. The Dock is port 3-3.1.1, and a stale bus number must
# not select it.
NANO_PORT="3-3.3"
PORT_SYS="/sys/bus/usb/devices/${NANO_PORT}"

if [[ "$BOARD" != "tangnano4k" ]]; then
  echo "error: disk writes are Nano 4K only" >&2
  exit 1
fi
if [[ ! -f "$PORT_SYS/busnum" || ! -f "$PORT_SYS/devnum" ]]; then
  echo "error: Nano 4K port $NANO_PORT is not present" >&2
  exit 1
fi
FOUND="$(printf '%03d:%03d' "$(cat "$PORT_SYS/busnum")" "$(cat "$PORT_SYS/devnum")")"
if [[ -n "${BUS:-}" && "$BUS" != "$FOUND" ]]; then
  echo "error: BUS=$BUS is not the Nano on $NANO_PORT ($FOUND)" >&2
  exit 1
fi
BUS="$FOUND"
echo "Nano NOR write: port $NANO_PORT bus $BUS"
case "$IMAGE" in
  *.fs|*.bit|*.bin.bak)
    echo "error: refusing $IMAGE; this script writes the data file only" >&2
    exit 1
    ;;
esac
if [[ ! -f "$IMAGE" ]]; then
  echo "error: $IMAGE does not exist" >&2
  exit 1
fi

python3 - "$IMAGE" "$OFFSET" "$LIMIT" <<'PY'
import struct, sys
path, offset, limit = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3])
data = open(path, "rb").read()
if offset != 0x200000:
    raise SystemExit(f"offset {offset:#x} is outside the disk region")
if offset + len(data) > limit:
    raise SystemExit(f"image ends at {offset + len(data):#x}, past {limit:#x}")
magic, version, build, length, sum_ = struct.unpack_from("<5I", data, 0)
if magic != 0x314B5344 or version != 1 or build != 0xE1:
    raise SystemExit(f"refusing header {magic:#x} {version} {build:#x}")
payload = data[20:]
if length != len(payload):
    raise SystemExit("length field does not match the file")
got = 0
for i in range(0, len(payload), 4):
    got = (got + int.from_bytes(payload[i:i+4], "little")) & 0xFFFFFFFF
if got != sum_:
    raise SystemExit(f"checksum {got:08x} != {sum_:08x}")
print(f"[ok] {path} {len(data)} bytes at {offset:#x} checksum {sum_:08x}")
PY

mkdir -p "$OUT"
GUARD_BEFORE="$OUT/guard_before.bin"
GUARD_AFTER="$OUT/guard_after.bin"
READBACK="$OUT/disk_readback.bin"
SIZE="$(stat -c %s "$IMAGE")"

echo "==> read 256 bytes at 0x1FFF00 before the write"
openFPGALoader --busdev-num "$BUS" -b "$BOARD" \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  "$GUARD_BEFORE"

echo "==> write $IMAGE at 0x200000 (external NOR, data file)"
openFPGALoader --busdev-num "$BUS" -b "$BOARD" \
  -f --external-flash -o 0x200000 --verify \
  "$IMAGE"

echo "==> read $SIZE bytes at 0x200000"
openFPGALoader --busdev-num "$BUS" -b "$BOARD" \
  --external-flash --dump-flash -o 0x200000 --file-size "$SIZE" \
  "$READBACK"
cmp "$IMAGE" "$READBACK"
echo "[ok] read-back matches $IMAGE"

echo "==> read 256 bytes at 0x1FFF00 after the write"
openFPGALoader --busdev-num "$BUS" -b "$BOARD" \
  --external-flash --dump-flash -o 0x1FFF00 --file-size 256 \
  "$GUARD_AFTER"
cmp "$GUARD_BEFORE" "$GUARD_AFTER"
echo "[ok] bytes below 0x200000 are unchanged"
