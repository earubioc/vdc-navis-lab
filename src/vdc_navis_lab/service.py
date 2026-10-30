"""Application logic behind the MCP tools. Pure Python: testable without an MCP client."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import exports, ingest, texts, views
from .bridge import Bridge, BridgeError
from .bridge.protocol import INVALID_PARAMS, NO_DOCUMENT, NOT_FOUND, STALE_DOCUMENT
from .engine import AnalysisResult, analyze
from .engine.diff import compare, snapshot_of
from .engine.plan import hotspots, matrix, work_packages
from .engine.pipeline import level_label
from .engine.tagging import Tagger
from .model import ClashSet
from .paths import PathError, home, output_roots, resolve_output
from .profile import PRIORITIES, Profile, ProfileError

PLAN_TTL = 30 * 60
MAX_PLAN_ISSUES = 500
MAX_PLAN_CLASHES = 5000
SETTABLE_STATUS = ("active", "reviewed", "approved", "resolved")
QUERY_OPS = ("eq", "contains", "in")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,60}$")


class ToolFault(Exception):
    def __init__(self, code: str, message: str, hint: str = "", data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.hint, self.data = code, message, hint, data

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error": self.code, "detail": self.message}
        if self.hint:
            out["hint"] = self.hint
        if self.data is not None:
            out["data"] = self.data
        return out


@dataclass(slots=True)
class Plan:
    id: str
    analysis_id: str
    instance_id: str
    fingerprint: str
    revision: str
    created: float
    groups: list[dict[str, Any]]
    statuses: list[dict[str, Any]]
    viewpoints: list[dict[str, Any]]
    preview: dict[str, Any]
    executed: bool = False


@dataclass
class App:
    bridge: Bridge = field(default_factory=Bridge)
    profile: Profile = field(default_factory=Profile.default)
    result: AnalysisResult | None = None
    analysis_instance: str = ""
    seen_revision: str = ""
    pending_analysis: dict[str, Any] = field(default_factory=dict)
    plans: dict[str, Plan] = field(default_factory=dict)
    pending_save: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    @property
    def read_only(self) -> bool:
        return os.environ.get("VDC_NAVIS_LAB_READ_ONLY", "").lower() in ("1", "true", "yes")

    def _refuse_if_read_only(self) -> None:
        if self.read_only:
            raise ToolFault("read_only", "VDC_NAVIS_LAB_READ_ONLY is set: this server will not modify the document",
                            "unset it in the server environment to allow writes")

    def _lang(self, lang: str | None) -> str:
        if lang and lang not in ("es", "en"):
            raise ToolFault(INVALID_PARAMS, "lang must be 'es' or 'en'")
        return lang or self.profile.lang

    def _require_result(self) -> AnalysisResult:
        if self.result is None:
            raise ToolFault("no_analysis", "there is no analysis yet",
                            "run nw_analyze (live) or nw_analyze(path=...) for an exported file")
        return self.result

    def _set_result(self, result: AnalysisResult, instance: str = "", revision: str = "") -> None:
        self.result = result
        self.analysis_instance = instance
        self.seen_revision = revision
        self.plans.clear()

    # ------------------------------------------------------------ nw_status
    def status(self) -> dict[str, Any]:
        found, dead = self.bridge.instances()
        instances = [{"instance_id": i["instance_id"], "product": i.get("product"), "version": i.get("version"),
                      "document": (i.get("doc") or {}).get("title"), "open": (i.get("doc") or {}).get("open"),
                      "fingerprint": (i.get("doc") or {}).get("fingerprint")} for i in found]
        out: dict[str, Any] = {
            "server": {"version": _version(), "read_only": self.read_only},
            "bridge": {"instances": instances, "unreachable": dead, "selected": self.bridge.pinned_id or None,
                       "connected": bool(found)},
            "profile": self.profile.summary(),
            "outputs": {"folders": [str(r) for r in output_roots()]},
            "plans_pending": sum(1 for p in self.plans.values() if not p.executed),
        }
        if not found:
            out["bridge"]["hint"] = ("no Navisworks add-in answered; offline analysis of exported files still works "
                                     "(nw_analyze with path=...)")
        else:
            out["tests"] = self._live_tests()
        r = self.result
        if r is None:
            out["analysis"] = {"present": False}
        else:
            stale: bool | None = None
            reasons: list[str] = []
            if self.analysis_instance:
                live = next((i for i in found if i["instance_id"] == self.analysis_instance), None)
                if live is None:
                    stale = None
                else:
                    doc = live.get("doc") or {}
                    stale = (doc.get("fingerprint") != r.document.get("fingerprint")
                             or str(doc.get("revision", "")) != self.seen_revision)
                    if stale:
                        reasons.append("the document changed since the analysis")
            if r.profile_hash != self.profile.checksum:
                reasons.append("the profile changed since the analysis")
            out["analysis"] = {"present": True, "analysis_id": r.analysis_id, "source": r.source,
                               "issues": len(r.issues), "age_s": round(time.time() - r.created),
                               "stale": stale, "reasons": reasons}
        if self.pending_analysis:
            out["extraction_job"] = {"job_id": self.pending_analysis["job_id"]}
        return out

    def _live_tests(self) -> dict[str, Any]:
        """Clash tests of the instance a read would use. Best effort: status must never fail."""
        try:
            ep, info, _ = self.bridge.resolve()
            tests = self.bridge.call_at(ep, "clash.tests")
        except BridgeError as exc:
            return {"available": False, "reason": exc.code, "detail": str(exc)}
        never = [t["name"] for t in tests if t.get("status") == "new"]
        return {"available": True, "instance_id": info["instance_id"], "count": len(tests), "never_run": never,
                "items": [{k: t.get(k) for k in ("name", "kind", "status", "count")} for t in tests]}

    # ------------------------------------------------------------ nw_connect
    def connect(self, action: str, target: str) -> dict[str, Any]:
        if action == "list":
            found, dead = self.bridge.instances()
            return {"instances": [{"instance_id": i["instance_id"], "document": (i.get("doc") or {}).get("title"),
                                   "version": i.get("version"), "endpoint": i["endpoint"]} for i in found],
                    "unreachable": dead, "selected": self.bridge.pinned_id or None}
        if action == "select":
            if not target:
                raise ToolFault(INVALID_PARAMS, "target is required to select")
            info = self.bridge.select(target)
            self.pending_analysis = {}
            return {"selected": info["instance_id"], "document": (info.get("doc") or {}).get("title")}
        if action == "release":
            self.bridge.release()
            return {"selected": None}
        raise ToolFault(INVALID_PARAMS, "action must be list, select or release")

    # ------------------------------------------------------------ nw_job
    def job(self, action: str, job_id: str) -> dict[str, Any]:
        ep, _, note = self.bridge.resolve(for_write=(action == "cancel"))
        if action == "list":
            return {"jobs": self.bridge.call_at(ep, "job.list")}
        if not job_id:
            raise ToolFault(INVALID_PARAMS, "job_id is required")
        if action == "status":
            return self.bridge.call_at(ep, "job.status", {"job_id": job_id})
        if action == "cancel":
            self._refuse_if_read_only()
            if self.pending_analysis.get("job_id") == job_id:
                self.pending_analysis = {}
            return self.bridge.call_at(ep, "job.cancel", {"job_id": job_id})
        raise ToolFault(INVALID_PARAMS, "action must be status, cancel or list")

    # ------------------------------------------------------------ nw_profile
    def profile_action(self, action: str, path: str, mapping: dict[str, str] | None) -> dict[str, Any]:
        refreshed = False
        if action == "show":
            return self.profile.summary() | {"expected_pairs": self.profile.raw.get("expected_pairs", [])}
        if action == "validate":
            try:
                Profile.load(path or None)
            except ProfileError as exc:
                return {"valid": False, "problems": str(exc).split("; ")}
            return {"valid": True}
        if action in ("load", "reset"):
            try:
                new = Profile.load(path if action == "load" else None)
            except ProfileError as exc:
                raise ToolFault("invalid_profile", str(exc)) from None
            new.overrides = dict(self.profile.overrides)
            self.profile = new
            refreshed = self._reanalyze()
        elif action == "assign":
            if not mapping:
                raise ToolFault(INVALID_PARAMS, "mapping {file name: discipline code} is required")
            for name, code in mapping.items():
                if code not in self.profile.disciplines:
                    raise ToolFault(INVALID_PARAMS, f"unknown discipline {code!r}",
                                    hint=f"known: {', '.join(self.profile.disciplines)}")
                self.profile.overrides[str(name)] = code
            refreshed = self._reanalyze()
        else:
            raise ToolFault(INVALID_PARAMS, "action must be show, load, validate, reset or assign")
        return self.profile.summary() | {"analysis_refreshed": refreshed}

    def _reanalyze(self) -> bool:
        """The raw clash data is still in memory, so a profile change re-ranks instantly."""
        if self.result is None:
            return False
        self.result = analyze(self.result.clashset, self.profile, self.result.lang)
        self.plans.clear()
        return True

    # ------------------------------------------------------------ nw_model / nw_query
    def model(self) -> dict[str, Any]:
        census, info, note = self.bridge.call("model.census")
        tagger = Tagger(self.profile)
        models = []
        for m in census["models"]:
            cats = m.get("categories", {})
            total = sum(cats.values()) or 1
            share: dict[str, float] = {}
            for cat, n in cats.items():
                d = tagger.discipline_of(cat, "")
                share[d] = share.get(d, 0) + n / total
            by_file = tagger.discipline_of_file(m["name"])
            by_cat = max(share, key=share.get) if share else "OTHER"
            proposed = by_file or by_cat
            models.append({
                "name": m["name"], "elements": m.get("elements", 0), "main_categories": dict(list(cats.items())[:5]),
                "by_file_name": by_file or None, "by_categories": {k: round(v, 2) for k, v in sorted(share.items(), key=lambda kv: -kv[1])[:3]},
                "proposed": proposed, "agree": (not by_file) or by_file == by_cat,
            })
        out = {"document": (info.get("doc") or {}).get("title"), "units": census.get("units", "m"), "models": models}
        if note:
            out["note"] = note
        return out

    def query(self, where: list[dict[str, Any]] | None, group_by: str, limit: int) -> dict[str, Any]:
        criteria = []
        for c in where or []:
            if not isinstance(c, dict) or "field" not in c or "value" not in c or c.get("op", "eq") not in QUERY_OPS:
                raise ToolFault(INVALID_PARAMS, "each condition needs field, value and op in eq|contains|in")
            criteria.append({"field": str(c["field"]), "op": c.get("op", "eq"), "value": c["value"]})
        if len(criteria) > 10:
            raise ToolFault(INVALID_PARAMS, "at most 10 conditions")
        limit = max(1, min(int(limit), 200))
        res, info, note = self.bridge.call("elements.query", {"criteria": criteria, "group_by": group_by, "limit": limit})
        if group_by == "level" and res.get("groups"):
            merged: dict[str, int] = {}
            for g in res["groups"]:
                key = level_label(g["key"]) or g["key"]
                merged[key] = merged.get(key, 0) + g["count"]
            res["groups"] = [{"key": k, "count": v} for k, v in sorted(merged.items(), key=lambda kv: -kv[1])]
        if note:
            res["note"] = note
        return res

    # ------------------------------------------------------------ nw_run
    def run(self, tests: list[str] | None, max_wait_s: float) -> dict[str, Any]:
        self._refuse_if_read_only()
        ep, info, note = self.bridge.resolve(for_write=True)
        started = self.bridge.call_at(ep, "clash.run", {"tests": tests or None})
        status = self.bridge.wait_job(ep, started["job_id"], min(max(max_wait_s, 0), 50))
        return {"job_id": started["job_id"], "state": status["state"], "progress": status.get("progress"),
                "hint": None if status["state"] == "completed" else "poll with nw_job(action='status', job_id=...)"}

    # ------------------------------------------------------------ nw_analyze
    def analyze(self, path: str, tests: list[str] | None, top: int, max_wait_s: float, job_id: str,
                lang: str | None) -> dict[str, Any]:
        lang = self._lang(lang)
        top = max(1, min(int(top), 100))
        if path:
            cs = _load_file(path)
            self._set_result(analyze(cs, self.profile, lang))
            return views.summary(self.result, self.profile, top, lang)

        if job_id or self.pending_analysis:
            pend = self.pending_analysis
            if job_id and pend.get("job_id") != job_id:
                raise ToolFault(NOT_FOUND, f"the analysis job in progress is {pend.get('job_id') or 'none'}, not {job_id}")
            ep_text, info = pend["endpoint"], pend["info"]
        else:
            ep, info, note = self.bridge.resolve()
            ep_text = str(ep)
            started = self.bridge.call_at(ep, "clash.export", {"tests": tests or [], "limit": 0})
            self.pending_analysis = {"job_id": started["job_id"], "endpoint": ep_text, "info": info}

        from .bridge.transport import Endpoint
        ep = Endpoint.parse(ep_text)
        jid = self.pending_analysis["job_id"]
        status = self.bridge.wait_job(ep, jid, min(max(max_wait_s, 0), 50))
        if status["state"] in ("running", "queued", "verifying"):
            return {"state": status["state"], "job_id": jid, "progress": status.get("progress"),
                    "hint": f"still extracting; call nw_analyze(job_id='{jid}') to collect, or nw_job to watch it"}
        self.pending_analysis = {}
        if status["state"] != "completed":
            raise ToolFault("export_failed", status.get("error") or f"export job {status['state']}")
        data = self.bridge.call_at(ep, "job.result", {"job_id": jid})
        try:
            cs = ClashSet.from_dict(data)
        except (KeyError, ValueError, TypeError) as exc:
            raise ToolFault("bad_export", f"the add-in returned an export this server cannot read ({type(exc).__name__})") from None
        live = self.bridge.call_at(ep, "hello")
        cs.document = {**cs.document, **{k: v for k, v in (live.get("doc") or {}).items() if k in ("title", "fingerprint")}}
        cs.sleeves_modeled = self._count_sleeves(ep)
        self._set_result(analyze(cs, self.profile, lang), live["instance_id"], str((live.get("doc") or {}).get("revision", "")))
        return views.summary(self.result, self.profile, top, lang)

    def _count_sleeves(self, ep: Any) -> int | None:
        """Elements in the open model that look like modeled sleeves or openings (by name). None when it could not
        be checked, so a failure never claims 'there are none'."""
        patterns = [str(x) for x in self.profile.section("score", "sleeve").get("element_name_patterns", [])]
        if not patterns:
            return None
        total = 0
        try:
            for pat in patterns:
                res = self.bridge.call_at(ep, "elements.query", {
                    "criteria": [{"field": "name", "op": "contains", "value": pat}], "group_by": "", "limit": 1})
                total += int(res.get("count", 0))
        except Exception:
            return None
        return total

    # ------------------------------------------------------------ nw_issues / nw_issue
    def issues(self, priority: str, discipline: str, level: str, cause: str, responsible: str, sort: str,
               limit: int, offset: int, lang: str | None) -> dict[str, Any]:
        r = self._require_result()
        lang = self._lang(lang)
        if priority and priority not in PRIORITIES:
            raise ToolFault(INVALID_PARAMS, f"priority must be one of {', '.join(PRIORITIES)}")
        if sort not in ("rank", "score", "clashes", "level"):
            raise ToolFault(INVALID_PARAMS, "sort must be rank, score, clashes or level")
        items = r.issues
        if priority:
            items = [i for i in items if i.priority == priority]
        if discipline:
            items = [i for i in items if discipline.upper() in i.pair]
        if responsible:
            items = [i for i in items if i.responsible == responsible.upper()]
        if level:
            items = [i for i in items if i.level.lower() == level.lower()]
        if cause:
            items = [i for i in items if cause in i.cause_ids]
        keys = {"rank": lambda i: i.rank_key, "score": lambda i: (-i.score, i.id),
                "clashes": lambda i: (-len(i.clashes), i.id), "level": lambda i: (i.level, i.rank_key)}
        items = sorted(items, key=keys[sort])
        limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
        return {"total": len(items), "offset": offset,
                "items": [views.brief(i, self.profile, lang) for i in items[offset:offset + limit]]}

    def issue(self, issue_id: str, lang: str | None) -> dict[str, Any]:
        r = self._require_result()
        issue = r.issue(issue_id)
        if issue is None:
            raise ToolFault(NOT_FOUND, f"no issue {issue_id!r} in the current analysis",
                            "ids come from nw_analyze or nw_issues and change if the analysis is rebuilt")
        return views.detail(issue, r, self.profile, self._lang(lang))

    # ------------------------------------------------------------ nw_report
    def report(self, kind: str, path: str, overwrite: bool, limit: int, lang: str | None,
               issue: str = "") -> dict[str, Any]:
        r = dataclasses.replace(self._require_result(), lang=self._lang(lang))
        lang = r.lang
        limit = max(1, min(int(limit), 500))
        if kind == "image":
            return self._issue_image(r, issue, path, overwrite)
        if kind == "summary":
            return views.summary(r, self.profile, min(limit, 100), lang)
        if kind == "matrix":
            return {"matrix": matrix(r), "coverage": views.coverage_view(r, lang)}
        if kind == "hotspots":
            return {"hotspots": hotspots(r, limit=min(limit, 20))}
        if kind == "plan":
            return {"packages": work_packages(r, self.profile)[:limit]}
        if kind == "markdown" and not path:
            return {"markdown": exports.to_markdown(r, self.profile, min(limit, 50))}
        ext = {"markdown": "md", "csv": "csv", "bcf": "bcf", "json": "json", "pdf": "pdf"}.get(kind)
        if ext is None:
            raise ToolFault(INVALID_PARAMS, "kind must be summary, matrix, hotspots, plan, markdown, csv, bcf, json, pdf or image")
        target = _output(path, f"vdc-navis-lab-{r.analysis_id}.{ext}", overwrite)
        if kind == "markdown":
            data = exports.to_markdown(r, self.profile, min(limit, 500)).encode("utf-8")
        elif kind == "csv":
            data = exports.to_csv(r, self.profile)
        elif kind == "bcf":
            data = exports.to_bcf(r, self.profile, limit)
        elif kind == "pdf":
            data = exports.to_pdf(r, self.profile, limit if limit != 25 else 40)
        else:
            data = json.dumps(r.clashset.to_dict(), ensure_ascii=False).encode("utf-8")
        target.write_bytes(data)
        return {"path": str(target), "bytes": len(data), "kind": kind, "issues": len(r.issues)}

    def _issue_image(self, r: AnalysisResult, issue: str, path: str, overwrite: bool) -> dict[str, Any]:
        """A PNG framed on one issue's representative clash. Needs the live document the analysis came
        from: it is a rendering query, not data read from the cached analysis, so it never writes to
        Navisworks and does not need a plan (D-006 is about document mutation, not file output)."""
        if not issue:
            raise ToolFault(INVALID_PARAMS, "issue is required for kind='image'")
        iss = r.issue(issue)
        if iss is None:
            raise ToolFault(NOT_FOUND, f"unknown issue {issue!r}")
        if r.source not in ("navisworks", "simulator"):
            raise ToolFault(INVALID_PARAMS, "kind='image' needs a live Navisworks analysis, not a file")
        ep, info, note = self.bridge.resolve()
        target = _output(path, f"vdc-navis-lab-{iss.id}.png", overwrite)
        res = self.bridge.call_at(ep, "clash.image", {"clash_id": iss.rep.id, "path": str(target)})
        out = {"path": res.get("path", str(target)), "issue": iss.id, "clash_id": iss.rep.id}
        if note:
            out["note"] = note
        return out

    # ------------------------------------------------------------ nw_view
    MAX_VIEW_CLASHES = 3000

    def view(self, action: str, issues: Any, ghost: bool, clear_selection: bool = False) -> dict[str, Any]:
        """Selection, framing and temporary colours in the open Navisworks view. View state only: nothing is written
        to the document, so it needs no plan; reset (or closing the document) restores the appearance."""
        if action not in ("select", "color", "reset"):
            raise ToolFault(INVALID_PARAMS, "action must be select, color or reset")
        if action == "reset":
            ep, _, note = self.bridge.resolve()
            res = self.bridge.call_at(ep, "view.reset", {"clear_selection": bool(clear_selection)})
            return {**res, **({"note": note} if note else {})}
        r = self._require_result()
        if r.source not in ("navisworks", "simulator"):
            raise ToolFault(INVALID_PARAMS, "nw_view needs an analysis of the open document, not of a file",
                            "run nw_analyze without path while Navisworks is open")
        ep, info, note = self.bridge.resolve()
        fingerprint = str((info.get("doc") or {}).get("fingerprint", ""))
        if fingerprint != str(r.document.get("fingerprint")):
            raise ToolFault(STALE_DOCUMENT, "the open document is not the one this analysis was made for",
                            "re-run nw_analyze on the open document")
        if action == "select":
            if not issues or issues == "all":
                raise ToolFault(INVALID_PARAMS, "issues is required: an id, a list of ids, 'top:N' or a filter")
            chosen = self._select([issues] if isinstance(issues, str) and not issues.startswith("top:") else issues, r)
            if not chosen:
                raise ToolFault(NOT_FOUND, "no issue matches that selector")
            guids = [c.id for i in chosen for c in i.clashes]
            if len(guids) > self.MAX_VIEW_CLASHES:
                raise ToolFault("too_many", f"that selection holds {len(guids)} clashes; the limit is {self.MAX_VIEW_CLASHES}")
            res = self.bridge.call_at(ep, "view.select", {"if_fingerprint": fingerprint, "guids": guids,
                                                          "focus": chosen[0].rep.id, "ghost": bool(ghost)})
            out = {**res, "issues": [i.id for i in chosen][:20], "framed_on": chosen[0].id}
        else:
            chosen = self._select(issues if issues else "all", r)
            if not chosen:
                raise ToolFault(NOT_FOUND, "no issue matches that selector")
            total = sum(len(i.clashes) for i in chosen)
            if total > self.MAX_VIEW_CLASHES * 5:
                raise ToolFault("too_many", f"that selection holds {total} clashes; narrow it with a filter")
            groups = []
            for band in reversed(PRIORITIES):  # low first, so the most severe colour wins on shared elements
                guids = [c.id for i in chosen if i.priority == band for c in i.clashes]
                if guids:
                    groups.append({"color": exports.PRIORITY_COLORS[band], "guids": guids, "priority": band})
            res = self.bridge.call_at(ep, "view.color", {"if_fingerprint": fingerprint, "ghost": bool(ghost),
                                                         "groups": [{"color": g["color"], "guids": g["guids"]} for g in groups]})
            out = {**res, "legend": {g["priority"]: {"color": g["color"], "clashes": len(g["guids"])} for g in groups},
                   "issues": len(chosen)}
        out["hint"] = "temporary: nw_view(action='reset') restores the original appearance"
        if note:
            out["note"] = note
        return out

    # ------------------------------------------------------------ nw_apply
    def apply(self, ops: list[dict[str, Any]] | None, plan_id: str, dry_run: bool) -> dict[str, Any]:
        if plan_id:
            return self._execute_plan(plan_id)
        if not dry_run:
            raise ToolFault(INVALID_PARAMS, "to execute, pass the plan_id returned by a dry run",
                            "call nw_apply(ops=[...]) first; execution never takes raw ops")
        return self._make_plan(ops or [])

    def _select(self, selector: Any, r: AnalysisResult) -> list:
        if selector == "all":
            return list(r.issues)
        if isinstance(selector, str) and selector.startswith("top:"):
            try:
                return r.issues[: max(1, int(selector[4:]))]
            except ValueError:
                raise ToolFault(INVALID_PARAMS, "selector 'top:N' needs an integer") from None
        if isinstance(selector, list):
            found = [r.issue(str(x)) for x in selector]
            missing = [str(x) for x, f in zip(selector, found) if f is None]
            if missing:
                raise ToolFault(NOT_FOUND, f"unknown issues: {missing[:5]}")
            return found
        if isinstance(selector, dict):
            items = r.issues
            if selector.get("priority"):
                items = [i for i in items if i.priority == selector["priority"]]
            if selector.get("discipline"):
                items = [i for i in items if selector["discipline"].upper() in i.pair]
            if selector.get("level"):
                items = [i for i in items if i.level.lower() == str(selector["level"]).lower()]
            return items[: int(selector.get("limit", MAX_PLAN_ISSUES))]
        raise ToolFault(INVALID_PARAMS, "issues must be a list of ids, 'top:N', or a filter object")

    def _make_plan(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        r = self._require_result()
        if not self.analysis_instance:
            raise ToolFault("needs_live_analysis", "writes need an analysis of the open document, not of a file",
                            "run nw_analyze without path while Navisworks is open")
        if not ops:
            raise ToolFault(INVALID_PARAMS, "ops is empty",
                            "e.g. [{'op':'group','issues':'top:20'},{'op':'status','issues':{'priority':'low'},'status':'reviewed'}]")
        ep, info, _ = self.bridge.resolve(for_write=True)
        if info.get("instance_id") != self.analysis_instance:
            raise ToolFault("target_changed", "the selected instance is not the one this analysis came from",
                            "re-run nw_analyze on the instance you want to write to")
        doc = info.get("doc") or {}
        if doc.get("fingerprint") != r.document.get("fingerprint") or str(doc.get("revision", "")) != self.seen_revision:
            raise ToolFault("outdated_analysis", "the document changed since the analysis; its issue ids may no longer match",
                            "re-run nw_analyze before planning writes")

        groups: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        viewpoints: list[dict[str, Any]] = []
        preview_ops = []
        issues_seen: set[str] = set()
        clashes_total = 0
        for op in ops:
            kind = op.get("op") if isinstance(op, dict) else None
            members = self._select(op.get("issues"), r) if kind in ("group", "status", "viewpoint") else None
            if kind == "group":
                names = []
                for i in members:
                    name = _group_name(i, self.profile, r.lang)
                    groups.append({"name": name, "guids": [c.id for c in i.clashes]})
                    names.append(name)
                    issues_seen.add(i.id)
                    clashes_total += len(i.clashes)
                preview_ops.append({"op": "group", "issues": len(members), "sample": names[:4]})
            elif kind == "status":
                st = str(op.get("status", ""))
                if st not in SETTABLE_STATUS:
                    raise ToolFault(INVALID_PARAMS, f"status must be one of {', '.join(SETTABLE_STATUS)}")
                guids = [c.id for i in members for c in i.clashes]
                statuses.append({"status": st, "guids": guids})
                issues_seen.update(i.id for i in members)
                clashes_total += len(guids)
                crit = sum(1 for i in members if i.priority == "critical")
                entry = {"op": "status", "status": st, "issues": len(members), "clashes": len(guids)}
                if st in ("approved", "resolved") and crit:
                    entry["warning"] = f"{crit} critical issue(s) would be closed"
                preview_ops.append(entry)
            elif kind == "viewpoint":
                names = []
                for i in members:
                    name = _group_name(i, self.profile, r.lang)
                    viewpoints.append({"guid": i.rep.id, "name": name})
                    names.append(name)
                    issues_seen.add(i.id)
                preview_ops.append({"op": "viewpoint", "issues": len(members), "sample": names[:4]})
            else:
                raise ToolFault(INVALID_PARAMS, "each op needs op='group', op='status' or op='viewpoint'")
        if len(issues_seen) > MAX_PLAN_ISSUES or clashes_total > MAX_PLAN_CLASHES:
            raise ToolFault("plan_too_large", f"limit is {MAX_PLAN_ISSUES} issues and {MAX_PLAN_CLASHES} clashes per plan",
                            "split the work into several plans")
        plan = Plan(id=f"P-{uuid.uuid4().hex[:8]}", analysis_id=r.analysis_id, instance_id=self.analysis_instance,
                    fingerprint=str(doc.get("fingerprint")), revision=self.seen_revision, created=time.time(),
                    groups=groups, statuses=statuses, viewpoints=viewpoints,
                    preview={"ops": preview_ops, "issues": len(issues_seen), "clashes": clashes_total})
        self.plans[plan.id] = plan
        return {"plan_id": plan.id, "dry_run": True, "document": doc.get("title"), "expires_in_s": PLAN_TTL,
                **plan.preview, "next": f"nw_apply(plan_id='{plan.id}') executes this plan; nothing was changed yet"}

    def _execute_plan(self, plan_id: str) -> dict[str, Any]:
        self._refuse_if_read_only()
        plan = self.plans.get(plan_id)
        if plan is None:
            raise ToolFault(NOT_FOUND, f"unknown plan {plan_id!r}", "plans are rejected when the analysis is rebuilt; plan again")
        if plan.executed:
            raise ToolFault("plan_executed", "this plan was already executed", "make a new plan to apply more changes")
        if time.time() - plan.created > PLAN_TTL:
            raise ToolFault("plan_expired", "the plan is older than 30 minutes", "plan again")
        r = self._require_result()
        if r.analysis_id != plan.analysis_id:
            raise ToolFault("outdated_analysis", "the analysis was rebuilt after this plan was made", "plan again")
        ep, info, _ = self.bridge.resolve(for_write=True)
        if info.get("instance_id") != plan.instance_id:
            raise ToolFault("target_changed", "the selected instance is not the one the plan was made for")
        doc = info.get("doc") or {}
        if doc.get("fingerprint") != plan.fingerprint or str(doc.get("revision", "")) != plan.revision:
            raise ToolFault(STALE_DOCUMENT, "the document changed since the plan was made", "plan again")
        res = self.bridge.call_at(ep, "clash.apply", {
            "if_fingerprint": plan.fingerprint, "dedupe_key": plan.id,
            "groups": plan.groups, "statuses": plan.statuses, "viewpoints": plan.viewpoints})
        plan.executed = True
        verified, applied = res.get("verified", {}), res.get("applied", {})
        want_groups, want_status = len(plan.groups), sum(len(s["guids"]) for s in plan.statuses)
        want_viewpoints = len(plan.viewpoints)
        ok = (verified.get("groups", 0) == want_groups and verified.get("statuses", 0) == want_status
              and verified.get("viewpoints", 0) == want_viewpoints and not res.get("missing"))
        state = "completed" if ok else (
            "failed" if not (verified.get("groups") or verified.get("statuses") or verified.get("viewpoints")) else "partial")
        live = self.bridge.call_at(ep, "hello")
        self.seen_revision = str((live.get("doc") or {}).get("revision", ""))  # our own change is not staleness
        out = {"state": state,
               "requested": {"groups": want_groups, "statuses": want_status, "viewpoints": want_viewpoints},
               "applied": applied, "verified": verified, "missing": res.get("missing", [])[:10]}
        if plan.statuses:
            out["hint"] = "statuses changed in the document: run nw_analyze again to refresh the ranking"
        return out

    # ------------------------------------------------------------ nw_snapshot
    def snapshot(self, action: str, name: str, against: str) -> dict[str, Any]:
        folder = home() / "snapshots"
        folder.mkdir(parents=True, exist_ok=True)

        def path_of(n: str) -> Path:
            if not _SAFE_NAME.match(n):
                raise ToolFault(INVALID_PARAMS, "snapshot names use letters, digits, '.', '_' and '-' (max 60)")
            return folder / f"{n}.json"

        if action == "list":
            items = []
            for f in sorted(folder.glob("*.json")):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    items.append({"name": f.stem, "created": datetime.fromtimestamp(d["created"]).isoformat(timespec="seconds"),
                                  "issues": len(d["issues"]), "source": d.get("source")})
                except (OSError, ValueError, KeyError):
                    continue
            return {"folder": str(folder), "snapshots": items}
        if action == "save":
            r = self._require_result()
            n = name or f"{datetime.now():%Y%m%d-%H%M%S}-{r.analysis_id}"
            target = path_of(n)
            if target.exists():
                raise ToolFault("exists", f"snapshot {n!r} already exists", "choose another name")
            target.write_text(json.dumps(snapshot_of(r), ensure_ascii=False), encoding="utf-8")
            return {"saved": n, "issues": len(r.issues)}
        if action == "compare":
            if not against:
                raise ToolFault(INVALID_PARAMS, "against (a saved snapshot name) is required")
            ap = path_of(against)
            if not ap.exists():
                raise ToolFault(NOT_FOUND, f"no snapshot {against!r}")
            before = json.loads(ap.read_text(encoding="utf-8"))
            if name:
                bp = path_of(name)
                if not bp.exists():
                    raise ToolFault(NOT_FOUND, f"no snapshot {name!r}")
                after = json.loads(bp.read_text(encoding="utf-8"))
            else:
                after = snapshot_of(self._require_result())
            return compare(before, after)
        raise ToolFault(INVALID_PARAMS, "action must be save, list or compare")

    # ------------------------------------------------------------ nw_document
    def document(self, action: str, path: str, confirm: bool, overwrite: bool) -> dict[str, Any]:
        if action not in ("save", "save_as"):
            raise ToolFault(INVALID_PARAMS, "action must be save or save_as")
        ep, info, _ = self.bridge.resolve(for_write=True)
        doc = info.get("doc") or {}
        if not doc.get("open"):
            raise ToolFault(NO_DOCUMENT, "no document is open in that instance")
        target = None
        if action == "save_as":
            if not path:
                raise ToolFault(INVALID_PARAMS, "path is required for save_as")
            try:
                target = str(resolve_output(path, path, overwrite))
            except PathError as exc:
                raise ToolFault("path_refused", str(exc)) from None
        key = (info["instance_id"], doc.get("fingerprint"), action, target)
        if not confirm:
            self.pending_save = {"key": key, "at": time.time()}
            return {"dry_run": True, "action": action, "document": doc.get("title"), "target": target,
                    "next": "call again with confirm=true to perform it"}
        self._refuse_if_read_only()
        if self.pending_save.get("key") != key or time.time() - self.pending_save.get("at", 0) > PLAN_TTL:
            raise ToolFault("not_previewed", "confirm only works right after a preview of the same action",
                            "call without confirm first")
        self.pending_save = {}
        res = self.bridge.call_at(ep, "doc.save", {"if_fingerprint": doc.get("fingerprint"), "path": target})
        return {"state": "completed" if res.get("verified") else "partial", **res}


# ------------------------------------------------------------ module helpers
def _version() -> str:
    from . import __version__
    return __version__


def _load_file(path: str) -> ClashSet:
    try:
        return ingest.load(path)
    except ingest.IngestError as exc:
        raise ToolFault("cannot_read_file", str(exc)) from None


def _output(path: str, default: str, overwrite: bool) -> Path:
    try:
        return resolve_output(path, default, overwrite)
    except PathError as exc:
        raise ToolFault("path_refused", str(exc), hint=f"allowed folders: {[str(r) for r in output_roots()]}") from None


def _group_name(issue, profile: Profile, lang: str) -> str:
    where = issue.level or ("sin nivel" if lang == "es" else "no level")
    a, b = issue.pair
    name = f"[{texts.PRIORITY[lang][issue.priority]}] {a}-{b} {where} {issue.id}"
    return name[:120]
