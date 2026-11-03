#!/usr/bin/env bash
# Compile tests/*.Mod with the pinned Norebo ORP, keep RAW .rsc/code, then
# (unchanged) run the existing Python fixup path into .code/.asm.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=norebo_env.sh
source "$ROOT/tools/norebo_env.sh"

if ! norebo_export; then
  echo "Attempting tools/setup_norebo.sh ..."
  "$ROOT/tools/setup_norebo.sh"
  norebo_export
fi

TESTS_DIR="$ROOT/tests"
RAW_DIR="$TESTS_DIR/raw"
mkdir -p "$RAW_DIR"

cd "$TESTS_DIR" || exit 1

shopt -s nullglob
mod_files=(*.Mod)
if [ ${#mod_files[@]} -eq 0 ]; then
  echo "No .Mod files found in tests directory"
  exit 1
fi

for mod_file in "${mod_files[@]}"; do
  base_name="${mod_file%.Mod}"
  module_name="$(grep -m 1 "MODULE" "$mod_file" | sed -E 's/MODULE[[:space:]]+([^;]+);.*/\1/')"

  echo "Processing $mod_file (MODULE $module_name)..."

  rm -f "$module_name.rsc" "$module_name.smb"

  "$NOREBO_BIN" ORP.Compile "$mod_file"

  if [ ! -f "$module_name.rsc" ]; then
    echo "Error: Compilation failed for $mod_file"
    exit 1
  fi

  # RAW object file + code section, before any Python fixup.
  cp "$module_name.rsc" "$RAW_DIR/${base_name}.rsc"
  python3 "$ROOT/tools/extract_rsc_code.py" "$module_name.rsc" > "$RAW_DIR/${base_name}.code"
  echo "Raw code: $RAW_DIR/${base_name}.code  (also $RAW_DIR/${base_name}.rsc)"

  # Existing fixup / disassembly path (used by the CPU tests; do not skip).
  python3 "$ROOT/tools/rsc_parser.py" "$module_name.rsc" fixup > input.txt
  python3 "$ROOT/tools/instruction_parser.py" > "$base_name.asm"
  mv input.txt "$base_name.code"
  sed -i '/^BEGIN$/d; /^END$/d' "$base_name.code"

  echo "Fixup output: $base_name.asm, $base_name.code"
  echo ""
done

python3 "$ROOT/tools/module_loader.py"
python3 "$ROOT/tools/image_dump.py" final_system.code

echo "All .Mod files processed successfully"
echo "Raw (unfixed) artifacts are in $RAW_DIR — gitignored, not the CPU-test images."
