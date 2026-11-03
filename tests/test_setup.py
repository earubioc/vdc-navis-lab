import pytest

from vdc_navis_lab.engine.audit import audit_models
from vdc_navis_lab.profile import Profile, ProfileError, check_rule
from vdc_navis_lab.service import ToolFault



def live(app):
    out = app.analyze("", None, 10, 10, "", None)
    assert "analysis_id" in out, out
    return out


def test_discipline_sets_and_tests_from_the_matrix_go_through_a_plan(app, sim):
    plan = app.setup("plan", [{"op": "discipline_sets"}, {"op": "tests", "pairs": "matrix"}], "", True)
    assert plan["dry_run"] and plan["sets"] >= 3 and plan["tests"] >= 3
    assert not sim.setup_sets and not sim.setup_tests, "a dry run changes nothing"
    done = app.setup("plan", None, plan["plan_id"], False)
    assert done["state"] == "completed", done
    assert done["verified"] == {"sets": plan["sets"], "tests": plan["tests"]}
    assert len(sim.setup_tests) == plan["tests"] and "hint" in done
    again = app.setup("plan", [{"op": "discipline_sets"}, {"op": "tests", "pairs": "matrix"}], "", True)
    redo = app.setup("plan", None, again["plan_id"], False)
    assert redo["applied"]["sets_added"] == 0 and redo["applied"]["tests_reused"] == plan["tests"]
    listing = app.setup("list", None, "", True)
    assert any(r["kind"] == "search" for r in listing["sets"]) and len(listing["tests"]) > plan["tests"]
    with pytest.raises(ToolFault):
        app.setup("plan", None, plan["plan_id"], False)  # already executed


def test_tests_pairs_are_checked_and_missing_disciplines_skipped(app):
    with pytest.raises(ToolFault):
        app.setup("plan", [{"op": "tests", "pairs": ["STR-NOPE"]}], "", True)
    with pytest.raises(ToolFault):
        app.setup("plan", [{"op": "tests", "pairs": ["STR-STR"]}], "", True)
    with pytest.raises(ToolFault):
        app.setup("plan", [{"op": "tests", "type": "soft"}], "", True)
    plan = app.setup("plan", [{"op": "tests", "pairs": ["STR-ELE", "ELE-STR", "STR-DRN"]}], "", True)
    names = [t["name"] for t in plan["ops"][0]["tests"]]
    assert names == ["VDC STR-ELE"], "reversed duplicate dropped"
    assert plan["ops"][0]["skipped"][0]["pair"] == "STR-DRN"
    assert plan["sets"] == 2, "the tests bring their two discipline sets along"
    only_tests = app.setup("plan", None, plan["plan_id"], False)
    assert only_tests["state"] == "completed" and only_tests["verified"] == {"sets": 2, "tests": 1}


def test_search_set_needs_valid_criteria(app, sim):
    with pytest.raises(ToolFault):
        app.setup("plan", [{"op": "search_set", "name": "x", "where": []}], "", True)
    with pytest.raises(ToolFault):
        app.setup("plan", [{"op": "search_set", "name": "x", "where": [{"field": "color", "value": "r"}]}], "", True)
    plan = app.setup("plan", [{"op": "search_set", "name": "Ductos",
                               "where": [{"field": "category", "op": "contains", "value": "Duct"}]}], "", True)
    assert app.setup("plan", None, plan["plan_id"], False)["state"] == "completed"
    assert app.setup("list", None, "", True)["sets"][0]["kind"] == "search"
    miss = app.setup("plan", [{"op": "search_set", "name": "Nada",
                               "where": [{"field": "level", "value": "__none__"}]}], "", True)
    out = app.setup("plan", None, miss["plan_id"], False)
    assert out["state"] == "failed" and out["missing"]


def test_setup_refuses_when_read_only_and_when_the_document_changed(app, sim, monkeypatch):
    plan = app.setup("plan", [{"op": "discipline_sets"}], "", True)
    sim.fingerprint = "changed"
    with pytest.raises(ToolFault) as e:
        app.setup("plan", None, plan["plan_id"], False)
    assert e.value.code == "stale_document"
    monkeypatch.setenv("VDC_NAVIS_LAB_READ_ONLY", "1")
    with pytest.raises(ToolFault) as e:
        app.setup("plan", [{"op": "discipline_sets"}], "", True)
    assert e.value.code == "read_only"


def test_properties_helper_returns_names(app):
    out = app.setup("properties", None, "", True)
    assert out["categories"][0]["properties"]


def test_group_by_level_makes_one_group_per_test_and_level(app, sim):
    live(app)
    preview = app.apply([{"op": "group", "issues": "all", "by": "level"}], "", True)
    op = preview["ops"][0]
    assert op["by"] == "level" and op["groups"] >= 2
    done = app.apply(None, preview["plan_id"], False)
    assert done["state"] == "completed" and done["verified"]["groups"] == done["requested"]["groups"]
    with pytest.raises(ToolFault):
        app.apply([{"op": "group", "issues": "all", "by": "storey"}], "", True)
    pair = app.apply([{"op": "group", "issues": "all", "by": "pair"}], "", True)
    assert pair["ops"][0]["groups"] >= 2


