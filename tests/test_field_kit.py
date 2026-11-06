"""The folder that is copied to another machine: layout, scripts, instructions, and the 2027 gate (no DLLs, no compile)."""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAMPO = ROOT / "installer" / "campo"
spec = importlib.util.spec_from_file_location("refs_framework", ROOT / "tools" / "refs_framework.py")
refs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refs)


def _dlls(folder: Path, framework: bytes = b".NETFramework,Version=v4.8"):
    folder.mkdir(parents=True)
    for n in refs.REQUIRED:
        (folder / n).write_bytes(b"MZ\x00\x00" + (framework if "Interop" not in n else b"") + b"\x00rest")


# ------------------------------------------------------------------ the 2027 gate
def test_missing_dlls_stop_the_build_and_say_what_is_needed(tmp_path, capsys):
    assert refs.main(["2027", "--refs", str(tmp_path)]) == 3
    out = capsys.readouterr().out
    assert "FALTAN 4 de 4" in out and "Autodesk.Navisworks.Api.dll" in out and "2027" in out


def test_net48_passes_and_another_framework_stops(tmp_path, capsys):
    _dlls(tmp_path / "2026")
    assert refs.main(["2026", "--refs", str(tmp_path)]) == 0
    _dlls(tmp_path / "2027", b".NETCoreApp,Version=v8.0")
    assert refs.main(["2027", "--refs", str(tmp_path)]) == 4
    assert "NO es net48" in capsys.readouterr().out


def test_the_repo_does_not_carry_autodesk_dlls():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    assert not [t for t in tracked if t.lower().endswith(".dll") or "addin/refs" in t]
    assert "addin/refs/" in (ROOT / ".gitignore").read_text()


# ------------------------------------------------------------------ scripts and instructions
@pytest.mark.parametrize("name", ["campo.ps1", "instalar-prueba.ps1", "desinstalar-prueba.ps1"])
def test_scripts_are_ascii_so_powershell_5_does_not_garble_them(name):
    text = (CAMPO / name).read_text(encoding="utf-8")
    assert all(ord(c) < 128 for c in text), name
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")")


def test_field_test_wrapper_runs_the_cli_command_with_the_license_and_generic_ids():
    text = (CAMPO / "campo.ps1").read_text(encoding="utf-8")
    for needle in ("field-test", "--equipo", "--modelo", "--confirmo-copia", "--sin-escrituras", "VDC_NAVIS_LAB_LICENSE_FILE", "server\\lib", "3\\.(11|12|13)"):
        assert needle in text, needle


def test_uninstaller_removes_every_trace_the_installer_leaves():
    inst, un = (CAMPO / "instalar-prueba.ps1").read_text(encoding="utf-8"), (CAMPO / "desinstalar-prueba.ps1").read_text(encoding="utf-8")
    assert "msiexec" in inst and "/x" in un and "license.token" in un and ".vdc_navis_lab" in un and "Uninstall" in un
    assert "Plugins\\VdcNavisLab" in inst and "Plugins\\VdcNavisLab" in un


def test_instructions_fit_one_sheet_in_spanish_without_long_dashes():
    html = (CAMPO / "INSTRUCCIONES.html").read_text(encoding="utf-8")
    assert "—" not in html and "@VERSION@" in html and "@YEARS@" in html
    for must in ("copia", "campo.ps1", "instalar-prueba.ps1", "desinstalar-prueba.ps1", "Desinstalación limpia", "COPIA"):
        assert must in html, must
    assert len(re.sub(r"<[^>]+>", " ", html).split()) < 700  # one A4 sheet at 9.6 pt


# ------------------------------------------------------------------ the builder
def _fake_inputs(tmp_path, version="1.1.0"):
    msis = tmp_path / "msis"
    msis.mkdir(exist_ok=True)
    for y in (2025, 2026, 2027):
        (msis / f"VdcNavisLab-{y}-{version}.msi").write_bytes(b"msi" + str(y).encode())
    mcpb = tmp_path / f"vdc-navis-lab-{version}-pro-offline-windows.mcpb"
    mcpb.write_bytes(b"zip")
    token = tmp_path / "t.token"
    token.write_text("VDCL1.x.y\n")
    return msis, mcpb, token


def _build(tmp_path, out):
    msis, mcpb, token = _fake_inputs(tmp_path)
    return subprocess.run(["bash", str(ROOT / "installer" / "build-field-kit.sh"), "--msi-dir", str(msis), "--mcpb", str(mcpb),
                           "--token", str(token), "--out", str(out)], capture_output=True, text=True)


def test_builder_lays_out_the_folder(tmp_path):
    out = tmp_path / "kit"
    r = _build(tmp_path, out)
    assert r.returncode == 0, r.stderr
    names = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert names == sorted(["INSTRUCCIONES.html", "SHA256SUMS.txt", "campo.ps1", "desinstalar-prueba.ps1", "instalar-prueba.ps1",
                            "licencia/license.token", "msi/VdcNavisLab-2025-1.1.0.msi", "msi/VdcNavisLab-2026-1.1.0.msi", "msi/VdcNavisLab-2027-1.1.0.msi",
                            "vdc-navis-lab-1.1.0-pro-offline-windows.mcpb"])
    assert (out / "resultados").is_dir()
    html = (out / "INSTRUCCIONES.html").read_text(encoding="utf-8")
    assert "1.1.0" in html and "2025, 2026 y 2027" in html and "@" not in html.replace("@page", "").replace("@media", "")
    assert "VdcNavisLab-2025-1.1.0.msi" in (out / "SHA256SUMS.txt").read_text()


def test_builder_refuses_a_folder_inside_a_repository_that_does_not_ignore_it(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    r = _build(tmp_path, repo / "kit")
    assert r.returncode == 1 and "licencia" in r.stderr
    (repo / ".gitignore").write_text("kit/\n")
    assert _build(tmp_path, repo / "kit").returncode == 0


def test_builder_refuses_a_missing_msi_version(tmp_path):
    msis, mcpb, token = _fake_inputs(tmp_path, "1.0.1")
    other = tmp_path / "vdc-navis-lab-1.1.0-pro-offline-windows.mcpb"
    other.write_bytes(b"zip")
    r = subprocess.run(["bash", str(ROOT / "installer" / "build-field-kit.sh"), "--msi-dir", str(msis), "--mcpb", str(other),
                        "--token", str(token), "--out", str(tmp_path / "k")], capture_output=True, text=True)
    assert r.returncode == 1 and "no hay MSI 1.1.0" in r.stderr
