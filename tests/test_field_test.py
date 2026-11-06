"""Field-test kit: the report holds aggregate figures only. Verified with the sanitizer, with example names planted in the
model, in the tests and in error text, and with tools/check_names.py over a git repository that contains the report."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from vdc_navis_lab import cli, field_test, verify
from vdc_navis_lab.bridge.simulator import Simulator
from vdc_navis_lab.sanitize import MASK, Sanitizer, numbers_only
from vdc_navis_lab.service import App

ROOT = Path(__file__).resolve().parents[1]
# Example names, not real ones: what a confidential model would carry. All longer than 10 characters, as check_names requires.
NAMES = ["Hospital Santa Aurora Torre B", "Cruce Viga Maestra Eje 7", "Edificio Los Alamos Fase 2", "Maria Fernanda Gutierrez"]


@pytest.fixture
def hostile(tmp_path, monkeypatch):
    """A simulator whose document and tests carry names that must never reach the report."""
    monkeypatch.setenv("VDC_NAVIS_LAB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("VDC_NAVIS_LAB_NO_PLUGINS", raising=False)
    sim = Simulator(job_delay=0.01)
    sim.title = NAMES[0] + ".nwf"
    for i, t in enumerate(sim.clashset.tests[:2]):
        old = t.name
        t.name = NAMES[1 + i]
        for c in sim.clashset.clashes:
            if c.test == old:
                c.test = t.name
    sim._by_test = {}
    for c in sim.clashset.clashes:
        sim._by_test.setdefault(c.test, []).append(c)
    monkeypatch.setenv("VDC_NAVIS_LAB_ENDPOINT", sim.start())
    yield sim
    sim.stop()


# ------------------------------------------------------------------ identifiers
def test_identifiers_are_generic_and_names_are_refused():
    assert field_test.check_id("e1", "equipo") == "E1" and field_test.check_id("M12", "modelo") == "M12"
    for bad in ("Hospital", "M123", "1M", "", "M-1", NAMES[0]):
        with pytest.raises(ValueError):
            field_test.check_id(bad, "modelo")


# ------------------------------------------------------------------ the sanitizer on its own
def test_sanitizer_masks_paths_files_emails_and_known_names():
    s = Sanitizer([NAMES[0], "Tower_A level-3"])
    text = (r"failed at C:\Users\maria\Proyectos\Obra Norte\modelo final.nwf and \\servidor\obras\x.nwd, /home/maria/p/m.rvt, "
            "~/docs/a.ifc; mail maria@empresa.co; HOSPITAL santa-aurora torre_b; tower a LEVEL 3; model A.nwd")
    out = s.clean(text)
    for frag in ("Users", "Proyectos", "servidor", "/home", "maria", "empresa", "aurora", ".nwf", ".nwd", ".rvt", ".ifc", "Tower", "LEVEL"):
        assert frag.lower() not in out.lower(), (frag, out)
    assert MASK in out and s.redactions >= 8 and s.leaks(out) == 0


def test_sanitizer_keeps_ordinary_figures_and_words():
    s = Sanitizer(["test", "user", "vdc-navis-lab", "ab"])  # harmless or too short to mask
    text = "9 tests, 54 results -> 35 issues (critical 1, high 16); filtered 15, complete=False; vdc-navis-lab 1.1.0; 3.2 s; 60/40"
    assert s.clean(text) == text and s.redactions == 0


def test_sanitizer_walks_structures_and_keys():
    s = Sanitizer([NAMES[1]])
    out = s.clean_obj({"a": [NAMES[1], {NAMES[1].upper(): 3}], "n": 7, "b": True})
    assert NAMES[1].lower() not in json.dumps(out).lower() and out["n"] == 7 and out["b"] is True


def test_numbers_only_drops_free_text():
    d = {"pages": 8, "name": NAMES[0], "code": "memory", "ok": True, "nested": {"x": 1, "y": "Some Name"}, "Bad Key": 3}
    assert numbers_only(d) == {"pages": 8, "code": "memory", "ok": True, "nested": {"x": 1}}


# ------------------------------------------------------------------ the whole run
def _run(tmp_path, writes=True, **kw):
    app = App()
    from vdc_navis_lab.plugins import load_plugins
    load_plugins(app)
    return field_test.run(app, equipo="E1", modelo="M1", writes=writes, out_dir=tmp_path / "out", say=lambda s: None, **kw)


def test_report_has_figures_and_no_names_even_when_everything_is_named(hostile, tmp_path):
    report, paths = _run(tmp_path)
    blob = "\n".join(p.read_text(encoding="utf-8") for p in paths)
    low = blob.lower()
    for n in NAMES + ["Hospital", "Santa Aurora", "Viga Maestra", ".nwf"]:
        assert n.lower() not in low, n
    assert report["verdict"] in ("PASS", "INCOMPLETE") and report["equipo"] == "E1" and report["modelo"] == "M1"
    assert report["redactions"] == 0, "a clean run must not need the scrubber: if this fails, a word of our own text is missing from the vocabulary"
    v, b, a = report["verify"], report["bench"], report["analyze"]
    assert v["figures"]["tests"] == 9 and v["figures"]["results"] == 54 and v["checks"][0]["name"] == "status"
    assert b["state"] == "done" and b["results"] == 54 and a["state"] == "done" and sum(a["bands"].values()) == a["issues"]
    assert report["environment"]["server"] and report["navisworks"]["addin_version"] == "simulator"
    assert "PASS" in paths[1].read_text(encoding="utf-8") and json.loads(paths[0].read_text(encoding="utf-8"))["report_version"] == 1


@pytest.mark.pro
def test_licensed_run_exercises_the_write_plan_and_the_exports_with_no_masking(hostile, tmp_path):
    """The Pro paths have their own detail text (counts of what was verified): its words must be in the vocabulary."""
    from conftest import enable_pro
    app = enable_pro(App())
    report, paths = field_test.run(app, equipo="E1", modelo="M1", writes=True, out_dir=tmp_path / "out", say=lambda s: None)
    checks = {c["name"]: c for c in report["verify"]["checks"]}
    assert checks["write plan (Pro)"]["status"] == "PASS" and checks["exports (Pro)"]["status"] == "PASS"
    assert "groups" in checks["write plan (Pro)"]["detail"] and report["redactions"] == 0, checks["write plan (Pro)"]["detail"]
    assert report["verify"]["writes"] == "ejecutadas sobre la copia" and report["verdict"] == "PASS"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in paths).lower()
    assert "hospital" not in blob and "santa aurora" not in blob


def test_names_planted_in_error_text_and_details_are_masked(hostile, tmp_path, monkeypatch):
    real = verify.run

    def noisy(app, writes=False, wait_s=900.0, say=print):
        rep = real(app, writes=writes, wait_s=wait_s, say=say)
        rep.checks.append(verify.Check("planted", False, 1.0, rf"cannot open C:\Users\maria\{NAMES[0]}.nwf: {NAMES[3]} <maria@empresa.co>"))
        say(f"FAIL  planted   {NAMES[1]} in /home/maria/{NAMES[2]}.nwd")
        return rep

    monkeypatch.setattr(verify, "run", noisy)
    lines: list[str] = []
    app = App()
    report, paths = field_test.run(app, equipo="E1", modelo="M2", writes=False, out_dir=tmp_path / "out", say=lines.append)
    blob = "\n".join(p.read_text(encoding="utf-8") for p in paths) + "\n".join(lines)
    for frag in NAMES + ["maria", "Users", "empresa", ".nwf", ".nwd", "/home"]:
        assert frag.lower() not in blob.lower(), frag
    assert report["verdict"] == "FAIL" and report["redactions"] >= 3
    planted = report["verify"]["checks"][-1]
    assert planted["status"] == "FAIL" and planted["detail"] == "error" and planted["name"] == MASK  # a word our code never uses is masked


def test_no_navisworks_gives_a_fail_report_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VDC_NAVIS_LAB_ENDPOINT", "")
    monkeypatch.setattr("vdc_navis_lab.bridge.transport.discover", lambda *a, **k: [])
    report, paths = field_test.run(App(), equipo="E1", modelo="M1", writes=False, out_dir=tmp_path / "out", say=lambda s: None)
    assert report["verdict"] == "FAIL" and report["verify"]["checks"][0]["status"] == "FAIL"
    assert paths[1].read_text(encoding="utf-8").startswith("## Prueba de campo E1 / M1: FAIL")


def test_installed_navisworks_reports_years_and_version_only(tmp_path):
    base = tmp_path / "Autodesk"
    (base / "Navisworks Manage 2025" / "Plugins" / "VdcNavisLab").mkdir(parents=True)
    (base / "Navisworks Manage 2025" / "Plugins" / "VdcNavisLab" / "VdcNavisLab.dll").write_bytes(b"x")
    (base / "Navisworks Manage 2026").mkdir()
    (base / "Navisworks Simulate 2026").mkdir()
    got = field_test.installed_navisworks(base)
    assert set(got) == {"2025", "2026"} and got["2025"]["addin_installed"] and not got["2026"]["addin_installed"]
    assert str(tmp_path) not in json.dumps(got)


# ------------------------------------------------------------------ the command line
def test_cli_requires_confirmation_for_writes_and_never_asks_when_not_a_terminal(hostile, tmp_path, capsys, monkeypatch):
    """Without --confirmo-copia and without a keyboard, the write test does not run: the default is the safe one."""
    monkeypatch.setattr(sys, "stdin", open("/dev/null") if sys.platform != "win32" else sys.stdin)
    code = cli.main(["field-test", "--equipo", "E1", "--modelo", "M1", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert code == 0 and "no ejecutadas" in out and "write plan" not in out
    assert "Hospital" not in out and "copiar desde aquí" in out


def test_cli_asks_for_the_word_and_only_that_word_enables_writes(hostile, tmp_path, capsys, monkeypatch):
    class Tty:
        def isatty(self): return True
    monkeypatch.setattr(sys, "stdin", Tty())
    for answer, wrote in (("si", False), ("", False), ("copia", True)):
        monkeypatch.setattr("builtins.input", lambda prompt, a=answer: a)
        monkeypatch.setenv("VDC_NAVIS_LAB_READ_ONLY", "1")
        cli.main(["field-test", "--out", str(tmp_path / f"o{answer or 'x'}")])
        out = capsys.readouterr().out
        assert ("write plan" in out) == wrote or ("Pro" in out and wrote), (answer, out[:300])
        assert "Hospital" not in out


def test_cli_refuses_a_name_as_identifier(capsys):
    assert cli.main(["field-test", "--modelo", "Hospital Santa Aurora"]) == 2
    assert "generic identifier" in capsys.readouterr().err


def test_cli_read_only_flag_skips_writes_even_with_confirmation(hostile, tmp_path, capsys):
    cli.main(["field-test", "--confirmo-copia", "--sin-escrituras", "--out", str(tmp_path / "out")])
    assert "write plan" not in capsys.readouterr().out


# ------------------------------------------------------------------ tools/check_names.py over a repository holding the report
def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


def test_check_names_finds_nothing_in_the_report_and_does_find_a_planted_name(hostile, tmp_path):
    report, paths = _run(tmp_path)
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps(NAMES + ["Hospital Santa Aurora", "Viga Maestra Eje"]), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for p in paths:
        (repo / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "field-test report")
    ok = subprocess.run([sys.executable, str(ROOT / "tools/check_names.py"), str(terms)], cwd=repo, capture_output=True, text=True)
    assert ok.returncode == 0 and "CLEAN" in ok.stdout, ok.stdout
    # control: the same checker does catch an unsanitized report, so a CLEAN above means something
    (repo / "raw.md").write_text(f"El modelo {NAMES[0]} tiene la prueba {NAMES[1]}.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "raw")
    bad = subprocess.run([sys.executable, str(ROOT / "tools/check_names.py"), str(terms)], cwd=repo, capture_output=True, text=True)
    assert bad.returncode == 1 and "MATCH" in bad.stdout and NAMES[0] not in bad.stdout  # it prints indexes, never the names
