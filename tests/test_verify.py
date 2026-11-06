"""`vdc-navis-lab-cli verify`: passes against the simulator, fails cleanly without Navisworks, never prints names."""

from vdc_navis_lab import cli


def test_verify_against_the_simulator_passes_and_prints_no_names(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("VDC_NAVIS_LAB_ENDPOINT", raising=False)
    assert cli.main(["verify", "--simulate", "--writes"]) == 0
    out = capsys.readouterr().out
    assert "RESULT: ALL PASS" in out and "write plan" in out
    for word in ("tower", ".nwd", ".rvt"):
        assert word not in out.lower()


def test_verify_without_a_navisworks_fails_on_the_first_step_and_says_so(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_HOME", str(tmp_path))
    monkeypatch.setenv("VDC_NAVIS_LAB_ENDPOINT", "")
    monkeypatch.setattr("vdc_navis_lab.bridge.transport.discover", lambda *a, **k: [])
    assert cli.main(["verify"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  status" in out and "FAILED" in out
