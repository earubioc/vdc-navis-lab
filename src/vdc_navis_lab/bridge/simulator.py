"""A stand-in for the Navisworks add-in, speaking the real protocol over loopback TCP.

It serves the synthetic tower from vdc_navis_lab.sample, keeps clash groups and statuses in memory, and
re-reads them to report what was *verified*. It exists so the server, the tests and demos run on
any machine; it is not a model of Navisworks' behaviour beyond the contract in docs/PROTOCOL.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socketserver
import threading
import time
import uuid
from collections import Counter
from typing import Any

from ..model import SCHEMA, ClashSet
from ..paths import home
from ..sample.generator import build
from .protocol import (API_VERSION, BUSY, INVALID_PARAMS, NOT_FOUND, STALE_DOCUMENT, UNSUPPORTED, encode_error,
                       encode_result)
from .transport import registry_dir

METHODS = ["hello", "doc.info", "model.census", "elements.query", "clash.tests", "clash.run", "clash.export", "clash.page", "clash.release",
           "clash.apply", "clash.image", "view.select", "view.color", "view.reset", "sets.list", "props.sample", "setup.apply", "doc.save", "job.status", "job.result", "job.cancel", "job.list"]

# A 1x1 transparent PNG: the simulator cannot render, so this stands in for whatever real image
# Navisworks would have produced, just to exercise the file-writing path end to end.
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+A8AAQUAAYayDIYAAAAASUVORK5CYII=")


class Fault(Exception):
    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


class Simulator:
    def __init__(self, seed: int = 7, port: int = 0, job_delay: float = 0.15, clashset: ClashSet | None = None,
                 page_memory_stop_after: int = 0, legacy: bool = False, page_delay: float = 0.0) -> None:
        """`clashset` replaces the synthetic tower (for scale tests); `page_memory_stop_after` makes clash.page report its
        memory guard after that many described results; `legacy` answers like an add-in without clash.page."""
        if clashset is not None:
            self.clashset, self.elements = clashset, []
            self.clashset.document = {**(self.clashset.document or {}), "title": self.clashset.document.get("title", "simulated-federation")}
        else:
            self.clashset, self.elements = build(seed)
        self.legacy = legacy
        self.page_delay = page_delay
        self.page_memory_stop_after = page_memory_stop_after
        self._described = 0
        self._by_test: dict[str, list] = {}
        for c in self.clashset.clashes:
            self._by_test.setdefault(c.test, []).append(c)
        self._page_cache: dict[str, list] = {}
        self.job_delay = job_delay
        self.instance_id = f"sim-{uuid.uuid4().hex[:8]}"
        self.started = time.time()
        self.title = self.clashset.document["title"]
        self.fingerprint = hashlib.sha1(f"{self.title}|{sorted(self.clashset.models)}".encode()).hexdigest()[:16]
        self.groups: dict[str, set[str]] = {}
        self.status: dict[str, str] = {c.id: c.status for c in self.clashset.clashes}
        self.viewpoints: dict[str, str] = {}
        self.selection: list[str] = []
        self.sets: dict[str, set[str]] = {}
        self.setup_sets: dict[str, dict] = {}
        self.setup_tests: dict[str, dict] = {}
        self.colours: dict[str, str] = {}
        self.ghosted = False
        self.jobs: dict[str, dict[str, Any]] = {}
        self.applied: dict[str, dict] = {}
        self.saves = 0
        self.revision = 0
        self._lock = threading.RLock()
        self._port_req = port
        self._server: socketserver.ThreadingTCPServer | None = None
        self._registry_file = None

    # ------------------------------------------------------------ lifecycle
    def start(self, register: bool = False) -> str:
        sim = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                line = self.rfile.readline(64 * 1024 * 1024)
                if not line:
                    return
                self.wfile.write(sim.dispatch(line))

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(("127.0.0.1", self._port_req), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        endpoint = f"tcp://127.0.0.1:{self._server.server_address[1]}"
        self.endpoint = endpoint
        if register:
            self._registry_file = registry_dir() / f"{self.instance_id}.json"
            self._registry_file.write_text(json.dumps({"endpoint": endpoint, "pid": os.getpid()}), encoding="utf-8")
        return endpoint

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._registry_file:
            try:
                self._registry_file.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------ dispatch
    def dispatch(self, line: bytes) -> bytes:
        try:
            req = json.loads(line.decode("utf-8"))
            rid, method, params = req.get("id"), req.get("method", ""), req.get("params") or {}
        except (ValueError, UnicodeDecodeError, AttributeError):
            return encode_error(None, INVALID_PARAMS, "malformed request")
        handler = getattr(self, "m_" + method.replace(".", "_"), None)
        if handler is None:
            return encode_error(rid, UNSUPPORTED, f"unknown method {method!r}", "call hello for the method list")
        try:
            with self._lock:
                return encode_result(rid, handler(params))
        except Fault as f:
            return encode_error(rid, f.code, f.message, f.hint)
        except (KeyError, TypeError, ValueError) as exc:
            return encode_error(rid, INVALID_PARAMS, f"invalid parameters: {type(exc).__name__}")

    def _doc(self) -> dict[str, Any]:
        return {"open": True, "title": self.title, "fingerprint": self.fingerprint, "revision": str(self.revision)}

    # ------------------------------------------------------------ jobs
    def _job(self, kind: str, work) -> str:
        jid = f"job-{uuid.uuid4().hex[:8]}"
        self.jobs[jid] = {"job_id": jid, "kind": kind, "state": "running",
                          "progress": {"kind": "indeterminate", "note": "simulated"}, "result": None, "error": ""}

        def finish() -> None:
            with self._lock:
                job = self.jobs[jid]
                if job["state"] == "cancelled":
                    return
                try:
                    job["result"] = work()
                    job["state"] = "completed"
                    if kind == "clash.run":
                        self.revision += 1
                except Fault as f:
                    job["state"], job["error"] = "failed", f.message

        threading.Timer(self.job_delay, finish).start()
        return jid

    # ------------------------------------------------------------ methods
    def m_hello(self, p: dict) -> dict:
        methods = [m for m in METHODS if not (self.legacy and m in ("clash.page", "clash.release"))]
        return {"product": "navisworks-simulator", "version": "0.1", "addin_version": "simulator", "api": API_VERSION,
                "instance_id": self.instance_id, "started": self.started, "doc": self._doc(), "methods": methods}

    def m_doc_info(self, p: dict) -> dict:
        return {**self._doc(), "models": self.clashset.models, "units": "m", "saves": self.saves}

    def m_model_census(self, p: dict) -> dict:
        models = []
        for name in self.clashset.models:
            els = [e for e in self.elements if e.model == name]
            cats = Counter(e.category for e in els)
            bbox = None
            if els:
                lo = [min(e.bbox[0][i] for e in els) for i in range(3)]
                hi = [max(e.bbox[1][i] for e in els) for i in range(3)]
                bbox = [lo, hi]
            models.append({"name": name, "elements": len(els), "categories": dict(cats.most_common(12)), "bbox": bbox,
                           "units": "Meters"})
        return {"units": "m", "models": models}

    def m_elements_query(self, p: dict) -> dict:
        criteria = p.get("criteria") or []
        group_by = p.get("group_by") or ""
        limit = max(1, min(int(p.get("limit", 20)), 500))

        def value_of(e, field: str) -> str:
            return str(getattr(e, field, "") or e.props.get(field, "")) if field in ("category", "model", "level", "family", "name", "system") \
                else str(e.props.get(field, ""))

        def ok(e) -> bool:
            for c in criteria:
                v, want, op = value_of(e, c["field"]).lower(), str(c["value"]).lower(), c.get("op", "eq")
                if op == "eq" and v != want:
                    return False
                if op == "contains" and want not in v:
                    return False
                if op == "in" and v not in [str(x).lower() for x in c["value"]]:
                    return False
                if op == "contains_any" and not any(str(x).lower() in v for x in c["value"]):
                    return False
            return True

        hits = [e for e in self.elements if ok(e)]
        out: dict[str, Any] = {"count": len(hits)}
        if group_by:
            out["groups"] = [{"key": k, "count": n} for k, n in Counter(value_of(e, group_by) for e in hits).most_common(limit)]
        out["sample"] = [{"id": e.id, "name": e.name, "category": e.category, "model": e.model, "level": e.level}
                         for e in hits[:limit]]
        return out

    def m_clash_tests(self, p: dict) -> list[dict]:
        rows = [{**t.to_dict(), "count": len(self._by_test.get(t.name, ()))} for t in self.clashset.tests]
        rows += [{"name": n, "kind": t["type"], "status": "new", "tolerance": t["tolerance_m"], "count": 0}
                 for n, t in self.setup_tests.items()]
        return rows

    def m_clash_run(self, p: dict) -> dict:
        names = set(p.get("tests") or [t.name for t in self.clashset.tests])
        unknown = names - {t.name for t in self.clashset.tests}
        if unknown:
            raise Fault(NOT_FOUND, f"unknown tests: {sorted(unknown)}")

        def work():
            for t in self.clashset.tests:
                if t.name in names and t.status == "new":
                    t.status = "active"
            return {"ran": sorted(names)}
        return {"job_id": self._job("clash.run", work)}

    def m_clash_page(self, p: dict) -> dict:
        """One slice of one test, open results first, like the add-in. Positions are indexes in that order."""
        if self.legacy:
            raise Fault(UNSUPPORTED, "unknown method 'clash.page'")
        if self.page_delay:
            time.sleep(self.page_delay)
        name, cursor = str(p["test"]), max(0, int(p.get("cursor", 0)))
        limit = max(25, min(3000, int(p.get("limit", 500))))
        closed_left = int(p.get("closed_describe", -1))
        want = str(p.get("if_fingerprint", ""))
        if want and want != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the extraction started on", "start the analysis again")
        if p.get("begin"):
            self._page_cache.clear()
            self._described = 0
        if name not in self._by_test and name not in {t.name for t in self.clashset.tests}:
            raise Fault(NOT_FOUND, "unknown clash test")
        items = self._page_cache.get(name)
        if items is None or cursor == 0:
            raw = self._by_test.get(name, [])
            closed_set = ("approved", "resolved")
            items = [c for c in raw if self.status[c.id] not in closed_set] + [c for c in raw if self.status[c.id] in closed_set]
            self._page_cache = {name: items}
        n_open = sum(1 for c in items if self.status[c.id] not in ("approved", "resolved"))
        out, closed_skipped, closed_described, stop = [], 0, 0, None
        i = cursor
        while i < len(items):
            if len(out) >= limit:
                break
            if self.page_memory_stop_after and self._described >= self.page_memory_stop_after:
                stop = "memory"
                break
            c = items[i]
            st = self.status[c.id]
            closed = st in ("approved", "resolved")
            if closed and closed_left == 0:
                closed_skipped += 1
                i += 1
                continue
            d = c.to_dict()
            d["status"] = st
            out.append(d)
            self._described += 1
            if closed:
                closed_described += 1
                closed_left -= 1 if closed_left > 0 else 0
            i += 1
        t = next((t for t in self.clashset.tests if t.name == name), None)
        return {"test": {"name": name, "kind": t.kind if t else "hard", "status": t.status if t else "new",
                         "tolerance": t.tolerance if t else 0.0, "count": len(items)},
                "clashes": out, "next": i if i < len(items) else None, "total": len(items), "open_total": n_open,
                "closed_total": len(items) - n_open, "skipped": 0, "skipped_open": 0, "closed_skipped": closed_skipped,
                "closed_described": closed_described, "memory_growth_mb": 0, "stop": stop}

    def m_clash_release(self, p: dict) -> dict:
        self._page_cache.clear()
        return {"released": True}

    def m_clash_export(self, p: dict) -> dict:
        names = set(p.get("tests") or [])
        limit = int(p.get("limit", 0))

        def work():
            data = self.clashset.to_dict()
            data["schema"] = SCHEMA
            data["document"] = self._doc()
            data["source"] = "simulator"
            if names:
                data["clashes"] = [c for c in data["clashes"] if c["test"] in names]
            for c in data["clashes"]:
                c["status"] = self.status[c["id"]]
            if limit and len(data["clashes"]) > limit:
                data["clashes"], data["truncated"] = data["clashes"][:limit], True
            return data
        return {"job_id": self._job("clash.export", work)}

    def m_clash_apply(self, p: dict) -> dict:
        if p.get("if_fingerprint") != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the plan was made for",
                        "run nw_status and re-analyze before applying")
        key = str(p.get("dedupe_key") or "")
        if key and key in self.applied:
            return {**self.applied[key], "replayed": True}
        known = {c.id for c in self.clashset.clashes}
        created = reused = status_set = 0
        missing: list[str] = []
        test_of = {c.id: c.test for c in self.clashset.clashes}
        gkey = lambda g: (test_of.get(next((x for x in g["guids"] if x in known), ""), "") + "|" + g["name"])  # a group lives under one test
        for g in p.get("groups") or []:
            guids = [x for x in g["guids"] if x in known]
            missing += [x for x in g["guids"] if x not in known]
            if gkey(g) in self.groups:
                reused += 1
            else:
                created += 1
            self.groups.setdefault(gkey(g), set()).update(guids)
        for s in p.get("statuses") or []:
            for guid in s["guids"]:
                if guid in known:
                    self.status[guid] = s["status"]
                    status_set += 1
                else:
                    missing.append(guid)
        viewpoints_added = 0
        for v in p.get("viewpoints") or []:
            guid = v["guid"]
            if guid in known:
                self.viewpoints[guid] = v["name"]
                viewpoints_added += 1
            else:
                missing.append(guid)
        sets_added = sets_reused = 0
        for st in p.get("sets") or []:
            guids = [x for x in st["guids"] if x in known]
            missing += [x for x in st["guids"] if x not in known]
            if st["name"] in self.sets:
                sets_reused += 1
            else:
                sets_added += 1
                self.sets[st["name"]] = set(guids)
        verified_sets = sum(1 for st in p.get("sets") or []
                            if {x for x in st["guids"] if x in known} <= self.sets.get(st["name"], set()))
        wanted_groups = {gkey(g): {x for x in g["guids"] if x in known} for g in p.get("groups") or []}
        verified_groups = sum(1 for n, ids in wanted_groups.items() if ids <= self.groups.get(n, set()))
        verified_status = sum(1 for s in p.get("statuses") or [] for guid in s["guids"]
                              if guid in known and self.status[guid] == s["status"])
        verified_viewpoints = sum(1 for v in p.get("viewpoints") or []
                                  if v["guid"] in known and self.viewpoints.get(v["guid"]) == v["name"])
        if created or status_set or viewpoints_added or sets_added:
            self.revision += 1
        result = {"applied": {"groups_added": created, "groups_reused": reused, "statuses_set": status_set,
                              "viewpoints_added": viewpoints_added,
                              "sets_added": sets_added, "sets_reused": sets_reused},
                  "verified": {"groups": verified_groups, "statuses": verified_status, "viewpoints": verified_viewpoints,
                               "sets": verified_sets},
                  "missing": sorted(set(missing))}
        if key:
            self.applied[key] = result
        return result

    def m_sets_list(self, p: dict) -> dict:
        rows = [{"name": n, "path": f"VDC Lab/{n}", "kind": "explicit", "items": len(ids)} for n, ids in self.sets.items()]
        for n, st in self.setup_sets.items():
            if "files" in st:
                rows.append({"name": n, "path": f"VDC Lab/{n}", "kind": "search", "conditions": len(st["files"]), "matches": 10})
            else:
                rows.append({"name": n, "path": f"VDC Lab/{n}", "kind": "search", "conditions": len(st["where"]), "matches": 10})
        return {"sets": rows}

    def m_props_sample(self, p: dict) -> dict:
        return {"item": "Conduit : sample", "from_selection": False, "categories": [
            {"category": "Element", "internal": "LcRevitData_Element", "properties": [
                {"name": "Category", "internal": "LcRevitPropertyElementCategory", "value": "Conduits"},
                {"name": "Level", "internal": "LcRevitPropertyElementLevel", "value": "Level 1"}]}]}

    def m_setup_apply(self, p: dict) -> dict:
        if p.get("if_fingerprint") != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the plan was made for", "plan again")
        missing: list[str] = []
        sets_added = sets_reused = tests_added = tests_reused = 0
        for st in p.get("sets") or []:
            if st["name"] in self.setup_sets or st["name"] in self.sets:
                sets_reused += 1
                continue
            if "files" in st:
                if not set(st["files"]) & set(self.clashset.models):
                    missing.append(st["name"] + ": ningún archivo coincide")
                    continue
            else:
                if any(c.get("value") == "__none__" for c in st["where"]):
                    missing.append(st["name"] + ": el criterio no encuentra elementos")
                    continue
            self.setup_sets[st["name"]] = st
            sets_added += 1
        for t in p.get("tests") or []:
            if t["name"] in self.setup_tests:
                tests_reused += 1
                continue
            if t["a_set"] not in self.setup_sets or t["b_set"] not in self.setup_sets:
                missing.append(t["name"] + ": falta el conjunto de un lado")
                continue
            self.setup_tests[t["name"]] = t
            tests_added += 1
        if sets_added or tests_added:
            self.revision += 1
        ok_sets = sum(1 for st in p.get("sets") or [] if st["name"] in self.setup_sets or st["name"] in self.sets)
        ok_tests = sum(1 for t in p.get("tests") or [] if t["name"] in self.setup_tests)
        return {"applied": {"sets_added": sets_added, "sets_reused": sets_reused, "tests_added": tests_added,
                            "tests_reused": tests_reused},
                "verified": {"sets": ok_sets, "tests": ok_tests}, "missing": missing, "notes": []}

    def m_doc_save(self, p: dict) -> dict:
        if p.get("if_fingerprint") != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the save was requested for")
        self.saves += 1
        return {"saved": True, "verified": True, "path": p.get("path") or self.title}

    def m_clash_image(self, p: dict) -> dict:
        clash_id = str(p.get("clash_id") or "")
        path = str(p.get("path") or "")
        if not path:
            raise Fault(INVALID_PARAMS, "path is required")
        if not any(c.id == clash_id for c in self.clashset.clashes):
            raise Fault(NOT_FOUND, f"unknown clash {clash_id!r}")
        with open(path, "wb") as f:
            f.write(_PLACEHOLDER_PNG)
        return {"saved": True, "path": path}

    def _known_for_view(self, p: dict) -> set[str]:
        if p.get("if_fingerprint") != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the analysis was made for",
                        "run nw_status and re-analyze")
        return {c.id for c in self.clashset.clashes}

    def m_view_select(self, p: dict) -> dict:
        known = self._known_for_view(p)
        guids = [str(g) for g in p.get("guids") or []]
        if not guids:
            raise Fault(INVALID_PARAMS, "guids is required")
        found = [g for g in guids if g in known]
        if not found:
            raise Fault(NOT_FOUND, "none of the clashes exist in the open document")
        self.selection = found
        self.colours, self.ghosted = {}, bool(p.get("ghost"))
        return {"selected": len(found) * 2, "clashes": len(found), "verified": True, "framed": bool(p.get("focus")),
                "ghosted": self.ghosted, "missing": [g for g in guids if g not in known][:20]}

    def m_view_color(self, p: dict) -> dict:
        known = self._known_for_view(p)
        groups = p.get("groups") or []
        if not groups:
            raise Fault(INVALID_PARAMS, "groups is required")
        self.colours, self.ghosted = {}, bool(p.get("ghost"))
        missing: list[str] = []
        for g in groups:
            for guid in g["guids"]:
                if guid in known:
                    self.colours[guid] = g["color"]
                else:
                    missing.append(guid)
        return {"groups": len(groups), "coloured_items": len(self.colours) * 2, "ghosted": self.ghosted,
                "missing": sorted(set(missing))[:20]}

    def m_view_reset(self, p: dict) -> dict:
        self.colours, self.ghosted = {}, False
        cleared = bool(p.get("clear_selection"))
        if cleared:
            self.selection = []
        return {"reset": True, "selection_cleared": cleared}

    def m_job_status(self, p: dict) -> dict:
        job = self._get(p)
        return {k: v for k, v in job.items() if k != "result"}

    def m_job_result(self, p: dict) -> Any:
        job = self._get(p)
        if job["state"] != "completed":
            raise Fault(BUSY, f"job is {job['state']}")
        return job["result"]

    def m_job_cancel(self, p: dict) -> dict:
        job = self._get(p)
        if job["state"] == "running":
            job["state"] = "cancelled"
        return {"job_id": job["job_id"], "state": job["state"]}

    def m_job_list(self, p: dict) -> list[dict]:
        return [{k: v for k, v in j.items() if k != "result"} for j in self.jobs.values()]

    def _get(self, p: dict) -> dict:
        job = self.jobs.get(str(p.get("job_id", "")))
        if job is None:
            raise Fault(NOT_FOUND, "unknown job")
        return job
