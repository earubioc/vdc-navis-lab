"""Scale tooling: the infrastructure-sized generator, `bench`, and its live mode against the simulator."""

from vdc_navis_lab import bench, cli
from vdc_navis_lab.bridge.simulator import Simulator
from vdc_navis_lab.sample.generator import build_infra
from vdc_navis_lab.service import App


def test_infra_generator_is_deterministic_and_has_the_requested_volume():
    a, b = build_infra(12, 50, seed=3), build_infra(12, 50, seed=3)
    assert len(a.tests) == 12 and len(a.clashes) == 600
    assert [(c.id, c.status, round(c.distance, 6)) for c in a.clashes] == [(c.id, c.status, round(c.distance, 6)) for c in b.clashes]
    assert {"hard", "clearance"} <= {t.kind for t in a.tests} or len(a.tests) < 10
    assert {c.status for c in a.clashes} >= {"new", "approved"}


def test_infra_generator_reaches_hundreds_of_tests_with_thousands_each_in_the_header():
    cs = build_infra(210, 2, seed=1)   # many tests; few results so the test stays fast
    assert len(cs.tests) == 210 and all(t.count == 2 for t in cs.tests)


def test_bench_cli_prints_figures_only(capsys):
    assert cli.main(["bench", "--tests", "10", "--per-test", "40", "--per-place", "5"]) == 0
    out = capsys.readouterr().out
    assert "400 results" in out and "peak memory" in out and "INFRA" not in out


def test_bench_live_against_the_simulator(monkeypatch, tmp_path, capsys):
    sim = Simulator(job_delay=0.05)
    monkeypatch.setenv("VDC_NAVIS_LAB_HOME", str(tmp_path))
    monkeypatch.setenv("VDC_NAVIS_LAB_ENDPOINT", sim.start())
    try:
        out = bench.run_live(App(), wait_s=60)
    finally:
        sim.stop()
    assert out["finished"] and out["raw"] > 0 and out["pings"]["failed"] == 0


def test_bench_paged_runs_the_whole_path_in_a_separate_simulator(capsys):
    out = bench.run_paged(12, 200, seed=4, per_place=8, wait_s=120)
    assert out["finished"] and out["raw"] == 2400 and out["partial"] is None  # complete=False here only because 12 tests do not cover the expected pairs
    assert out["extraction"]["pages"] >= 12 and out["extraction"]["closed_only_counted"] > 0
    assert out["pings"]["failed"] == 0
    assert "INFRA" not in capsys.readouterr().out


def test_bench_paged_reports_a_partial_extraction(monkeypatch, capsys):
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_CLASHES", "400")
    out = bench.run_paged(6, 300, seed=4, per_place=8, wait_s=120)
    assert out["finished"] and out["complete"] is False and out["capped"] is True
    assert [r["code"] for r in out["partial"]["reasons"]] == ["cap"]
    assert "PARTIAL (cap)" in capsys.readouterr().out