def test_rules_from_the_profile_expand_into_ordinary_ops(app, sim):
    live(app)
    app.profile = Profile.from_text(
        open("src/vdc_navis_lab/profiles/default.toml", encoding="utf-8").read()
        + '\n[[rules]]\nname = "bajos"\nwhen = { priority = "low" }\nstatus = "reviewed"\n'
        + '\n[[rules]]\nname = "criticos"\nwhen = { priority = "critical" }\nset = true\nviewpoint = true\n')
    preview = app.apply([{"op": "rules"}], "", True)
    kinds = [o["op"] for o in preview["ops"]]
    assert kinds == ["status", "viewpoint", "set"], kinds
    only = app.apply([{"op": "rules", "names": ["criticos"]}], "", True)
    assert [o["op"] for o in only["ops"]] == ["viewpoint", "set"]
    inline = app.apply([{"op": "rules", "rules": [{"name": "r", "when": {"pair": "str-ele"}, "status": "reviewed"}]}], "", True)
    assert inline["ops"][0]["op"] == "status"
    with pytest.raises(ToolFault):
        app.apply([{"op": "rules", "rules": [{"when": {"priority": "urgent"}, "status": "reviewed"}]}], "", True)


def test_rules_without_any_rule_say_how_to_add_them(app):
    live(app)
    with pytest.raises(ToolFault) as e:
        app.apply([{"op": "rules"}], "", True)
    assert "rules" in e.value.hint


def test_profile_validation_rejects_bad_rules():
    base = open("src/vdc_navis_lab/profiles/default.toml", encoding="utf-8").read()
    with pytest.raises(ProfileError):
        Profile.from_text(base + '\n[[rules]]\nwhen = { priority = "low" }\n')  # no action
    with pytest.raises(ProfileError):
        Profile.from_text(base + '\n[[rules]]\nwhen = { pair = "STR-XXX" }\nstatus = "reviewed"\n')
    assert check_rule({"when": {"priority": "low"}, "status": "reviewed"}, Profile.default().disciplines) == []


def _models(**over):
    base = [
        {"name": "A_EST.nwc", "elements": 100, "proposed": "STR", "agree": True, "bbox": [[0, 0, 0], [60, 40, 20]]},
        {"name": "A_ELE.nwc", "elements": 80, "proposed": "ELE", "agree": True, "bbox": [[2, 2, 0], [58, 38, 19]]},
        {"name": "A_HID.nwc", "elements": 60, "proposed": "PLB", "agree": True, "bbox": [[1, 1, 0], [59, 39, 19]]},
    ]
    base.extend(over.get("extra", []))
    return base


def _codes(res):
    return {(r["name"], f["code"]) for r in res["models"] for f in r["findings"]}


def test_audit_clean_federation_has_no_model_findings(profile):
    res = audit_models(_models(), profile, "es")
    assert all(f["code"] == "ok" for r in res["models"] for f in r["findings"])
    assert {g["code"] for g in res["global"]} == {"missing_discipline"}  # HVAC and FIRE are expected but absent


def test_audit_flags_empty_far_unit_and_unclassified_models(profile):
    extra = [
        {"name": "B_VACIO.nwc", "elements": 0, "proposed": "HVAC", "agree": True, "bbox": None},
        {"name": "C_LEJOS.nwc", "elements": 50, "proposed": "HVAC", "agree": True, "bbox": [[900000, 900000, 0], [900060, 900040, 20]]},
        {"name": "D_MM.nwc", "elements": 50, "proposed": "FIRE", "agree": True, "bbox": [[0, 0, 0], [60000, 40000, 20000]]},
        {"name": "E_X.nwc", "elements": 5, "proposed": "OTHER", "agree": False, "by_file_name": "ARC",
         "by_categories": {"STR": 0.9}, "bbox": [[0, 0, 0], [10, 10, 10]]},
    ]
    res = audit_models(_models(extra=extra), profile, "en")
    codes = _codes(res)
    assert ("B_VACIO.nwc", "empty") in codes
    assert ("C_LEJOS.nwc", "far") in codes and ("C_LEJOS.nwc", "no_overlap") in codes
    assert ("D_MM.nwc", "size") in codes and ("D_MM.nwc", "huge") in codes
    assert ("E_X.nwc", "unclassified") in codes and ("E_X.nwc", "disagree") in codes
    assert res["status"] == "fail" and res["counts"]["error"] >= 1


def test_audit_flags_duplicates_and_missing_boxes(profile):
    dup = _models(extra=[{"name": "A_EST.nwc", "elements": 3, "proposed": "STR", "agree": True, "bbox": [[0, 0, 0], [1, 1, 1]]},
                         {"name": "F_SINCAJA.nwc", "elements": 3, "proposed": "FIRE", "agree": True, "bbox": None}])
    codes = _codes(audit_models(dup, profile, "es"))
    assert ("A_EST.nwc", "duplicate") in codes and ("F_SINCAJA.nwc", "no_bbox") in codes


def test_nw_model_audit_flag_attaches_the_audit(app):
    plain = app.model()
    assert "audit" not in plain and all("bbox" not in m for m in plain["models"])
    audited = app.model(True)
    assert audited["audit"]["status"] in ("ok", "warn", "fail") and audited["audit"]["models"]
