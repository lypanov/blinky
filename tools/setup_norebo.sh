#!/usr/bin/env bash
# Create the pinned pdewacht/project-norebo tree and build it with its
# own build.sh. On this machine that tree is
# /home/lypanov/fpga/norebo-compiled, outside every worktree. GitHub CI
# has no /home/lypanov/fpga, so the same script installs
# tools/project-norebo (gitignored). Override with NOREBO_INSTALL_ROOT.
#
# The live destination is never rm -rf'd. A matching built tree is a
# no-op. A present-but-wrong machine tree is a refuse: move it aside
# and re-run. A present-but-wrong worktree copy is moved aside, then
# replaced from a staging clone.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=norebo_env.sh
source "$ROOT/tools/norebo_env.sh"

norebo_read_pin
DEST="$(norebo_install_root)"
MACHINE="$(norebo_machine_root)"

if [ -z "${NOREBO_URL:-}" ] || [ -z "${NOREBO_SHA:-}" ]; then
  echo "error: tools/norebo.pin is missing url= or sha=" >&2
  exit 1
fi

STAMP="$DEST/.blinky-pin"

if norebo_is_built "$DEST"; then
  got="$(norebo_got_sha "$DEST")"
  if [ "$got" = "$NOREBO_SHA" ]; then
    printf '%s\n' "$NOREBO_SHA" > "$STAMP"
    echo "=== Norebo already built at $DEST ($NOREBO_SHA) ==="
    echo "NOREBO_ROOT=$DEST"
    echo "commit=$NOREBO_SHA"
    exit 0
  fi
  echo "error: $DEST is ${got:-empty}, pin is $NOREBO_SHA" >&2
  echo "move that tree aside and re-run tools/setup_norebo.sh" >&2
  exit 1
fi

if [ -e "$DEST" ]; then
  if [ "$DEST" = "$MACHINE" ]; then
    echo "error: $DEST exists but is not a built pin match" >&2
    echo "move that tree aside and re-run tools/setup_norebo.sh" >&2
    exit 1
  fi
  aside="${DEST}.old.$$"
  echo "=== Moving unusable $DEST to $aside ==="
  mv "$DEST" "$aside"
fi

STAGE="${DEST}.new"
if [ -e "$STAGE" ]; then
  echo "error: staging path $STAGE already exists" >&2
  echo "move it aside and re-run tools/setup_norebo.sh" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
echo "=== Cloning $NOREBO_URL at $NOREBO_SHA into $STAGE ==="
git clone "$NOREBO_URL" "$STAGE"
git -C "$STAGE" checkout --detach "$NOREBO_SHA"

got="$(git -C "$STAGE" rev-parse HEAD)"
if [ "$got" != "$NOREBO_SHA" ]; then
  echo "error: expected $NOREBO_SHA, got ${got:-empty}" >&2
  exit 1
fi

echo "=== Building Norebo with ./build.sh ==="
(
  cd "$STAGE"
  ./build.sh
)

if ! norebo_is_built "$STAGE"; then
  echo "error: build.sh finished but $STAGE/build2/ORP.rsc is missing" >&2
  exit 1
fi

printf '%s\n' "$NOREBO_SHA" > "$STAGE/.blinky-pin"
mv "$STAGE" "$DEST"

echo "=== Norebo ready ==="
echo "NOREBO_ROOT=$DEST"
echo "commit=$NOREBO_SHA"
echo "Use: tools/process_mod_files.sh   or   tools/verify_raw_oberon_code.py"
