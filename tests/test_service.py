import json

import pytest

from vdc_navis_lab.bridge import Bridge
from vdc_navis_lab.bridge.transport import Endpoint
from vdc_navis_lab.service import App, ToolFault


def live(app):
    out = app.analyze("", None, 10, 10, "", None)
    assert "analysis_id" in out, out
    return out


def test_status_without_navisworks_does_not_fail():
    out = App(bridge=Bridge(lambda: [])).status()
    assert out["bridge"]["connected"] is False and "offline" in out["bridge"]["hint"]
    assert out["analysis"] == {"present": False}


def test_live_analysis_matches_offline_analysis(app, tower, profile):
    from vdc_navis_lab.engine import analyze
    out = live(app)
    offline = analyze(tower, profile)
    assert out["issues"] == len(offline.issues) and out["raw_count"] == len(tower.clashes)
    assert app.status()["analysis"]["stale"] is False


def test_issues_filters_and_detail(app):
    live(app)
    crit = app.issues("critical", "", "", "", "", "rank", 10, 0, None)
    assert crit["total"] == 1
    iid = crit["items"][0]["id"]
    d = app.issue(iid, "en")
    assert d["priority"] == "critical" and d["representative"]["a"]["bbox"] and d["components"]["penetration"] == 1.0
    assert app.issues("", "FIRE", "", "", "", "rank", 10, 0, None)["total"] == 1
    assert app.issues("", "", "", "", "HVAC", "score", 5, 0, "en")["items"][0]["score"] >= 60
    with pytest.raises(ToolFault):
        app.issue("NW-NOPE", None)
    with pytest.raises(ToolFault):
        app.issues("urgent", "", "", "", "", "rank", 10, 0, None)


def test_apply_two_step_flow_verifies_by_rereading(app, sim):
    live(app)
    plan = app.apply([{"op": "group", "issues": "top:5"}, {"op": "status", "issues": {"priority": "low"}, "status": "reviewed"}],
                     "", True)
    assert plan["dry_run"] is True and plan["issues"] >= 5 and not sim.groups, "dry run changes nothing"
    done = app.apply(None, plan["plan_id"], False)
    assert done["state"] == "completed" and done["verified"]["groups"] == 5
    assert len(sim.groups) == 5
    assert app.status()["analysis"]["stale"] is False, "our own change is not staleness"
    with pytest.raises(ToolFault, match="already executed"):
        app.apply(None, plan["plan_id"], False)


def test_execution_never_takes_raw_ops(app):
    live(app)
    with pytest.raises(ToolFault, match="plan_id"):
        app.apply([{"op": "group", "issues": "top:1"}], "", False)


def test_external_change_makes_analysis_stale_and_blocks_writes(app, sim):
    live(app)
    plan = app.apply([{"op": "group", "issues": "top:2"}], "", True)
    sim.revision += 1  # someone edits the model in Navisworks
    assert app.status()["analysis"]["stale"] is True
    with pytest.raises(ToolFault) as exc:
        app.apply(None, plan["plan_id"], False)
    assert exc.value.code in ("stale_document", "outdated_analysis")
    with pytest.raises(ToolFault) as exc:
        app.apply([{"op": "group", "issues": "top:2"}], "", True)
    assert exc.value.code == "outdated_analysis"


def test_writes_need_a_live_analysis(app, tmp_path):
    f = tmp_path / "a.json"
    from vdc_navis_lab.sample.generator import build
    f.write_text(json.dumps(build()[0].to_dict()), encoding="utf-8")
    assert app.analyze(str(f), None, 5, 1, "", None)["issues"] > 0
    with pytest.raises(ToolFault) as exc:
        app.apply([{"op": "group", "issues": "top:1"}], "", True)
    assert exc.value.code == "needs_live_analysis"


def test_read_only_mode_blocks_every_write(app, monkeypatch):
    live(app)
    plan = app.apply([{"op": "group", "issues": "top:1"}], "", True)  # previews are allowed
    monkeypatch.setenv("VDC_NAVIS_LAB_READ_ONLY", "1")
    for call in (lambda: app.apply(None, plan["plan_id"], False), lambda: app.run(None, 1),
                 lambda: app.document("save", "", True, False)):
        with pytest.raises(ToolFault) as exc:
            call()
        assert exc.value.code == "read_only"


def test_bad_ops_are_rejected(app):
    live(app)
    for ops in ([{"op": "delete"}], [{"op": "status", "issues": "top:1", "status": "new"}],
                [{"op": "group", "issues": ["NW-NOPE"]}], [{"op": "group", "issues": "top:x"}], []):
        with pytest.raises(ToolFault):
            app.apply(ops, "", True)


def test_closing_critical_issues_warns(app):
    live(app)
    plan = app.apply([{"op": "status", "issues": {"priority": "critical"}, "status": "approved"}], "", True)
    assert "critical" in plan["ops"][0]["warning"]


