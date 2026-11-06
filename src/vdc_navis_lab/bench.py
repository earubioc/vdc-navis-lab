"""Scale measurements: `vdc-navis-lab-cli bench`.

Three modes, all printing only figures (never names of files, tests, elements or levels), so the output can be shared
about a confidential model:

* default: a synthetic infrastructure-sized federation, generated and analysed in memory;
* --file X: the same measurement on an exported clash file (.json/.xml/.csv);
* --live: the whole path against the Navisworks that is open now (extraction, analysis, responsiveness of Navisworks
  while it works, peak memory of both processes). Run it on your own machine with your own model: nothing is sent anywhere.
"""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time
from typing import Any, Callable

from . import ingest
from .engine import analyze
from .profile import Profile
from .sample.generator import build_infra


def peak_rss_mb() -> int:
    """Peak memory of this process, in MB."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = Counters()
        c.cb = ctypes.sizeof(c)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return int(c.PeakWorkingSetSize / (1024 * 1024))
    import resource
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(kb / 1024 / (1024 if sys.platform == "darwin" else 1))


def _band_text(result: Any) -> str:
    n = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for i in result.issues:
        n[i.priority] = n.get(i.priority, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in n.items())


def _json_mb(cs: Any) -> float:
    """Size of the full export as JSON, extrapolated from a sample (serialising 700,000 results just to count would
    itself take minutes and gigabytes)."""
    sample = cs.clashes[: min(2000, len(cs.clashes))]
    if not sample:
        return 0.0
    per = len(json.dumps([c.to_dict() for c in sample])) / len(sample)
    return per * len(cs.clashes) / (1024 * 1024)


def run_clashset(cs: Any, label: str, build_s: float | None, say: Callable[[str], None] = print) -> dict[str, Any]:
    say(f"{label}: {len(cs.tests)} tests, {len(cs.clashes)} results, export as JSON about {_json_mb(cs):.0f} MB")
    after_build = peak_rss_mb()
    if build_s is not None:
        say(f"  generation {build_s:.1f} s, memory so far {after_build} MB")
    t0 = time.monotonic()
    res = analyze(cs, Profile.default(), "es")
    secs = time.monotonic() - t0
    peak = peak_rss_mb()
    out = {"results": len(cs.clashes), "tests": len(cs.tests), "issues": len(res.issues), "analysis_s": round(secs, 1),
           "peak_mb": peak, "engine_mb": peak - after_build if peak > after_build else 0}
    say(f"  analysis {secs:.1f} s -> {len(res.issues)} issues ({_band_text(res)}); peak memory {peak} MB")
    return out


def run_synthetic(tests: int, per_test: int, seed: int, per_place: int = 6,
                  say: Callable[[str], None] = print) -> dict[str, Any]:
    t0 = time.monotonic()
    cs = build_infra(tests, per_test, seed, per_place=per_place)
    return run_clashset(cs, "synthetic infrastructure", time.monotonic() - t0, say)


def run_file(path: str, say: Callable[[str], None] = print) -> dict[str, Any]:
    t0 = time.monotonic()
    cs = ingest.load(path)
    return run_clashset(cs, "file", time.monotonic() - t0, say)


def run_live(app: Any, wait_s: float = 1800.0, say: Callable[[str], None] = print) -> dict[str, Any]:
    from .service import ToolFault
    from .verify import _wait, nw_peak_mb

    st = app.status()
    inst = st["bridge"]["instances"]
    if not inst or not inst[0].get("open"):
        raise ToolFault("no_document", "Navisworks is not reachable or has no document open")
    t = st["tests"]
    total = sum(int(i.get("count") or 0) for i in t["items"])
    say(f"live: {inst[0].get('version', '?')}; {t['count']} tests, {total} results in Navisworks")
    ep, _, _ = app.bridge.resolve(False)
    pings: list[tuple[float, bool]] = []
    stop = threading.Event()

    def ping() -> None:
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                app.bridge.call_at(ep, "hello", None, 25.0)
                pings.append((time.monotonic() - t0, True))
            except Exception:
                pings.append((time.monotonic() - t0, False))
            stop.wait(2.0)

    th = threading.Thread(target=ping, daemon=True)
    th.start()
    t0 = time.monotonic()
    try:
        a = _wait(lambda: app.analyze("", None, 5, 45, "", None), wait_s)
        if a.get("state") == "running":
            a = _wait(lambda: app.analyze("", None, 5, 45, a.get("job_id", ""), None), wait_s)
    finally:
        stop.set()
        th.join(5)
    secs = time.monotonic() - t0
    out: dict[str, Any] = {"results": total, "tests": t["count"], "analysis_s": round(secs, 1), "peak_mb": peak_rss_mb(),
                           "nw_peak_mb": nw_peak_mb()}
    if a.get("state") == "running":
        say(f"  extraction and analysis did not finish within {wait_s:.0f} s")
        out["finished"] = False
    else:
        cov = a.get("coverage", {})
        out.update(finished=True, raw=a["raw_count"], issues=a["issues"], complete=cov.get("complete"),
                   skipped=cov.get("skipped"))
        say(f"  extraction + analysis {secs:.0f} s: {a['raw_count']} results -> {a['issues']} issues; "
            f"per band {a['per_band']}; complete={cov.get('complete')}")
        if any("truncad" in w or "truncat" in w or "cap" in w for w in cov.get("warnings", [])):
            say("  the extraction hit the cap or the memory guard (coverage says so)")
            out["capped"] = True
    if pings:
        ok = [s for s, good in pings if good]
        bad = len(pings) - len(ok)
        med = statistics.median(ok) * 1000 if ok else None
        mx = max(s for s, _ in pings) * 1000
        say(f"  Navisworks answered {len(ok)} of {len(pings)} pings during the work; "
            f"median {med:.0f} ms, slowest {mx:.0f} ms, {bad} failed (busy)" if med is not None else
            f"  Navisworks did not answer any of {len(pings)} pings during the work")
        out["pings"] = {"n": len(pings), "failed": bad, "median_ms": round(med) if med is not None else None, "max_ms": round(mx)}
    say(f"  memory: this process {out['peak_mb']} MB" + (f", Navisworks peak {out['nw_peak_mb']} MB" if out["nw_peak_mb"] else ""))
    return out
