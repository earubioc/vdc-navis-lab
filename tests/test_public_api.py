"""The public interface plugins may use (D-14): if a signature changes without a version bump, this fails.

Adding a member is compatible (minor version). Removing or changing one needs a new Pro for the new minor, so this
table must change in the same commit, and the version policy in plugins.py says what that costs.
"""
import dataclasses
import inspect

import pytest

from vdc_navis_lab import exports, views
from vdc_navis_lab.bridge import Bridge
from vdc_navis_lab.capabilities import CATALOG, Capabilities
from vdc_navis_lab.engine import plan as eplan
from vdc_navis_lab.engine.snapshot import snapshot_of
from vdc_navis_lab.errors import ToolFault
from vdc_navis_lab.plugins import PluginInfo, load_plugins
from vdc_navis_lab.service import PLAN_TTL, App, Plan

SIGNATURES = {
    App.require_writable: "(self) -> 'None'",
    App.require_result: "(self) -> 'AnalysisResult'",
    Bridge.resolve: "(self, for_write: 'bool' = False) -> 'tuple[Endpoint, dict[str, Any], str]'",
    Bridge.call_at: "(self, ep: 'Endpoint', method: 'str', params: 'dict[str, Any] | None' = None, timeout: 'float | None' = None) -> 'Any'",
    Bridge.call: "(self, method: 'str', params: 'dict[str, Any] | None' = None, *, for_write: 'bool' = False, timeout: 'float | None' = None) -> 'tuple[Any, dict[str, Any], str]'",
    Capabilities.provide: "(self, name: 'str', fn: 'Callable[..., Any]', plugin: 'str' = '', available: 'Callable[[], bool] | None' = None) -> 'None'",
    Capabilities.has: "(self, name: 'str') -> 'bool'",
    Capabilities.call: "(self, name: 'str', *args: 'Any', **kwargs: 'Any') -> 'Any'",
    Capabilities.names: "(self) -> 'dict[str, list[str]]'",
    views.action_text: "(issue: 'Issue', profile: 'Profile', lang: 'str') -> 'str'",
    views.coverage_view: "(result: 'AnalysisResult', lang: 'str') -> 'dict[str, Any]'",
    views.pair_label: "(issue: 'Issue', profile: 'Profile', lang: 'str') -> 'str'",
    views.reasons_text: "(issue: 'Issue', profile: 'Profile', lang: 'str', limit: 'int' = 4) -> 'list[str]'",
    views.cause_text: "(cause: 'Cause', lang: 'str') -> 'dict[str, str]'",
    eplan.hotspots: "(result: 'AnalysisResult', cell_m: 'float' = 10.0, limit: 'int' = 5) -> 'list[dict]'",
    eplan.matrix: "(result: 'AnalysisResult') -> 'dict[str, dict[str, int]]'",
    exports.to_markdown: "(result: 'AnalysisResult', profile: 'Profile', limit: 'int' = 25) -> 'str'",
    snapshot_of: "(result) -> 'dict[str, Any]'",
}

APP_FIELDS = ["bridge", "profile", "result", "analysis_instance", "seen_revision", "pending_analysis", "plans",
              "setup_plans", "pending_save", "census_cache", "sleeve_cache", "plugins", "log", "capabilities"]
PLAN_FIELDS = ["id", "analysis_id", "instance_id", "fingerprint", "revision", "created", "groups", "statuses",
               "viewpoints", "preview", "sets", "executed"]

# What each capability is called with by the core. A plugin implements exactly these.
CAPABILITY_CALLS = {
    "writes.execute": "(app, plan_id)",
    "setup.execute": "(app, plan_id)",
    "document.save": "(app, ep, doc, target, key)",
    "report.csv": "(result, profile, limit)", "report.bcf": "(result, profile, limit)",
    "report.pdf": "(result, profile, limit)", "report.handoff": "(result, profile, limit)",
    "report.json": "(result, profile, limit)",
    "report.image": "(app, ep, issue, target)",
    "snapshot.compare": "(before, after)",
    "profiles.packs": "()",
}


@pytest.mark.parametrize("fn", list(SIGNATURES), ids=lambda f: f.__qualname__)
def test_public_signature_is_frozen(fn):
    assert str(inspect.signature(fn)) == SIGNATURES[fn]


def test_public_fields_are_frozen():
    assert [f.name for f in dataclasses.fields(App)] == APP_FIELDS
    assert [f.name for f in dataclasses.fields(Plan)] == PLAN_FIELDS
    assert [f.name for f in dataclasses.fields(PluginInfo)] == ["name", "version", "core_requires", "provides", "state", "detail"]
    assert PLAN_TTL == 30 * 60 and ToolFault("c", "m").to_dict() == {"error": "c", "detail": "m"}
    assert list(inspect.signature(load_plugins).parameters) == ["app", "mcp", "entry_points", "core_version"]


def test_capability_catalogue_and_call_shapes_are_frozen():
    assert set(CAPABILITY_CALLS) == set(CATALOG)


@pytest.mark.skipif(not __import__("conftest").PRO_AVAILABLE, reason="needs the Pro package")
def test_the_pro_package_implements_the_frozen_call_shapes():
    import vdc_navis_lab_pro as pro
    for name, shape in CAPABILITY_CALLS.items():
        fn = pro.providers()[name]
        want = [p.strip() for p in shape.strip("()").split(",") if p.strip()]
        got = [p for p in inspect.signature(fn).parameters]
        assert got == want, (name, got, want)
