"""Self-check against a live Navisworks (or the simulator): `vdc-navis-lab-cli verify`.

It exercises every kind of call a session makes and prints only PASS or FAIL with figures. It never prints names
of files, tests, elements or levels, so the output can be pasted into a conversation about a confidential model. The
full error text of a failure goes to a log file in the data folder, which stays on this computer.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .paths import home
from .service import App, ToolFault


@dataclass
class Check:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    nw_peak_mb: int | None = None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def nw_peak_mb() -> int | None:
    """Peak working set of the Navisworks process, in MB (Windows only, best effort)."""
    if sys.platform != "win32":
        return None
    cmd = ("(Get-Process Roamer,FiletoolsTaskRunner -ErrorAction SilentlyContinue | "
           "Measure-Object -Property PeakWorkingSet64 -Maximum).Maximum")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=20).stdout.strip()
        return int(float(out) / (1024 * 1024)) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _wait(call: Callable[[], dict[str, Any]], total_s: float, step_s: float = 3.0) -> dict[str, Any]:
    """Calls that answer 'running' (background census, long extraction) are repeated until they finish."""
    end = time.monotonic() + total_s
    while True:
        try:
            res = call()
        except ToolFault as exc:
            if exc.code != "running" or time.monotonic() > end:
                raise
            time.sleep(step_s)
            continue
        if res.get("state") == "running" and time.monotonic() < end:
            time.sleep(step_s)
            continue
        return res


def run(app: App, writes: bool = False, wait_s: float = 900.0, say: Callable[[str], None] = print) -> Report:
    rep = Report()
    log = home() / "verify.log"
    scratch = tempfile.TemporaryDirectory(prefix="vdc-navis-lab-verify-")
    roots = os.environ.get("VDC_NAVIS_LAB_OUTPUT_ROOTS", "")
    os.environ["VDC_NAVIS_LAB_OUTPUT_ROOTS"] = scratch.name + (os.pathsep + roots if roots else "")
    ctx: dict[str, Any] = {}

    def step(name: str, fn: Callable[[], str]) -> bool:
        t0 = time.monotonic()
        try:
            detail, ok = fn(), True
        except ToolFault as exc:
            detail, ok = f"{exc.code}", False
            with log.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} {name}: {exc.code}: {exc.message}\n")
        except Exception as exc:  # a crash in a check is a failed check, not a crashed run
            detail, ok = type(exc).__name__, False
            with log.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} {name}: {type(exc).__name__}: {exc}\n")
        c = Check(name, ok, time.monotonic() - t0, detail)
        rep.checks.append(c)
        say(f"{'PASS' if ok else 'FAIL'}  {name:<26} {c.seconds:7.1f} s  {detail}")
        return ok

    def status() -> str:
        st = app.status()
        inst = st["bridge"]["instances"]
        if not inst:
            raise ToolFault("no_instance", "no Navisworks instance")
        doc_open = bool(inst[0].get("open"))
        if not doc_open:
            raise ToolFault("no_document", "no document open")
        t = st["tests"]
        ctx["tests"], ctx["clashes"] = t["count"], sum(int(i.get("count") or 0) for i in t["items"])
        return f"{inst[0].get('version', '?')}; {t['count']} tests, {ctx['clashes']} results"

    def census() -> str:
        m = _wait(lambda: app.model(False), wait_s)
        models = m.get("models", [])
        return f"{len(models)} models, {sum(int(x.get('elements', 0)) for x in models)} elements"

    def analyze() -> str:
        a = _wait(lambda: app.analyze("", None, 5, 45, "", None), wait_s)
        if a.get("state") == "running":
            a = _wait(lambda: app.analyze("", None, 5, 45, a.get("job_id", ""), None), wait_s)
        ctx["analysis"] = a
        b = a["per_band"]
        return (f"{a['raw_count']} results -> {a['issues']} issues "
                f"(critical {b['critical']}, high {b['high']}, medium {b['medium']}, low {b['low']}); "
                f"filtered {sum(a.get('filtered', {}).values())}, complete={a['coverage']['complete']}")

    def issues() -> str:
        res = app.issues("", "", "", "", "", "rank", 5, 0, None)
        ctx["issue_ids"] = [i["id"] for i in res["items"]]
        if res["total"] == 0:
            return "0 issues (nothing to inspect; this is not a failure when every result was already closed)"
        d = app.issue(ctx["issue_ids"][0], None)
        return f"{res['total']} issues; detail has {len(d)} fields"

    def view() -> str:
        if not ctx.get("issue_ids"):
            return "skipped (no issues)"
        app.view("select", ctx["issue_ids"][:1], True)
        app.view("color", None, True)
        app.view("reset", None, True, True)
        return "select, color, reset"

    def reports() -> str:
        got = []
        for kind in ("summary", "matrix", "hotspots", "plan", "markdown"):
            app.report(kind, "", False, 10, None)
            got.append(kind)
        for kind in ("csv", "json", "pdf", "handoff", "bcf"):
            r = app.report(kind, str(Path(scratch.name) / f"v.{kind}"), True, 25, None)
            if int(r["bytes"]) <= 0:
                raise ToolFault("empty_file", kind)
            got.append(f"{kind} {int(r['bytes']) // 1024} KB")
        return ", ".join(got)

    def image() -> str:
        if not ctx.get("issue_ids"):
            return "skipped (no issues)"
        r = app.report("image", str(Path(scratch.name) / "v.png"), True, 1, None, ctx["issue_ids"][0])
        size = Path(r["path"]).stat().st_size
        if size <= 0:
            raise ToolFault("empty_file", "image")
        return f"png {size} bytes"

    def setup_list() -> str:
        res = app.setup("list", None, "", True)
        return f"sets and tests listed ({len(res.get('sets', []) or [])} sets)"

    def save_preview() -> str:
        res = app.document("save", "", False, False)
        if not res.get("dry_run"):
            raise ToolFault("no_preview", "save did not preview")
        return "preview only, nothing saved"

    def apply_plan() -> str:
        if not ctx.get("issue_ids"):
            return "skipped (no issues)"
        ops = [{"op": "group", "issues": "top:1"}, {"op": "status", "issues": "top:1", "status": "active"},
               {"op": "viewpoint", "issues": "top:1"}]
        plan = app.apply(ops, "", True)
        done = app.apply(None, plan["plan_id"], False)
        if done.get("state") != "completed":
            raise ToolFault("not_completed", str(done.get("state")))
        return f"state {done['state']}; verified {done.get('verified')}"

    for name, fn in (("status", status), ("model census", census), ("analysis", analyze), ("issues", issues),
                     ("view select/color/reset", view), ("reports and exports", reports), ("image of an issue", image),
                     ("sets and tests listing", setup_list), ("save preview", save_preview)):
        if not step(name, fn) and name == "status":
            break
    if writes and rep.checks and rep.checks[0].ok:
        step("write plan (group+status+viewpoint)", apply_plan)
    rep.nw_peak_mb = nw_peak_mb()
    scratch.cleanup()
    return rep
