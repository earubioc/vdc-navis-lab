"""Paged extraction of the clash results of the open Navisworks document.

The add-in answers `clash.page`: one bounded slice of one test per call, open results first, with a time budget per call.
This module walks the tests one after the other, keeps what it gets, and builds a ClashSet. Compared with one export job:

* it is not limited by the size of one pipe message (64 MB) nor by what the Navisworks process can hold at once;
* Navisworks gets the UI thread back between slices (a pause proportional to the time of each slice);
* it stops, and says why, when a budget runs out: described results (VDC_NAVIS_LAB_MAX_CLASHES), memory of this process
  (VDC_NAVIS_LAB_MAX_SERVER_MB), memory of Navisworks (the add-in's own guard), time (VDC_NAVIS_LAB_MAX_EXTRACT_S);
* closed results (approved, resolved) are the ones the noise filter drops, so when the profile drops them they are only
  counted, not described (a few per test are described, so a pair that only has closed results still shows as seen).

The budget is shared out test by test (what a test does not use goes to the following ones), so an incomplete extraction
is incomplete everywhere a little instead of missing whole tests.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
import uuid
from typing import Any

from .bridge import BridgeError
from .bridge.protocol import BUSY, TIMEOUT
from .memory import rss_mb
from .model import Clash, ClashSet, TestInfo

DEFAULT_CAP = 500_000
DEFAULT_SERVER_MB = 3072
DEFAULT_SECONDS = 3600
CLOSED_SAMPLE = 25
PAGE_RETRIES = 6


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class Limits:
    """Budgets of one extraction. 0 means no limit for that budget."""

    def __init__(self, cap: int | None = None, server_mb: int | None = None, seconds: int | None = None,
                 page_ms: int | None = None, duty: float | None = None) -> None:
        self.cap = _env_int("VDC_NAVIS_LAB_MAX_CLASHES", DEFAULT_CAP) if cap is None else cap
        self.server_mb = _env_int("VDC_NAVIS_LAB_MAX_SERVER_MB", DEFAULT_SERVER_MB) if server_mb is None else server_mb
        self.seconds = _env_int("VDC_NAVIS_LAB_MAX_EXTRACT_S", DEFAULT_SECONDS) if seconds is None else seconds
        self.page_ms = _env_int("VDC_NAVIS_LAB_PAGE_MS", 1500) if page_ms is None else page_ms
        raw = os.environ.get("VDC_NAVIS_LAB_EXTRACT_DUTY", "")
        try:
            duty = float(raw) if (duty is None and raw) else duty
        except ValueError:
            duty = None
        self.duty = min(1.0, max(0.1, duty if duty is not None else 0.8))


def _basename(path: str) -> str:
    return re.split(r"[\\/]", str(path or ""))[-1]


class Extraction:
    def __init__(self, bridge: Any, endpoint: Any, tests: list[str] | None, drop_closed: bool,
                 limits: Limits | None = None) -> None:
        self.bridge, self.ep = bridge, endpoint
        self.names = set(tests or [])
        self.drop_closed = drop_closed
        self.limits = limits or Limits()
        self.job_id = "ext-" + uuid.uuid4().hex[:8]
        self.state = "running"
        self.stage = "starting"
        self.error: tuple[str, str] | None = None
        self.result: ClashSet | None = None
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=self.job_id)
        self._lock = threading.Lock()
        self.started = time.monotonic()
        self.tests_total = self.tests_done = 0
        self.results_available = 0
        self.described = 0
        self.pages = 0
        self.waiting = 0
        self.slowest_s = 0.0

    # ------------------------------------------------------------ control
    def start(self) -> "Extraction":
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, seconds: float) -> str:
        self._thread.join(max(0.0, seconds))
        return self.state

    def status(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started
        with self._lock:
            return {"job_id": self.job_id, "kind": "extraction", "state": self.state, "error": self.error[1] if self.error else "",
                    "progress": {"kind": "determinate", "done": self.tests_done, "total": self.tests_total,
                                 "stage": self.stage, "results_described": self.described,
                                 "results_available": self.results_available, "pages": self.pages,
                                 "elapsed_s": round(elapsed, 1),
                                 "results_per_s": round(self.described / elapsed) if elapsed > 1 else None}}

    # ------------------------------------------------------------ work
    def _page(self, params: dict[str, Any]) -> dict[str, Any]:
        """One clash.page call. A busy Navisworks (a dialog, a long operation of the user) is waited for, not failed."""
        for attempt in range(PAGE_RETRIES):
            if self._cancel.is_set():
                raise _Stop("cancelled")
            try:
                return self.bridge.call_at(self.ep, "clash.page", params, 120.0)
            except BridgeError as exc:
                if exc.code not in (BUSY, TIMEOUT) or attempt == PAGE_RETRIES - 1:
                    raise
                with self._lock:
                    self.waiting += 1
                    self.stage = "waiting for Navisworks"
                time.sleep(min(30.0, 2.0 * (attempt + 1)))
        raise AssertionError("unreachable")

    def _run(self) -> None:
        try:
            self.result = self._extract()
            self.state = "cancelled" if self._cancel.is_set() and self.result.partial else "completed"
        except _Fail as exc:
            self.error, self.state = (exc.code, exc.message), "failed"
        except BridgeError as exc:
            self.error, self.state = (exc.code, str(exc)), "failed"
        except Exception as exc:  # a crash here must show as a failed job, never as a hung one
            self.error, self.state = ("internal", type(exc).__name__), "failed"
        finally:
            try:
                self.bridge.call_at(self.ep, "clash.release", None, 15.0)
            except Exception:
                pass

    def _extract(self) -> ClashSet:
        lim = self.limits
        hello = self.bridge.call_at(self.ep, "hello", {"light": True}, 60.0)
        doc = dict(hello.get("doc") or {})
        fingerprint = str(doc.get("fingerprint", ""))
        rows = self.bridge.call_at(self.ep, "clash.tests", None, 300.0)
        info = self.bridge.call_at(self.ep, "doc.info", None, 60.0)
        rows = [r for r in rows if not self.names or r.get("name") in self.names]
        if self.names and not rows:
            raise _Fail("not_found", "none of the requested tests exists in the open document")
        self.tests_total = len(rows)
        self.results_available = sum(int(r.get("count", 0) or 0) for r in rows)

        cs = ClashSet(models=[_basename(m) for m in info.get("models", [])], document=doc, source="navisworks")
        cs.tests = [TestInfo.from_dict(r) for r in rows]
        reasons: list[dict[str, Any]] = []
        cap = lim.cap
        base_mb = rss_mb()
        started = time.monotonic()
        first = True
        open_available = open_extracted = tests_partial = 0
        stop_all = False
        todo = [r for r in rows if int(r.get("count", 0) or 0) > 0]
        self.stage = "extracting"

        for n, row in enumerate(todo):
            if stop_all:
                tests_partial += 1
                # not even started: everything it has is missing (its open count is unknown, so use its total as the bound)
                open_available += int(row.get("count", 0) or 0)
                continue
            name = str(row["name"])
            left_tests = len(todo) - n
            quota = math.ceil((cap - self.described) / left_tests) if cap > 0 else 0
            if cap > 0 and quota <= 0:
                stop_all = True
                reasons.append({"code": "cap", "cap": cap})
                tests_partial += 1
                open_available += int(row.get("count", 0) or 0)
                continue
            cursor, got_open, described_here, sampled = 0, 0, 0, 0
            got_page = False
            open_total = closed_total = 0
            test_partial = False
            while True:
                if self._cancel.is_set():
                    stop_all = True
                    reasons.append({"code": "cancelled"})
                    test_partial = True
                    break
                if lim.seconds > 0 and time.monotonic() - started > lim.seconds:
                    stop_all = True
                    reasons.append({"code": "time", "s": lim.seconds})
                    test_partial = True
                    break
                if lim.server_mb > 0 and rss_mb() - base_mb > lim.server_mb:
                    stop_all = True
                    reasons.append({"code": "memory_server", "mb": lim.server_mb})
                    test_partial = True
                    break
                ask = 1000
                if quota > 0:
                    ask = min(ask, quota - described_here)
                    if ask <= 0:
                        test_partial = True  # this test used its share
                        break
                params = {"test": name, "cursor": cursor, "limit": max(25, ask), "budget_ms": lim.page_ms,
                          "closed_describe": (max(0, CLOSED_SAMPLE - sampled) if self.drop_closed else -1),
                          "begin": first, "if_fingerprint": fingerprint}
                t0 = time.monotonic()
                try:
                    page = self._page(params)
                except _Stop:
                    stop_all = True
                    reasons.append({"code": "cancelled"})
                    test_partial = True
                    break
                dt = time.monotonic() - t0
                self.slowest_s = max(self.slowest_s, dt)
                first, got_page = False, True
                items = page.get("clashes", [])
                for raw in items:
                    c = Clash.from_dict(raw)
                    cs.clashes.append(c)
                    if c.status in ("approved", "resolved"):
                        sampled += 1
                    else:
                        got_open += 1
                described_here += len(items)
                cs.skipped += int(page.get("skipped", 0))
                cs.skipped_open = (cs.skipped_open or 0) + int(page.get("skipped_open", 0))
                cs.closed_unextracted[name] = cs.closed_unextracted.get(name, 0) + int(page.get("closed_skipped", 0))
                open_total, closed_total = int(page.get("open_total", 0)), int(page.get("closed_total", 0))
                with self._lock:
                    self.described += len(items)
                    self.pages += 1
                    self.stage = "extracting"
                if page.get("stop") == "memory":
                    stop_all = True
                    reasons.append({"code": "memory_addin"})
                    test_partial = True
                    cursor = int(page["next"]) if page.get("next") is not None else cursor
                    break
                if page.get("next") is None:
                    cursor = open_total + closed_total
                    break
                cursor = int(page["next"])
                # Give Navisworks the UI thread back: a pause proportional to what the slice took.
                time.sleep(max(0.05, dt * (1.0 - lim.duty) / lim.duty))

            if got_page:
                needed = open_total + (0 if self.drop_closed else closed_total)
            else:  # never got a page: the total is what clash.tests said
                needed = int(row.get("count", 0) or 0)
            open_available += needed
            open_extracted += got_open if self.drop_closed else described_here
            if not got_page:
                unexamined = needed
            elif self.drop_closed:
                unexamined = max(0, open_total - min(cursor, open_total))
            else:
                unexamined = max(0, open_total + closed_total - cursor)
            if unexamined:
                tests_partial += 1
            if self.drop_closed and got_page:  # a closed result that was not described is, for the filter, simply a closed result
                examined_closed = max(0, cursor - open_total)
                cs.closed_unextracted[name] = cs.closed_unextracted.get(name, 0) + max(0, closed_total - examined_closed)
            with self._lock:
                self.tests_done += 1

        if tests_partial or reasons:
            if not reasons:
                reasons.append({"code": "cap", "cap": cap})
            seen: set[str] = set()
            cs.partial = {"reasons": [r for r in reasons if not (r["code"] in seen or seen.add(r["code"]))],
                          "open_available": open_available, "open_extracted": open_extracted,
                          "tests_partial": tests_partial, "tests_total": len(rows),
                          "described": self.described, "pages": self.pages}
            cs.truncated = True
        cs.closed_unextracted = {k: v for k, v in cs.closed_unextracted.items() if v}
        cs.stats = {"pages": self.pages, "described": self.described, "seconds": round(time.monotonic() - started, 1),
                    "slowest_slice_s": round(self.slowest_s, 2), "closed_only_counted": sum(cs.closed_unextracted.values()),
                    "waited_for_navisworks": self.waiting}
        return cs


class _Stop(Exception):
    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


class _Fail(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message
