#!/usr/bin/env bash
# Clone a pinned pdewacht/project-norebo and build it with its own build.sh.
# Default checkout: tools/project-norebo (gitignored). Override with NOREBO_ROOT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=norebo_env.sh
source "$ROOT/tools/norebo_env.sh"

norebo_read_pin
DEST="$(norebo_root)"

if [ -z "${NOREBO_URL:-}" ] || [ -z "${NOREBO_SHA:-}" ]; then
  echo "error: tools/norebo.pin is missing url= or sha=" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"

STAMP="$DEST/.blinky-pin"
need_clone=1
if [ -d "$DEST/.git" ]; then
  current="$(git -C "$DEST" rev-parse HEAD 2>/dev/null || true)"
  if [ "$current" = "$NOREBO_SHA" ]; then
    need_clone=0
  fi
elif [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$NOREBO_SHA" ] && norebo_is_built "$DEST"; then
  need_clone=0
fi

if [ "$need_clone" -eq 1 ]; then
  echo "=== Cloning $NOREBO_URL at $NOREBO_SHA ==="
  rm -rf "$DEST"
  git clone "$NOREBO_URL" "$DEST"
  git -C "$DEST" checkout --detach "$NOREBO_SHA"
fi

got="$(git -C "$DEST" rev-parse HEAD 2>/dev/null || cat "$STAMP" 2>/dev/null || true)"
if [ "$got" != "$NOREBO_SHA" ]; then
  echo "error: expected $NOREBO_SHA, got ${got:-empty}" >&2
  exit 1
fi

if norebo_is_built "$DEST" && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$NOREBO_SHA" ]; then
  echo "=== Norebo already built at $DEST ($NOREBO_SHA) ==="
else
  echo "=== Building Norebo with ./build.sh ==="
  (
    cd "$DEST"
    if [ -e build1 ] || [ -e build2 ] || [ -e build3 ]; then
      make clean
    fi
    ./build.sh
  )
fi

if ! norebo_is_built "$DEST"; then
  echo "error: build.sh finished but $DEST/build2/ORP.rsc is missing" >&2
  exit 1
fi

printf '%s\n' "$NOREBO_SHA" > "$STAMP"

echo "=== Norebo ready ==="
echo "NOREBO_ROOT=$DEST"
echo "commit=$NOREBO_SHA"
echo "Use: tools/process_mod_files.sh   or   tools/verify_raw_oberon_code.py"
