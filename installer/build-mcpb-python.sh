#!/usr/bin/env bash
# Builds the offline Claude Desktop extension (.mcpb, server type "python"): every dependency is inside the bundle.
#   installer/build-mcpb-python.sh [--target windows|linux] [--pythons 3.11,3.12,3.13] [out dir]
# Needs network once, at build time (pip downloads wheels for the target platform; nothing is compiled).
# The compiled wheels (pydantic-core, cffi, rpds-py) have one file per Python version with different names, so the wheels of
# several versions can share one lib folder: the bundle runs on whichever of them the user has installed.
# The Windows bundle is the deliverable; the Linux bundle exists so the same layout can be started and tested here.
set -euo pipefail
target=windows; pythons="3.11,3.12,3.13"; out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target) target="$2"; shift 2;;
    --pythons) pythons="$2"; shift 2;;
    *) out="$1"; shift;;
  esac
done
root="$(cd "$(dirname "$0")/.." && pwd)"; out="${out:-$root/dist}"; mkdir -p "$out"
python3 - "$root" "$out" "$target" "$pythons" <<'PY'
import json, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

root, out, target, pythons = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4].split(",")
manifest = json.loads((root / "installer/mcpb-python/manifest.json").read_text(encoding="utf-8"))
version = manifest["version"]
pyver = next(l.split('"')[1] for l in (root / "pyproject.toml").read_text().splitlines() if l.startswith("version ="))
if pyver != version:
    sys.exit(f"FALLA: manifest.json dice {version} y pyproject.toml dice {pyver}")
plat = {"windows": ["win_amd64"],
        "linux": ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"]}[target]
if target == "linux":
    manifest["compatibility"]["platforms"] = ["linux"]
req = next(l for l in (root / "pyproject.toml").read_text().splitlines() if '"mcp>=' in l).split('"')[1]
work = Path(tempfile.mkdtemp(prefix="vdc-mcpb-py-"))
lib = work / "bundle/server/lib"
lib.mkdir(parents=True)
for v in pythons:
    dest = work / f"wheels-{v}"
    cmd = [sys.executable, "-m", "pip", "download", "-q", "--only-binary=:all:", "--implementation", "cp",
           "--python-version", v, "--abi", "cp" + v.replace(".", ""), "--dest", str(dest), req]
    for p in plat:
        cmd += ["--platform", p]
    subprocess.run(cmd, check=True)
    for whl in sorted(dest.glob("*.whl")):
        with zipfile.ZipFile(whl) as z:
            z.extractall(lib)
src = root / "src/vdc_navis_lab"
shutil.copytree(src, lib / "vdc_navis_lab", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copy(root / "installer/mcpb-python/main.py", work / "bundle/server/main.py")
(work / "bundle/manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
for name in ("LICENSE", "NOTICE", "README.md"):
    shutil.copy(root / name, work / "bundle" / name)
target_file = out / f"vdc-navis-lab-{version}-offline-{target}.mcpb"
n = 0
with zipfile.ZipFile(target_file, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted((work / "bundle").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            z.write(p, p.relative_to(work / "bundle").as_posix())
            n += 1
print(f"OK  {target_file}  ({target_file.stat().st_size // 1024} KB, {n} archivos, Python {', '.join(pythons)}, {target})")
shutil.rmtree(work)
PY
