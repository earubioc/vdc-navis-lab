"""A stand-in for the Navisworks add-in, speaking the real protocol over loopback TCP.

It serves the synthetic tower from navis_mcp.sample, keeps clash groups and statuses in memory, and
re-reads them to report what was *verified*. It exists so the server, the tests and demos run on
any machine; it is not a model of Navisworks' behaviour beyond the contract in docs/PROTOCOL.md.
"""

from __future__ import annotations

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

METHODS = ["hello", "doc.info", "model.census", "elements.query", "clash.tests", "clash.run", "clash.export",
           "clash.apply", "doc.save", "job.status", "job.result", "job.cancel", "job.list"]


class Fault(Exception):
    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


class Simulator:
    def __init__(self, seed: int = 7, port: int = 0, job_delay: float = 0.15) -> None:
        self.clashset, self.elements = build(seed)
        self.job_delay = job_delay
        self.instance_id = f"sim-{uuid.uuid4().hex[:8]}"
        self.started = time.time()
        self.title = self.clashset.document["title"]
        self.fingerprint = hashlib.sha1(f"{self.title}|{sorted(self.clashset.models)}".encode()).hexdigest()[:16]
        self.groups: dict[str, set[str]] = {}
        self.status: dict[str, str] = {c.id: c.status for c in self.clashset.clashes}
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
        return {"product": "navisworks-simulator", "version": "0.1", "api": API_VERSION,
                "instance_id": self.instance_id, "started": self.started, "doc": self._doc(), "methods": METHODS}

    def m_doc_info(self, p: dict) -> dict:
        return {**self._doc(), "models": self.clashset.models, "units": "m", "saves": self.saves}

    def m_model_census(self, p: dict) -> dict:
        models = []
        for name in self.clashset.models:
            els = [e for e in self.elements if e.model == name]
            cats = Counter(e.category for e in els)
            models.append({"name": name, "elements": len(els), "categories": dict(cats.most_common(12))})
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
            return True

        hits = [e for e in self.elements if ok(e)]
        out: dict[str, Any] = {"count": len(hits)}
        if group_by:
            out["groups"] = [{"key": k, "count": n} for k, n in Counter(value_of(e, group_by) for e in hits).most_common(limit)]
        out["sample"] = [{"id": e.id, "name": e.name, "category": e.category, "model": e.model, "level": e.level}
                         for e in hits[:limit]]
        return out

    def m_clash_tests(self, p: dict) -> list[dict]:
        return [{**t.to_dict(), "count": sum(1 for c in self.clashset.clashes if c.test == t.name)}
                for t in self.clashset.tests]

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
        for g in p.get("groups") or []:
            guids = [x for x in g["guids"] if x in known]
            missing += [x for x in g["guids"] if x not in known]
            if g["name"] in self.groups:
                reused += 1
            else:
                created += 1
            self.groups.setdefault(g["name"], set()).update(guids)
        for s in p.get("statuses") or []:
            for guid in s["guids"]:
                if guid in known:
                    self.status[guid] = s["status"]
                    status_set += 1
                else:
                    missing.append(guid)
        wanted_groups = {g["name"]: {x for x in g["guids"] if x in known} for g in p.get("groups") or []}
        verified_groups = sum(1 for n, ids in wanted_groups.items() if ids <= self.groups.get(n, set()))
        verified_status = sum(1 for s in p.get("statuses") or [] for guid in s["guids"]
                              if guid in known and self.status[guid] == s["status"])
        if created or status_set:
            self.revision += 1
        result = {"applied": {"groups_added": created, "groups_reused": reused, "statuses_set": status_set},
                  "verified": {"groups": verified_groups, "statuses": verified_status}, "missing": sorted(set(missing))}
        if key:
            self.applied[key] = result
        return result

    def m_doc_save(self, p: dict) -> dict:
        if p.get("if_fingerprint") != self.fingerprint:
            raise Fault(STALE_DOCUMENT, "the open document is not the one the save was requested for")
        self.saves += 1
        return {"saved": True, "verified": True, "path": p.get("path") or self.title}

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
