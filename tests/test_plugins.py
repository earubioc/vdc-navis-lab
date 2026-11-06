"""The extension point: capability catalogue, plugin discovery, version policy, the pro_required gate, the usage log.

These tests need no Pro package: they use fake plugins. They are the guarantee that Community alone never crashes
and that a missing, incompatible, failing or unlicensed plugin turns into `pro_required`, never an exception.
"""
import json
from types import SimpleNamespace

import pytest

from vdc_navis_lab import __version__
from vdc_navis_lab.capabilities import CATALOG, Capabilities
from vdc_navis_lab.errors import ToolFault
from vdc_navis_lab.plugins import PluginInfo, core_requirement, load_plugins, parse_version, satisfies
from vdc_navis_lab.service import App


def _ep(name, fn, requires=("vdc-navis-lab>=1.1,<1.2",), version="9.9.9"):
    return SimpleNamespace(name=name, load=lambda: fn, dist=SimpleNamespace(version=version, requires=list(requires)))


def _fake_register(mcp, app):
    app.capabilities.provide("report.csv", lambda r, profile, limit: b"fake,csv\n", plugin="fake")
    return PluginInfo(name="fake", version="9.9.9", detail=lambda: {"license": {"state": "valid"}})


# ------------------------------------------------------------------ version policy (D-14)
def test_version_policy_pro_nm_needs_core_nmx():
    spec = ">=1.1,<1.2"
    assert satisfies("1.1.0", spec) and satisfies("1.1.7", spec)
    assert not satisfies("1.0.9", spec) and not satisfies("1.2.0", spec) and not satisfies("2.0.0", spec)
    assert satisfies("1.1", spec) and parse_version("1.1.0rc1") == (1, 1, 0)


def test_core_requirement_is_read_from_package_metadata():
    assert core_requirement(["mcp>=2", "vdc-navis-lab (>=1.1,<1.2)"]) == ">=1.1,<1.2"
    assert core_requirement(["vdc_navis_lab<1.2,>=1.1"]) == "<1.2,>=1.1"
    assert core_requirement(["vdc-navis-lab-pro>=1"]) is None and core_requirement([]) is None


def test_this_core_satisfies_the_policy_a_minor_pro_declares():
    major, minor = __version__.split(".")[:2]
    assert satisfies(__version__, f">={major}.{minor},<{major}.{int(minor) + 1}")


# ------------------------------------------------------------------ catalogue
def test_catalogue_rejects_unknown_and_duplicate_names():
    caps = Capabilities()
    with pytest.raises(ValueError):
        caps.provide("report.docx", lambda: None)
    caps.provide("report.csv", lambda *a: b"")
    with pytest.raises(ValueError):
        caps.provide("report.csv", lambda *a: b"")
    with pytest.raises(ValueError):
        caps.call("not.a.capability")


def test_no_provider_means_pro_required_with_a_hint_a_model_can_act_on():
    caps = Capabilities()
    with pytest.raises(ToolFault) as e:
        caps.call("writes.execute", None, "P-1")
    d = e.value.to_dict()
    assert d["error"] == "pro_required" and d["data"] == {"capability": "writes.execute"}
    assert "do not retry" in d["hint"] and "claim that the change was made" in d["hint"]
    caps.disabled = True
    assert "VDC_NAVIS_LAB_NO_PLUGINS" in caps.missing_fault("report.pdf").message


def test_an_unavailable_provider_explains_itself_and_is_listed_as_missing():
    caps = Capabilities()

    def expired(*a):
        raise ToolFault("pro_required", "the Pro license is expired", "renew it", {"capability": "report.csv"})

    caps.provide("report.csv", expired, plugin="p", available=lambda: False)
    assert not caps.has("report.csv") and "report.csv" in caps.names()["missing"]
    with pytest.raises(ToolFault, match="expired"):
        caps.call("report.csv")


# ------------------------------------------------------------------ discovery
def test_a_compatible_plugin_is_loaded_and_its_capability_is_used(community_app):
    infos = load_plugins(community_app, None, [_ep("fake", _fake_register)], core_version="1.1.0")
    assert infos[0].state == "loaded" and infos[0].provides == ("report.csv",)
    community_app.analyze("", None, 3, 20, "", None)
    out = community_app.report("csv", "x.csv", True, 25, None)
    assert out["kind"] == "csv"
    ext = community_app.status()["extensions"]
    assert ext["plugins"][0]["license"]["state"] == "valid" and "report.csv" in ext["available"]
    assert "writes.execute" in ext["missing"]


def test_an_incompatible_plugin_is_never_loaded_halfway(community_app):
    called = []

    def register(mcp, app):
        called.append(1)

    infos = load_plugins(community_app, None, [_ep("old", register, requires=("vdc-navis-lab>=1.0,<1.1",))], core_version="1.1.0")
    assert infos[0].state == "incompatible" and not called and "1.1.0" in infos[0].detail["why"]
    undeclared = load_plugins(community_app, None, [_ep("blind", register, requires=())], core_version="1.1.0")
    assert undeclared[0].state == "incompatible" and not called


