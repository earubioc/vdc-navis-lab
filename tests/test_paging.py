"""Paged extraction (clash.page): same result as the single export, and honest when a budget runs out."""

from __future__ import annotations

import time

import pytest

from vdc_navis_lab import extract
from vdc_navis_lab.bridge import Bridge
from vdc_navis_lab.bridge.simulator import Simulator
from vdc_navis_lab.bridge.transport import Endpoint
from vdc_navis_lab.engine import analyze
from vdc_navis_lab.profile import Profile
from vdc_navis_lab.sample.generator import build_infra
from vdc_navis_lab.service import App, ToolFault


def _app(sim: Simulator) -> App:
    return App(bridge=Bridge(lambda: [Endpoint.parse(sim.endpoint)]))


def _run(app: App, **kw):
    """nw_analyze until it stops answering 'running'."""
    job = ""
    for _ in range(400):
        out = app.analyze("", kw.get("tests"), 5, 5, job, None)
        if out.get("state") != "running":
            return out
        job = out["job_id"]
        time.sleep(0.05)
    raise AssertionError("the extraction did not finish")


@pytest.fixture
def infra():
    return build_infra(tests=8, per_test=400, seed=5)


@pytest.fixture
def serve():
    started: list[Simulator] = []

    def make(cs, **kw) -> Simulator:
        s = Simulator(job_delay=0.01, clashset=cs, **kw)
        s.start()
        started.append(s)
        return s

    yield make
    for s in started:
        s.stop()


def test_paged_analysis_equals_the_direct_one(infra, serve):
    want = analyze(infra, Profile.default(), "es")
    out = _run(_app(serve(infra)))
    assert out["issues"] == len(want.issues)
    assert out["raw_count"] == want.raw_count == len(infra.clashes)
    assert out["per_band"] == want.per_band()
    assert out["coverage"]["complete"] == want.coverage.complete
    assert "partial" not in out["coverage"]
    # the closed results are counted as filtered even though most of them were never described
    closed = sum(1 for c in infra.clashes if c.status in ("approved", "resolved"))
    assert closed > 8 * extract.CLOSED_SAMPLE, "the fixture must have more closed results than the sample"
    assert sum(out["filtered"].values()) == sum(want.filtering.values())


def test_closed_results_are_sampled_not_all_described(infra, serve):
    app = _app(serve(infra))
    _run(app)
    cs = app.result.clashset
    closed_described = [c for c in cs.clashes if c.status in ("approved", "resolved")]
    assert 0 < len(closed_described) <= 8 * extract.CLOSED_SAMPLE
    total_closed = sum(1 for c in infra.clashes if c.status in ("approved", "resolved"))
    assert len(closed_described) + sum(cs.closed_unextracted.values()) == total_closed


def test_closed_results_are_all_described_when_the_profile_keeps_them(infra, serve, monkeypatch):
    app = _app(serve(infra))
    app.profile.raw.setdefault("noise", {})["drop_closed"] = False
    _run(app)
    assert len(app.result.clashset.clashes) == len(infra.clashes)
    assert not app.result.clashset.closed_unextracted


def test_cap_gives_a_partial_analysis_that_says_so(infra, serve, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_CLASHES", "600")
    app = _app(serve(infra))
    out = _run(app)
    cov = out["coverage"]
    assert cov["complete"] is False
    part = cov["partial"]
    assert [r["code"] for r in part["reasons"]] == ["cap"]
    assert part["open_extracted"] < part["open_available"]
    assert part["tests_partial"] >= 1 and part["tests_total"] == 8
    assert any("PARCIAL" in w and "600" in w for w in cov["warnings"])
    # fair sharing: every test contributes something instead of the first ones taking the whole budget
    per_test = {}
    for c in app.result.clashset.clashes:
        per_test[c.test] = per_test.get(c.test, 0) + 1
    assert len(per_test) == 8
    assert max(per_test.values()) <= 2 * min(per_test.values()) + extract.CLOSED_SAMPLE


def test_cap_keeps_open_results_first(serve, monkeypatch):
    cs = build_infra(tests=4, per_test=400, seed=9)
    open_total = sum(1 for c in cs.clashes if c.status not in ("approved", "resolved"))
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_CLASHES", str(open_total // 2))
    app = _app(serve(cs))
    _run(app)
    got = app.result.clashset.clashes
    assert sum(1 for c in got if c.status in ("approved", "resolved")) <= 4 * extract.CLOSED_SAMPLE
    assert sum(1 for c in got if c.status not in ("approved", "resolved")) >= open_total // 2 - 4 * extract.CLOSED_SAMPLE


def test_addin_memory_guard_stops_the_extraction_and_says_why(infra, serve):
    out = _run(_app(serve(infra, page_memory_stop_after=500)))
    part = out["coverage"]["partial"]
    assert [r["code"] for r in part["reasons"]] == ["memory_addin"]
    assert out["coverage"]["complete"] is False
    assert any("PARCIAL" in w and "Navisworks" in w for w in out["coverage"]["warnings"])


def test_server_memory_budget_stops_the_extraction(infra, serve, monkeypatch):
    seen = iter(range(10_000))
    monkeypatch.setattr(extract, "rss_mb", lambda: next(seen) * 40)  # grows 40 MB per check
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_SERVER_MB", "100")
    out = _run(_app(serve(infra)))
    assert [r["code"] for r in out["coverage"]["partial"]["reasons"]] == ["memory_server"]


def test_time_budget_stops_the_extraction(infra, serve, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_EXTRACT_S", "1")
    out = _run(_app(serve(infra, page_delay=0.4)))
    assert [r["code"] for r in out["coverage"]["partial"]["reasons"]] == ["time"]
    assert any("tiempo" in w for w in out["coverage"]["warnings"])


def test_extraction_is_one_job_across_retries_and_can_be_cancelled(serve):
    cs = build_infra(tests=6, per_test=3000, seed=2)
    app = _app(serve(cs))
    first = app.analyze("", None, 5, 0.01, "", None)
    assert first["state"] == "running" and first["job_id"].startswith("ext-")
    again = app.analyze("", None, 5, 0.01, first["job_id"], None)
    assert again["job_id"] == first["job_id"]
    status = app.job("status", first["job_id"])
    assert status["kind"] == "extraction" and "results_described" in status["progress"]
    assert app.status()["extraction_job"]["job_id"] == first["job_id"]
    out = app.job("cancel", first["job_id"])
    assert out["state"] in ("cancelled", "completed", "running")
    assert app.pending_analysis == {}


def test_an_add_in_without_paging_still_works(infra, serve, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_MAX_CLASHES", "40000")
    out = _run(_app(serve(infra, legacy=True)))
    assert out["raw_count"] == len(infra.clashes)
    assert "partial" not in out["coverage"]


def test_a_document_that_changes_during_the_extraction_is_refused(infra, serve):
    sim = serve(infra)
    app = _app(sim)
    first = app.analyze("", None, 5, 0.01, "", None)
    sim.fingerprint = "changed"  # another document took the place of the one the extraction started on
    with pytest.raises(ToolFault):
        for _ in range(400):
            out = app.analyze("", None, 5, 5, first["job_id"], None)
            if out.get("state") != "running":
                break
            time.sleep(0.05)


def test_unknown_test_names_are_refused(infra, serve):
    with pytest.raises(ToolFault):
        _run(_app(serve(infra)), tests=["no such test"])
