#!/usr/bin/env python3
"""
Recompile Blink2 / Blink3 / AMemoryMappedToggle with pinned Norebo and
compare the RAW (unfixed) code section to historical dumps.

Does not run Python fixups, does not overwrite tests/*.code, and does not
touch the CPU or linker.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"
FIXTURES = TESTS / "fixtures" / "unfixed"

# source .Mod (current tree) -> historical unfixed code dump
CASES = [
    {
        "name": "AMemoryMappedToggle",
        "sources": ["AMemoryMappedToggle.Mod"],
        "rsc": "AMemoryMappedToggle.rsc",
        "fixture": "AMemoryMappedToggle.code",
        "origin": "e5743c8:tests/AMemoryMappedToggle.code",
    },
    {
        "name": "LightToggle (Blink3test.Mod)",
        "sources": ["AMemoryMappedToggle.Mod", "Blink3test.Mod"],
        "rsc": "LightToggle.rsc",
        "fixture": "Blink3test.code",
        "origin": "Blink3test.Mod maxIterations := 262144 (MHI 0x60000004); imported BL 0xf7102011",
    },
    {
        "name": "Blink2 (Blink2test.Mod)",
        "sources": ["Blink2test.Mod"],
        "rsc": "LightToggle.rsc",
        "fixture": "Blink2test.code",
        "origin": "073dda5:tests/Blink2test.code (last unfixed dump of current Blink2test.Mod)",
    },
]


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)


def load_env():
    script = f"""
set -e
source "{TOOLS / 'norebo_env.sh'}"
if ! norebo_export; then
  "{TOOLS / 'setup_norebo.sh'}"
  norebo_export
fi
printf 'NOREBO_BIN=%s\\n' "$NOREBO_BIN"
printf 'NOREBO_PATH=%s\\n' "$NOREBO_PATH"
"""
    out = subprocess.check_output(["bash", "-c", script], text=True)
    bin_path = path = None
    for ln in out.splitlines():
        if ln.startswith("NOREBO_BIN="):
            bin_path = ln.split("=", 1)[1]
        elif ln.startswith("NOREBO_PATH="):
            path = ln.split("=", 1)[1]
        elif bin_path is None:
            # last two plain lines are a fallback if prefixes are missing
            pass
    if not bin_path or not path:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if len(lines) >= 2:
            bin_path, path = lines[-2], lines[-1]
    if not bin_path or not path:
        raise SystemExit(f"failed to resolve Norebo env, got: {out!r}")
    return bin_path, path


def read_words(path: Path):
    words = []
    for raw in path.read_text().splitlines():
        line = raw.strip().lower()
        if not line or line in ("begin", "end"):
            continue
        if not line.startswith("0x"):
            raise SystemExit(f"{path}: unexpected line {raw!r}")
        words.append(line)
    return words


def extract_raw(rsc: Path):
    out = subprocess.check_output(
        [sys.executable, str(TOOLS / "extract_rsc_code.py"), str(rsc)],
        text=True,
    )
    return [ln.strip().lower() for ln in out.splitlines() if ln.strip()]


def word_diff(expected, got, label, origin):
    lines = [
        f"--- expected ({origin})",
        f"+++ got     (fresh Norebo ORP raw code for {label})",
    ]
    n = max(len(expected), len(got))
    mismatches = 0
    for i in range(n):
        e = expected[i] if i < len(expected) else "<missing>"
        g = got[i] if i < len(got) else "<missing>"
        if e != g:
            mismatches += 1
            lines.append(f"  word[{i}] expected {e}  got {g}")
    if len(expected) != len(got):
        lines.append(
            f"  length expected {len(expected)} words, got {len(got)} words"
        )
        mismatches += 1
    return mismatches, lines


def compile_case(case, norebo_bin, norebo_path, work: Path):
    case_dir = work / case["name"].replace(" ", "_").replace("(", "").replace(")", "")
    case_dir.mkdir()
    for src in case["sources"]:
        shutil.copy(TESTS / src, case_dir / src)
        run(
            [norebo_bin, "ORP.Compile", src],
            cwd=case_dir,
            env={**os.environ, "NOREBO_PATH": norebo_path},
        )
    rsc = case_dir / case["rsc"]
    if not rsc.is_file():
        raise SystemExit(f"{case['name']}: expected {rsc.name} after compile")
    return rsc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="leave the temp compile directory in place",
    )
    args = parser.parse_args()

    norebo_bin, norebo_path = load_env()
    print(f"NOREBO_BIN={norebo_bin}")
    print(f"NOREBO_PATH={norebo_path}")

    work = Path(tempfile.mkdtemp(prefix="blinky-norebo-raw-"))
    failed = []
    try:
        for case in CASES:
            print(f"\n=== {case['name']} ===")
            print(f"origin: {case['origin']}")
            rsc = compile_case(case, norebo_bin, norebo_path, work)
            got = extract_raw(rsc)
            fixture = FIXTURES / case["fixture"]
            expected = read_words(fixture)
            mismatches, diff_lines = word_diff(
                expected, got, case["name"], case["origin"]
            )
            if mismatches == 0:
                print(f"MATCH  {len(got)} words  {rsc.name}  vs  {fixture.name}")
                if case["name"].startswith("LightToggle"):
                    if "0xf7102011" not in got:
                        print("error: imported BL 0xf7102011 missing from Blink3 raw code")
                        failed.append(case["name"])
                    else:
                        print("imported BL 0xf7102011 present at call site")
            else:
                print("MISMATCH")
                print("\n".join(diff_lines))
                failed.append(case["name"])
    finally:
        if args.keep_work:
            print(f"\nwork dir kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    print()
    if failed:
        print("FAIL: " + ", ".join(failed))
        sys.exit(1)
    print("PASS: raw code matches historical unfixed dumps bit for bit")
    sys.exit(0)


if __name__ == "__main__":
    main()
