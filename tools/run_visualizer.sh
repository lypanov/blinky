#!/usr/bin/env bash
# Serve the Blink2 / Blink3 visualizer on loopback (SSH-forward from the Mac).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
cd "$ROOT"

PORT="${PORT:-8765}"
BIND="${BIND:-127.0.0.1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --bind) BIND="$2"; shift 2 ;;
    --lan) BIND="0.0.0.0"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f sim/visualizer/traces/blink2.json || ! -f sim/visualizer/traces/blink3.json ]]; then
  echo "Committed traces missing — generating both with Verilator..."
  make -C sim traces
fi

echo ""
echo "Visualizer bound on ${BIND}:${PORT}  (not the public internet)"
echo "  local:   http://127.0.0.1:${PORT}/"
echo "  Blink3:  http://127.0.0.1:${PORT}/?p=blink3"
echo "  N=5:     http://127.0.0.1:${PORT}/?p=blink3n5"
echo "  UART:    http://127.0.0.1:${PORT}/?p=uartgate&gate=off"
echo "  delay:   http://127.0.0.1:${PORT}/?p=blink3&delay"
echo "  BEGIN:   http://127.0.0.1:${PORT}/?p=blink3&init"
echo "  light:=0 http://127.0.0.1:${PORT}/?p=blink3&light"
echo ""
echo "From Alex's Mac (SSH port forward; Bee stays loopback-only):"
echo "  ssh -N -L ${PORT}:127.0.0.1:${PORT} bee"
echo "  open http://127.0.0.1:${PORT}/"
echo ""
echo "LAN-only (same Wi-Fi as Bee, still not the internet):"
echo "  tools/run_visualizer.sh --bind 0.0.0.0"
echo "  then http://<bee-lan-ip>:${PORT}/"
echo ""
echo "Controls: Space run/pause, S/→ next instr, A/← prev, I AMMT BEGIN, L light:=0, D delay 262144, F jump to BL Toggle, 2/3/5 switch program (5 = Blink3 N=5)"
exec python3 "$ROOT/sim/visualizer/serve.py" --port "$PORT" --bind "$BIND"
