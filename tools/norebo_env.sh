# Shared Norebo paths. Source from other tools scripts.
# After PR #7 (monorepo layout) this file stays in tools/; tests move to core/tests/.

_norebo_env_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# On this machine the built pin lives here, outside every worktree.
# GitHub CI has no /home/lypanov/fpga, so setup_norebo.sh falls back
# to tools/project-norebo (gitignored, cached in test.yml).
norebo_machine_root() {
  printf '%s\n' "/home/lypanov/fpga/norebo-compiled"
}

norebo_worktree_root() {
  printf '%s\n' "${_norebo_env_root}/tools/project-norebo"
}

norebo_read_pin() {
  local pin="${_norebo_env_root}/tools/norebo.pin"
  NOREBO_URL="$(sed -n 's/^url=//p' "$pin")"
  NOREBO_SHA="$(sed -n 's/^sha=//p' "$pin")"
}

norebo_is_built() {
  local root="$1"
  [ -x "$root/norebo" ] && [ -d "$root/build2" ] && [ -f "$root/build2/ORP.rsc" ]
}

norebo_got_sha() {
  local dest="$1"
  if [ -d "$dest/.git" ]; then
    git -C "$dest" rev-parse HEAD 2>/dev/null || true
  elif [ -f "$dest/.blinky-pin" ]; then
    cat "$dest/.blinky-pin"
  fi
}

# Where setup_norebo.sh creates the tree. Ignores a leftover NOREBO_ROOT
# from norebo_export in the same shell. Override with NOREBO_INSTALL_ROOT.
norebo_install_root() {
  local machine parent
  if [ -n "${NOREBO_INSTALL_ROOT:-}" ]; then
    printf '%s\n' "$NOREBO_INSTALL_ROOT"
    return
  fi
  machine="$(norebo_machine_root)"
  parent="$(dirname "$machine")"
  if [ -d "$parent" ] && [ -w "$parent" ]; then
    printf '%s\n' "$machine"
  else
    norebo_worktree_root
  fi
}

# Where compiles look. On this machine the built pin wins, even if the
# shell still has NOREBO_ROOT from an old worktree copy.
norebo_root() {
  local machine worktree
  machine="$(norebo_machine_root)"
  worktree="$(norebo_worktree_root)"
  if norebo_is_built "$machine"; then
    printf '%s\n' "$machine"
  elif [ -n "${NOREBO_ROOT:-}" ]; then
    printf '%s\n' "$NOREBO_ROOT"
  elif norebo_is_built "$worktree"; then
    printf '%s\n' "$worktree"
  else
    norebo_install_root
  fi
}

norebo_export() {
  local root got
  norebo_read_pin
  root="$(norebo_root)"
  if ! norebo_is_built "$root"; then
    echo "error: Norebo is not built at $root" >&2
    echo "run: tools/setup_norebo.sh" >&2
    return 1
  fi
  got="$(norebo_got_sha "$root")"
  if [ -n "${NOREBO_SHA:-}" ] && [ -n "$got" ] && [ "$got" != "$NOREBO_SHA" ]; then
    echo "error: $root is $got, pin is $NOREBO_SHA" >&2
    echo "move that tree aside and run tools/setup_norebo.sh" >&2
    return 1
  fi
  # Prefer the rebuilt compiler (build.sh stage 2/3) over Bootstrap.
  export NOREBO_ROOT="$root"
  export NOREBO_PATH="$root/Norebo:$root/Oberon:$root/build2"
  export NOREBO_BIN="$root/norebo"
}
