"""The packaging scripts: the MCPB is built from the repo and agrees with pyproject; the MSI carries the DLL byte for byte."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    return next(l.split('"')[1] for l in (ROOT / "pyproject.toml").read_text().splitlines() if l.startswith("version ="))


def test_manifest_matches_the_package_and_the_tools():
    m = json.loads((ROOT / "installer/mcpb/manifest.json").read_text(encoding="utf-8"))
    assert m["version"] == _version()
    assert m["server"]["type"] == "uv"
    assert (ROOT / "installer/mcpb" / m["server"]["entry_point"]).is_file()
    # the switch the user sees maps to the variable the server reads
    assert m["server"]["mcp_config"]["env"]["VDC_NAVIS_LAB_READ_ONLY"] == "${user_config.read_only}"
    assert m["user_config"]["read_only"]["default"] is True


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_mcpb_bundle_contents(tmp_path):
    subprocess.run(["bash", str(ROOT / "installer/build-mcpb.sh"), str(tmp_path)], check=True, capture_output=True)
    bundle = tmp_path / f"vdc-navis-lab-{_version()}.mcpb"
    with zipfile.ZipFile(bundle) as z:
        names = set(z.namelist())
        assert z.testzip() is None
    for need in ("manifest.json", "run_server.py", "pyproject.toml", "LICENSE", "src/vdc_navis_lab/server.py",
                 "src/vdc_navis_lab/profiles/default.toml"):
        assert need in names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.startswith(("tests/", "examples/", "encuesta", "contexto/", "insumos/")) for n in names), "nothing private or heavy"


@pytest.mark.skipif(not (shutil.which("wixl") and shutil.which("msiextract")), reason="needs wixl and msitools")
def test_msi_installs_the_dll_where_navisworks_looks(tmp_path):
    dll = tmp_path / "VdcNavisLab.dll"
    dll.write_bytes(b"MZ" + bytes(range(256)) * 40)
    out = tmp_path / "out"
    subprocess.run(["bash", str(ROOT / "installer/build-msi.sh"), "2025", "1.0.1", str(dll), str(out)], check=True, capture_output=True)
    msi = out / "VdcNavisLab-2025-1.0.1.msi"
    assert msi.is_file()
    ex = tmp_path / "ex"
    subprocess.run(["msiextract", "-C", str(ex), str(msi)], check=True, capture_output=True)
    placed = ex / "Autodesk/Navisworks Manage 2025/Plugins/VdcNavisLab/VdcNavisLab.dll"
    assert placed.read_bytes() == dll.read_bytes()
    # another year never shares the upgrade code, so 2025 and 2026 can live side by side
    subprocess.run(["bash", str(ROOT / "installer/build-msi.sh"), "2026", "1.0.1", str(dll), str(out)], check=True, capture_output=True)
    codes = []
    for y in (2025, 2026):
        t = subprocess.run(["msiinfo", "export", str(out / f"VdcNavisLab-{y}-1.0.1.msi"), "Property"], capture_output=True, text=True).stdout
        codes.append(next(l for l in t.splitlines() if l.startswith("UpgradeCode")))
    assert codes[0] != codes[1]


def test_offline_manifest_matches_the_package_and_starts_from_its_own_lib():
    m = json.loads((ROOT / "installer/mcpb-python/manifest.json").read_text(encoding="utf-8"))
    assert m["version"] == _version() == json.loads((ROOT / "installer/mcpb/manifest.json").read_text(encoding="utf-8"))["version"]
    assert m["server"]["type"] == "python" and m["server"]["entry_point"] == "server/main.py"
    assert m["server"]["mcp_config"]["env"]["PYTHONPATH"] == "${__dirname}/server/lib"
    assert m["server"]["mcp_config"]["env"]["VDC_NAVIS_LAB_READ_ONLY"] == "${user_config.read_only}"
    assert m["user_config"]["read_only"]["default"] is True
    assert (ROOT / "installer/mcpb-python/main.py").is_file()


def test_offline_launcher_uses_only_its_lib(tmp_path):
    """main.py finds the package through server/lib next to it, with nothing else on the path."""
    import subprocess
    import sys
    lib = tmp_path / "server" / "lib"
    shutil.copytree(ROOT / "src" / "vdc_navis_lab", lib / "vdc_navis_lab", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "installer/mcpb-python/main.py", tmp_path / "server" / "main.py")
    code = ("import sys, runpy; sys.argv=['main.py']; sys.path[:] = [p for p in sys.path if 'vdc-navis-lab' not in p and p != '']\n"
            "import importlib.util as u\n"
            "sys.path.insert(0, %r)\n" % str(lib) +
            "print(u.find_spec('vdc_navis_lab').origin)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out.startswith(str(lib))
