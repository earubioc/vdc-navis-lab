"""nw_setup: build the coordination scaffolding in Navisworks (discipline sets, search sets, clash tests).

Two steps like nw_apply: ops are previewed into a plan, and executing the plan re-reads what was written.
Nothing here needs an analysis: it works on the models and the profile.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .bridge.protocol import INVALID_PARAMS, NOT_FOUND, STALE_DOCUMENT
from .engine.tagging import Tagger

if TYPE_CHECKING:  # pragma: no cover
    from .service import App

TEST_TYPES = ("hard", "clearance")
MAX_SETUP_ITEMS = 200
FIELDS = ("model", "category", "family", "level", "name", "system")


@dataclass(slots=True)
class SetupPlan:
    id: str
    instance_id: str
    fingerprint: str
    revision: str
    created: float
    sets: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    preview: dict[str, Any]
    executed: bool = False


def classify(app: "App") -> tuple[dict[str, list[str]], dict[str, str]]:
    """{discipline: [model files]} and {file: discipline} for the models loaded in the open document."""
    census, _info, _note = app.census()
    tagger = Tagger(app.profile)
    by_disc: dict[str, list[str]] = {}
    by_file: dict[str, str] = {}
    for m in census["models"]:
        cats = m.get("categories", {})
        total = sum(cats.values()) or 1
        share: dict[str, float] = {}
        for cat, n in cats.items():
            d = tagger.discipline_of(cat, "")
            share[d] = share.get(d, 0) + n / total
        disc = tagger.discipline_of_file(m["name"]) or (max(share, key=share.get) if share else "OTHER")
        if m.get("elements", 0) == 0:
            continue
        by_file[m["name"]] = disc
        by_disc.setdefault(disc, []).append(m["name"])
    return by_disc, by_file


def _pairs(spec: Any, app: "App", present: set[str]) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    known = app.profile.disciplines
    raw = app.profile.raw.get("expected_pairs", []) if spec in (None, "", "matrix") else spec
    if not isinstance(raw, list) or not raw:
        raise ToolFault_(INVALID_PARAMS, "pairs must be 'matrix' or a list like ['STR-ELE', 'STR-HVAC']")
    pairs: list[tuple[str, str]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()
    for item in raw:
        parts = str(item).upper().split("-")
        if len(parts) != 2 or any(p not in known for p in parts) or parts[0] == parts[1]:
            raise ToolFault_(INVALID_PARAMS, f"pair {item!r} must name two different known disciplines, as A-B")
        key = frozenset(parts)
        if key in seen:
            continue
        seen.add(key)
        missing = [p for p in parts if p not in present]
        if missing:
            skipped.append({"pair": "-".join(parts), "reason": f"no hay modelo de {', '.join(missing)} en el documento"})
        else:
            pairs.append((parts[0], parts[1]))
    return pairs, skipped


def ToolFault_(code: str, message: str, hint: str = ""):
    from .service import ToolFault
    return ToolFault(code, message, hint)


def make_plan(app: "App", ops: list[dict[str, Any]]) -> dict[str, Any]:
    if not ops:
        raise ToolFault_(INVALID_PARAMS, "ops is empty",
                         "e.g. [{'op':'discipline_sets'}, {'op':'tests','pairs':'matrix'}]")
    ep, info, _ = app.bridge.resolve(for_write=True)
    doc = info.get("doc") or {}
    by_disc, _ = classify(app)
    present = set(by_disc)
    lang = app.profile.lang
    sets: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    for op in ops:
        kind = op.get("op") if isinstance(op, dict) else None
        if kind == "discipline_sets":
            wanted = [str(c).upper() for c in op.get("disciplines") or sorted(by_disc)]
            unknown = [c for c in wanted if c not in app.profile.disciplines]
            if unknown:
                raise ToolFault_(INVALID_PARAMS, f"unknown disciplines {unknown}")
            names = []
            skipped = []
            for code in wanted:
                files = by_disc.get(code)
                if not files:
                    skipped.append(code)
                    continue
                name = f"{code} {app.profile.label(code, lang)}"
                sets.append({"name": name, "files": files})
                names.append({"name": name, "models": len(files)})
            preview.append({"op": "discipline_sets", "sets": names, **({"skipped": skipped} if skipped else {})})
        elif kind == "search_set":
            name = str(op.get("name") or "").strip()
            where = op.get("where")
            if not name or not isinstance(where, list) or not where:
                raise ToolFault_(INVALID_PARAMS, "search_set needs a name and where=[{field,op,value}]",
                                 "field: category|family|level|name|system, or category+property for any property; op: eq|contains|wildcard")
            crit = []
            for c in where:
                if not isinstance(c, dict) or "value" not in c or not (c.get("field") in FIELDS or (c.get("category") and c.get("property"))):
                    raise ToolFault_(INVALID_PARAMS, "each criterion needs value and field (" + "|".join(FIELDS) + ") or category+property")
                if c.get("op", "eq") not in ("eq", "contains", "wildcard"):
                    raise ToolFault_(INVALID_PARAMS, "criterion op must be eq, contains or wildcard")
                crit.append({k: str(v) for k, v in c.items() if k in ("field", "op", "value", "category", "property", "internal")})
            if len(crit) > 6:
                raise ToolFault_(INVALID_PARAMS, "at most 6 criteria per search set")
            sets.append({"name": name[:120], "where": crit})
            preview.append({"op": "search_set", "name": name[:120], "criteria": len(crit)})
        elif kind == "tests":
            kind_t = str(op.get("type", "hard"))
            if kind_t not in TEST_TYPES:
                raise ToolFault_(INVALID_PARAMS, f"type must be one of {', '.join(TEST_TYPES)}")
            tol_mm = float(op.get("tolerance_mm", 1.0))
            if not 0 <= tol_mm <= 1000:
                raise ToolFault_(INVALID_PARAMS, "tolerance_mm must be between 0 and 1000")
            prefix = str(op.get("prefix", "VDC "))
            pairs, skipped = _pairs(op.get("pairs", "matrix"), app, present)
            made = []
            for a, b in pairs:
                name = f"{prefix}{a}-{b}"[:120]
                a_set, b_set = f"{a} {app.profile.label(a, lang)}", f"{b} {app.profile.label(b, lang)}"
                for code, set_name in ((a, a_set), (b, b_set)):  # a test points at its discipline sets: make sure they exist
                    if not any(x["name"] == set_name for x in sets):
                        sets.append({"name": set_name, "files": by_disc[code]})
                tests.append({"name": name, "type": kind_t, "tolerance_m": tol_mm / 1000.0, "a_set": a_set, "b_set": b_set})
                made.append({"name": name, "a_set": a_set, "b_set": b_set})
            preview.append({"op": "tests", "tests": made, **({"skipped": skipped} if skipped else {})})
        else:
            raise ToolFault_(INVALID_PARAMS, "each op needs op='discipline_sets', 'search_set' or 'tests'")
    if len(sets) + len(tests) > MAX_SETUP_ITEMS:
        raise ToolFault_("plan_too_large", f"limit is {MAX_SETUP_ITEMS} sets and tests per plan")
    plan = SetupPlan(id=f"S-{uuid.uuid4().hex[:8]}", instance_id=str(info.get("instance_id")),
                     fingerprint=str(doc.get("fingerprint")), revision=str(doc.get("revision", "")),
                     created=time.time(), sets=sets, tests=tests,
                     preview={"ops": preview, "sets": len(sets), "tests": len(tests)})
    app.setup_plans[plan.id] = plan
    from .service import PLAN_TTL
    return {"plan_id": plan.id, "dry_run": True, "document": doc.get("title"), "expires_in_s": PLAN_TTL,
            **plan.preview, "next": f"nw_setup(plan_id='{plan.id}') executes this plan; nothing was changed yet"}


def execute(app: "App", plan_id: str) -> dict[str, Any]:
    from .service import PLAN_TTL
    app._refuse_if_read_only()
    plan = app.setup_plans.get(plan_id)
    if plan is None:
        raise ToolFault_(NOT_FOUND, f"unknown setup plan {plan_id!r}", "plan again with nw_setup(ops=[...])")
    if plan.executed:
        raise ToolFault_("plan_executed", "this plan was already executed", "make a new plan")
    if time.time() - plan.created > PLAN_TTL:
        raise ToolFault_("plan_expired", "the plan is older than 30 minutes", "plan again")
    ep, info, _ = app.bridge.resolve(for_write=True)
    doc = info.get("doc") or {}
    if info.get("instance_id") != plan.instance_id or doc.get("fingerprint") != plan.fingerprint:
        raise ToolFault_(STALE_DOCUMENT, "the open document is not the one the plan was made for", "plan again")
    res = app.bridge.call_at(ep, "setup.apply", {"if_fingerprint": plan.fingerprint, "sets": plan.sets, "tests": plan.tests})
    plan.executed = True
    verified, applied, missing = res.get("verified", {}), res.get("applied", {}), res.get("missing", [])
    want_sets, want_tests = len(plan.sets), len(plan.tests)
    ok = verified.get("sets", 0) == want_sets and verified.get("tests", 0) == want_tests and not missing
    state = "completed" if ok else ("failed" if not (verified.get("sets") or verified.get("tests")) else "partial")
    live = app.bridge.call_at(ep, "hello")
    if app.analysis_instance == plan.instance_id and not applied.get("tests_added"):
        # sets are our own change, not staleness; new tests have no results yet, so they keep the analysis flagged
        app.seen_revision = str((live.get("doc") or {}).get("revision", ""))
    out = {"state": state, "requested": {"sets": want_sets, "tests": want_tests}, "applied": applied,
           "verified": verified, "missing": missing[:10]}
    if res.get("notes"):
        out["notes"] = res["notes"][:10]
    if plan.tests and applied.get("tests_added"):
        out["hint"] = "tests created but not run: call nw_run to compute their results"
    return out


def listing(app: "App") -> dict[str, Any]:
    res, info, note = app.bridge.call("sets.list")
    tests, _info, _n = app.bridge.call("clash.tests")
    out = {"document": (info.get("doc") or {}).get("title"), "sets": res.get("sets", []),
           "tests": [{"name": t["name"], "kind": t.get("kind"), "status": t.get("status"), "count": t.get("count")} for t in tests]}
    if note:
        out["note"] = note
    return out


def properties(app: "App") -> dict[str, Any]:
    res, info, note = app.bridge.call("props.sample")
    if note:
        res["note"] = note
    return res
