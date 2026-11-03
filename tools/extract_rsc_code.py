#!/usr/bin/env python3
"""Dump the RAW code section of an Oberon .rsc file (no Python fixups)."""
import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rsc_parser import parse_rsc  # noqa: E402


def extract_raw_words(rsc_path):
    """Return a list of '0xXXXXXXXX' words from the code section, unfixed."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        module = parse_rsc(str(rsc_path), output_format="code_only", perform_fixup=False)
    return [f"0x{inst:08x}" for inst in module["code"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rsc", type=Path, help="path to a .rsc object file")
    args = parser.parse_args()
    if not args.rsc.is_file():
        print(f"error: {args.rsc} not found", file=sys.stderr)
        sys.exit(1)
    for word in extract_raw_words(args.rsc):
        print(word)


if __name__ == "__main__":
    main()
