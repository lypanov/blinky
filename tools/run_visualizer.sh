#!/usr/bin/env bash
# Phase 2: run the Blink2 sim (if needed) and serve the local visualizer.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$ROOT"
cd "$ROOT"

PORT="${PORT:-8765}"

if [[ ! -f sim/visualizer/trace.json ]]; then
  echo "No sim/visualizer/trace.json yet — running Phase 1 sim first..."
  make -C sim sim
fi

# Keep program.json next to the page.
if [[ -f sim/out/program.json ]]; then
  cp -f sim/out/program.json sim/visualizer/program.json
fi

echo "Blink2 visualizer:  http://127.0.0.1:${PORT}/"
echo "Controls: Space run/pause, S step, R reset, [ ] slower/faster"
exec python3 "$ROOT/sim/visualizer/serve.py" --port "$PORT"
