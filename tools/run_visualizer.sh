#!/usr/bin/env bash
# Phase 2: run the Blink2 sim (if needed) and serve the local visualizer.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$REPO/core"
export PATH="${HOME}/bin:/usr/local/bin:${PATH}"
export CHISEL_CPU_PROJECT_ROOT="$CORE"
cd "$REPO"

PORT="${PORT:-8765}"

if [[ ! -f core/sim/visualizer/trace.json ]]; then
  echo "No core/sim/visualizer/trace.json yet — running Phase 1 sim first..."
  make -C core/sim sim
fi

# Keep program.json next to the page.
if [[ -f core/sim/out/program.json ]]; then
  cp -f core/sim/out/program.json core/sim/visualizer/program.json
fi

echo "Blink2 visualizer:  http://127.0.0.1:${PORT}/"
echo "Controls: Space run/pause, S step, R reset, [ ] slower/faster"
exec python3 "$CORE/sim/visualizer/serve.py" --port "$PORT"