def test_status_change_then_reanalysis_drops_closed_issues(app):
    first = live(app)
    plan = app.apply([{"op": "status", "issues": {"priority": "low"}, "status": "approved"},
                      {"op": "status", "issues": {"priority": "medium"}, "status": "approved"}], "", True)
    app.apply(None, plan["plan_id"], False)
    second = app.analyze("", None, 10, 10, "", None)
    assert second["issues"] < first["issues"]
    assert second["filtered"]["ya aprobado o resuelto"] > first["filtered"]["ya aprobado o resuelto"]


def test_profile_assign_reranks_without_reextracting(app):
    live(app)
    before = app.result.analysis_id
    out = app.profile_action("assign", "", {"TORRE-HVAC.nwc": "PLB"})
    assert out["analysis_refreshed"] is True and app.result.analysis_id != before
    with pytest.raises(ToolFault):
        app.profile_action("assign", "", {"x.nwc": "NOPE"})
    assert app.profile_action("reset", "", None)["overrides"] == {"TORRE-HVAC.nwc": "PLB"}


def test_model_census_flags_disagreement_and_query_groups_clean_levels(app):
    m = app.model()
    assert m["models"] and all({"name", "proposed"} <= set(x) for x in m["models"])
    assert all(x["proposed"] in app.profile.disciplines for x in m["models"])
    q = app.query([{"field": "category", "op": "eq", "value": "Ducts"}], "level", 10)
    assert q["count"] == 16 and all('"' not in g["key"] and "#" not in g["key"] for g in q["groups"])
    with pytest.raises(ToolFault):
        app.query([{"field": "category", "op": "regex", "value": "x"}], "", 5)


def test_run_marks_tests_and_bumps_revision(app, sim):
    live(app)
    out = app.run(["ELE vs STR"], 5)
    assert out["state"] == "completed"
    assert app.status()["analysis"]["stale"] is True, "new results make the old analysis stale"
    with pytest.raises(Exception):
        app.run(["no such test"], 5)


def test_report_files_and_inline(app, tmp_path):
    live(app)
    assert "markdown" in app.report("markdown", "", False, 5, "en")
    out = app.report("csv", "tower.csv", False, 25, None)
    assert out["bytes"] > 100 and out["path"].endswith("tower.csv")
    with pytest.raises(ToolFault) as exc:
        app.report("csv", "tower.csv", False, 25, None)
    assert exc.value.code == "path_refused"
    with pytest.raises(ToolFault):
        app.report("csv", "../../escape.csv", True, 25, None)
    assert app.report("bcf", "tower.bcf", False, 25, None)["bytes"] > 100
    assert app.report("plan", "", False, 5, None)["packages"]


def test_snapshots_save_and_compare(app):
    live(app)
    assert app.snapshot("save", "v1", "")["issues"] > 0
    with pytest.raises(ToolFault):
        app.snapshot("save", "v1", "")
    with pytest.raises(ToolFault):
        app.snapshot("save", "../evil", "")
    d = app.snapshot("compare", "", "v1")
    assert d["new"] == [] and d["absent"] == []
    assert [s["name"] for s in app.snapshot("list", "", "")["snapshots"]] == ["v1"]


def test_document_save_requires_preview_first(app, sim):
    assert app.document("save", "", False, False)["dry_run"] is True
    with pytest.raises(ToolFault) as exc:
        app.document("save_as", "x.nwf", True, False)
    assert exc.value.code == "not_previewed"
    assert app.document("save", "", True, False)["state"] == "completed" and sim.saves == 1
    with pytest.raises(ToolFault):
        app.document("save", "", True, False)  # preview is single-use


def test_slow_extraction_returns_a_job_to_collect():
    from vdc_navis_lab.bridge.simulator import Simulator
    s = Simulator(job_delay=0.6)
    app = App(bridge=Bridge(lambda: [Endpoint.parse(s.start())]))
    try:
        pending = app.analyze("", None, 5, 0.05, "", None)
        assert pending["state"] == "running" and pending["job_id"]
        again = app.analyze("", None, 5, 0.01, "", None)  # joins, does not start a second export
        assert again["job_id"] == pending["job_id"] and len(s.jobs) == 1
        done = app.analyze("", None, 5, 10, pending["job_id"], None)
        assert done["issues"] > 0 and not app.pending_analysis
        with pytest.raises(ToolFault):
            app.analyze("", None, 5, 1, "job-bogus", None)
    finally:
        s.stop()


def test_status_lists_tests_and_flags_the_ones_never_run(app):
    t = app.status()["tests"]
    assert t["available"] is True and t["count"] == 9 and t["never_run"] == ["ELE vs STR"]
    assert {"name", "kind", "status", "count"} == set(t["items"][0])


def test_status_survives_an_addin_without_clash_tests(app, sim, monkeypatch):
    monkeypatch.setattr(sim, "m_clash_tests", lambda p: (_ for _ in ()).throw(__import__("vdc_navis_lab.bridge.simulator", fromlist=["Fault"]).Fault("unsupported", "no")))
    assert app.status()["tests"] == {"available": False, "reason": "unsupported", "detail": "no"}