def test_a_failing_plugin_does_not_stop_the_server(community_app):
    def boom(mcp, app):
        raise RuntimeError("bad plugin")

    infos = load_plugins(community_app, None, [_ep("boom", boom), _ep("fake", _fake_register)], core_version="1.1.0")
    assert [i.state for i in infos] == ["failed", "loaded"] and "RuntimeError" in infos[0].detail["why"]
    assert community_app.status()["server"]["version"]


def test_the_env_var_disables_every_plugin_even_if_installed(community_app, monkeypatch):
    monkeypatch.setenv("VDC_NAVIS_LAB_NO_PLUGINS", "1")
    infos = load_plugins(community_app, None, [_ep("fake", _fake_register)], core_version="1.1.0")
    assert infos[0].state == "disabled" and not community_app.capabilities.has("report.csv")
    with pytest.raises(ToolFault) as e:
        community_app.report("csv", "", False, 25, None) if community_app.result else community_app.capabilities.call("report.csv")
    assert e.value.code in ("pro_required", "no_analysis")


# ------------------------------------------------------------------ Community alone: every Pro entry point says pro_required
PRO_CALLS = {
    "writes.execute": lambda a: a.apply(None, "P-0", False),
    "setup.execute": lambda a: a.setup("plan", None, "S-0", False),
    "report.csv": lambda a: a.report("csv", "", False, 25, None),
    "report.bcf": lambda a: a.report("bcf", "", False, 25, None),
    "report.pdf": lambda a: a.report("pdf", "", False, 25, None),
    "report.handoff": lambda a: a.report("handoff", "", False, 25, None),
    "report.json": lambda a: a.report("json", "", False, 25, None),
    "report.image": lambda a: a.report("image", "", False, 25, None, a.issues("", "", "", "", "", "rank", 1, 0, None)["items"][0]["id"]),
    "snapshot.compare": lambda a: a.snapshot("compare", "", "v1"),
    "profiles.packs": lambda a: a.profile_action("load", "pack:anything", None),
}


@pytest.mark.parametrize("capability", sorted(PRO_CALLS))
def test_community_alone_answers_pro_required_never_an_exception(community_app, capability):
    community_app.analyze("", None, 3, 20, "", None)
    with pytest.raises(ToolFault) as e:
        PRO_CALLS[capability](community_app)
    assert e.value.code == "pro_required" and e.value.data == {"capability": capability}


def test_document_save_previews_in_community_and_refuses_to_execute(community_app):
    assert community_app.document("save", "", False, False)["dry_run"] is True
    with pytest.raises(ToolFault) as e:
        community_app.document("save", "", True, False)
    assert e.value.code == "pro_required" and e.value.data == {"capability": "document.save"}


def test_every_capability_of_the_catalogue_is_reached_from_the_core():
    covered = set(PRO_CALLS) | {"document.save"}
    assert covered == set(CATALOG)


def test_what_community_keeps(community_app):
    a = community_app
    a.analyze("", None, 3, 20, "", None)
    assert a.apply([{"op": "group", "issues": "top:2"}], "", True)["dry_run"] is True      # write preview
    assert "markdown" in a.report("markdown", "", False, 25, None)                         # markdown inline
    assert a.report("markdown", "", False, 25, None) and a.report("markdown", "m.md", True, 25, None)["bytes"] > 0
    assert a.snapshot("save", "v1", "")["saved"] == "v1" and a.snapshot("list", "", "")["snapshots"]
    assert a.setup("list", None, "", True)["sets"] is not None and a.setup("properties", None, "", True)
    packs = a.profile_action("packs", "", None)
    assert packs["packs"] == [] and "Pro" in packs["note"]


# ------------------------------------------------------------------ usage log
def test_usage_log_is_off_by_default_and_records_only_capability_date_outcome(community_app, monkeypatch, tmp_path):
    log = tmp_path / "home" / "usage.log"
    with pytest.raises(ToolFault):
        community_app.capabilities.call("report.pdf", object(), "a/secret/project/name.nwd")
    assert not log.exists()
    monkeypatch.setenv("VDC_NAVIS_LAB_USAGE_LOG", "1")
    with pytest.raises(ToolFault):
        community_app.capabilities.call("report.pdf", object(), "a/secret/project/name.nwd")
    community_app.capabilities.provide("report.csv", lambda *a: b"x", plugin="t")
    community_app.capabilities.call("report.csv", object(), "a/secret/project/name.nwd")
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [(r["capability"], r["outcome"]) for r in rows] == [("report.pdf", "pro_required"), ("report.csv", "ok")]
    assert set(rows[0]) == {"ts", "capability", "outcome"} and "secret" not in log.read_text(encoding="utf-8")
