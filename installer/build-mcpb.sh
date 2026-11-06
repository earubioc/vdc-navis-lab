#!/usr/bin/env bash
# Builds the Claude Desktop extension (.mcpb) of the server.
#   installer/build-mcpb.sh [out dir]
# The bundle holds only source: Claude Desktop installs the dependencies with uv when the extension is enabled.
# A .mcpb is a zip file; this script writes it with python's zipfile so it does not need node.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; out="${1:-$root/dist}"
mkdir -p "$out"
python3 - "$root" "$out" <<'PY'
import json, sys, zipfile
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
manifest = json.loads((root / "installer/mcpb/manifest.json").read_text(encoding="utf-8"))
version = manifest["version"]
pyver = next(l.split('"')[1] for l in (root / "pyproject.toml").read_text().splitlines() if l.startswith("version ="))
if pyver != version:
    sys.exit(f"FALLA: manifest.json dice {version} y pyproject.toml dice {pyver}")
files = {"manifest.json": root / "installer/mcpb/manifest.json", "run_server.py": root / "installer/mcpb/run_server.py"}
for name in ("pyproject.toml", "LICENSE", "NOTICE", "README.md"):
    files[name] = root / name
for p in sorted((root / "src").rglob("*")):
    if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"):
        files[p.relative_to(root).as_posix()] = p
target = out / f"vdc-navis-lab-{version}.mcpb"
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
    for arc, src in files.items():
        z.write(src, arc)
print(f"OK  {target}  ({target.stat().st_size // 1024} KB, {len(files)} archivos)")
PY
