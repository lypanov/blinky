# Shared Norebo paths. Source from other tools scripts.
# After PR #7 (monorepo layout) this file stays in tools/; tests move to core/tests/.

_norebo_env_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

norebo_read_pin() {
  local pin="${_norebo_env_root}/tools/norebo.pin"
  NOREBO_URL="$(sed -n 's/^url=//p' "$pin")"
  NOREBO_SHA="$(sed -n 's/^sha=//p' "$pin")"
}

norebo_root() {
  if [ -n "${NOREBO_ROOT:-}" ]; then
    printf '%s\n' "$NOREBO_ROOT"
  else
    printf '%s\n' "${_norebo_env_root}/tools/project-norebo"
  fi
}

norebo_is_built() {
  local root="$1"
  [ -x "$root/norebo" ] && [ -d "$root/build2" ] && [ -f "$root/build2/ORP.rsc" ]
}

norebo_export() {
  local root
  root="$(norebo_root)"
  if ! norebo_is_built "$root"; then
    echo "error: Norebo is not built at $root" >&2
    echo "run: tools/setup_norebo.sh" >&2
    return 1
  fi
  # Prefer the rebuilt compiler (build.sh stage 2/3) over Bootstrap.
  export NOREBO_ROOT="$root"
  export NOREBO_PATH="$root/Norebo:$root/Oberon:$root/build2"
  export NOREBO_BIN="$root/norebo"
}
