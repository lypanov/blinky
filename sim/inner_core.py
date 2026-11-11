#!/usr/bin/env python3
"""Compile the inner core and lift Modules.Check.

Norebo compiles oberon/src/Kernel.Mod, FileDir.Mod, Files.Mod, and
Modules.Mod in that order, in one directory, so the import keys match.
docs/OberonSources is not on that path. Check is not exported. Its
procedure is the only SUB SP, SP, 20 frame, and the character tests
are the immediates in that frame. The two GetSB links become
LDW SB, MT, mod.num*4. mod.num is 3, so the slot is MT[3].
"""
from __future__ import annotations

import hashlib
import os
import struct
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "oberon", "src")
CACHE = os.path.join(ROOT, "sim", "inner-core")
ORDER = ("Kernel", "FileDir", "Files", "Modules")
# MT[1] and MT[2] are the planted module table. Check's static base is MT[3].
MOD_NUM = 3
SUB_SP_20 = 0x4EE90014
ADD_SP_20 = 0x4EE80014
BR_R15 = 0xC700000F
MT = 12

_CACHE: dict | None = None


def _read_int(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(b"\0", offset)
    return data[offset:end].decode("ascii"), end + 1


def parse_rsc(path: str) -> dict:
    data = open(path, "rb").read()
    name, offset = _read_name(data, 0)
    key, offset = _read_int(data, offset)
    version = data[offset]
    offset += 1
    size, offset = _read_int(data, offset)
    imports = []
    while data[offset] != 0:
        imp, offset = _read_name(data, offset)
        imp_key, offset = _read_int(data, offset)
        imports.append((imp, imp_key))
    offset += 1
    td, offset = _read_int(data, offset)
    offset += td
    var, offset = _read_int(data, offset)
    strx, offset = _read_int(data, offset)
    offset += strx
    ncode, offset = _read_int(data, offset)
    code = list(struct.unpack_from("<" + "I" * ncode, data, offset))
    return {
        "name": name,
        "key": key,
        "version": version,
        "size": size,
        "bytes": len(data),
        "imports": imports,
        "td": td,
        "var": var,
        "code": code,
    }


def _fix_getsb(word: int) -> int:
    """Modules.Mod global D-fixup. The chain displacement is replaced."""
    return ((word // 0x1000000) * 0x10 + MT) * 0x100000 + MOD_NUM * 4


def extract_check(code: list[int]) -> list[int]:
    starts = [i for i, word in enumerate(code) if word == SUB_SP_20]
    if len(starts) != 1:
        raise SystemExit(f"expected one Check frame, found {len(starts)}")
    start = starts[0]
    try:
        end = code.index(ADD_SP_20, start)
    except ValueError as exc:
        raise SystemExit("Check does not release its frame") from exc
    if end + 1 >= len(code) or code[end + 1] != BR_R15:
        raise SystemExit("Check does not return through R15")
    body = code[start : end + 2]
    immediates = {word & 0xFFFF for word in body if (word >> 28) == 4}
    for ch in (0x41, 0x5A, 0x61, 0x7A, 0x30, 0x39, 0x2E):
        if ch not in immediates:
            raise SystemExit(f"Check is missing the compare with {ch:#x}")
    fixed = []
    links = 0
    for word in body:
        if (word >> 20) == 0x8D0:
            fixed.append(_fix_getsb(word))
            links += 1
        else:
            fixed.append(word)
    if links != 2:
        raise SystemExit(f"Check has {links} GetSB links, expected 2")
    if fixed[1] != 0xAFE00000:
        raise SystemExit("Check does not save the link")
    return fixed


def _import_key(parsed: dict, name: str) -> int:
    hits = [key for imp, key in parsed["imports"] if imp == name]
    if len(hits) != 1:
        raise SystemExit(f"{parsed['name']} imports {parsed['imports']}, wanted {name}")
    return hits[0]


def _check_keys(mods: dict[str, dict]) -> None:
    if mods["FileDir"]["imports"] != [("Kernel", mods["Kernel"]["key"])]:
        raise SystemExit(f"FileDir imports {mods['FileDir']['imports']}")
    files = mods["Files"]["imports"]
    expect = [("Kernel", mods["Kernel"]["key"]), ("FileDir", mods["FileDir"]["key"])]
    if files != expect:
        raise SystemExit(f"Files imports {files}, expected {expect}")
    if _import_key(mods["Modules"], "Files") != mods["Files"]["key"]:
        raise SystemExit("Modules.rsc Files key does not equal Files.rsc")
    if mods["Modules"]["name"] != "Modules":
        raise SystemExit("the object file is not Modules")


def _check_sources() -> None:
    sums = {}
    for line in open(os.path.join(ROOT, "oberon", "SHA256SUMS")):
        digest, name = line.split()
        sums[name] = digest
    for name in ORDER:
        rel = f"src/{name}.Mod"
        data = open(os.path.join(SRC, f"{name}.Mod"), "rb").read()
        got = hashlib.sha256(data).hexdigest()
        if sums.get(rel) != got:
            raise SystemExit(f"{rel} sha256 {got} is not the recorded source")


def _unchanged_symbol(name: str, key: int) -> str:
    root = os.environ.get("NOREBO_ROOT")
    if not root:
        root = os.path.join(ROOT, "tools", "project-norebo")
    hits = []
    for base in ("build2", "build3", "Oberon", "Norebo"):
        path = os.path.join(root, base, f"{name}.smb")
        if not os.path.isfile(path):
            continue
        got = struct.unpack_from("<I", open(path, "rb").read(), 4)[0]
        if got == key:
            hits.append(path)
    if not hits:
        raise SystemExit(f"no {name}.smb with key {key:08X} under {root}")
    return hits[0]


def compile_inner() -> dict:
    _check_sources()
    os.makedirs(CACHE, exist_ok=True)
    for name in ORDER:
        src = os.path.join(SRC, f"{name}.Mod")
        if not os.path.isfile(src):
            raise SystemExit(f"missing {src}")
        dst = os.path.join(CACHE, f"{name}.Mod")
        # The publisher's bytes, including CRLF. A text-mode copy would change the key.
        open(dst, "wb").write(open(src, "rb").read())
    script = f"""
set -euo pipefail
source "{ROOT}/tools/norebo_env.sh"
if ! norebo_export; then
  "{ROOT}/tools/setup_norebo.sh"
  norebo_export
fi
cd "{CACHE}"
for m in {" ".join(ORDER)}; do
  "$NOREBO_BIN" ORP.Compile "$m.Mod/s"
done
"""
    out = subprocess.check_output(["bash", "-c", script], stderr=subprocess.STDOUT)
    text = out.decode("latin1", errors="replace")
    if "compilation FAILED" in text or "not found" in text:
        raise SystemExit(text)
    mods = {name: parse_rsc(os.path.join(CACHE, f"{name}.rsc")) for name in ORDER}
    _check_keys(mods)
    # ORB.Export does not rewrite a symbol file whose key is unchanged.
    # Modules' exports match the pinned compiler, so Modules.smb stays on
    # NOREBO_PATH and never appears in this directory. Copy that file.
    for name in ORDER:
        smb = os.path.join(CACHE, f"{name}.smb")
        if os.path.isfile(smb):
            continue
        src = _unchanged_symbol(name, mods[name]["key"])
        open(smb, "wb").write(open(src, "rb").read())
    check = extract_check(mods["Modules"]["code"])
    return {"modules": mods, "check": check, "log": text}


def load_inner() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = compile_inner()
    return _CACHE


def main() -> int:
    got = load_inner()
    mods = got["modules"]
    print(got["log"], end="")
    for name in ORDER:
        mod = mods[name]
        print(
            f"[ok] {name}.rsc {mod['bytes']} bytes key {mod['key']:08X} "
            f"code {len(mod['code'])} var {mod['var']}"
        )
    print(f"[ok] Modules.Check {len(got['check'])} words, MT[{MOD_NUM}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
