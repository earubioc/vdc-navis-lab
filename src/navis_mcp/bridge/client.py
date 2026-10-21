"""Stateless client: one connection per request, so a restarted Navisworks never leaves a stale socket."""

from __future__ import annotations

import time
from typing import Any, Callable

from .protocol import (AMBIGUOUS, API_VERSION, NO_INSTANCE, UNREACHABLE, BridgeError, decode_response,
                       encode_request)
from .transport import Endpoint, connect, discover

DEFAULT_TIMEOUT = 30.0


class Bridge:
    def __init__(self, discover_fn: Callable[[], list[Endpoint]] = discover, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._discover = discover_fn
        self.timeout = timeout
        self.pinned_id: str = ""

    # ---- raw call
    def call_at(self, ep: Endpoint, method: str, params: dict[str, Any] | None = None,
                timeout: float | None = None) -> Any:
        conn = connect(ep, timeout or self.timeout)
        try:
            conn.send(encode_request(method, params))
            return decode_response(conn.read_line())
        finally:
            conn.close()

    # ---- instances
    def instances(self) -> tuple[list[dict[str, Any]], list[str]]:
        """(reachable instances with their hello, endpoints that did not answer)."""
        found, dead = [], []
        for ep in self._discover():
            try:
                info = self.call_at(ep, "hello", {"client_api": API_VERSION}, timeout=3.0)
            except BridgeError:
                dead.append(str(ep))
                continue
            info["endpoint"] = str(ep)
            found.append(info)
        return found, dead

    def select(self, instance_id: str) -> dict[str, Any]:
        found, _ = self.instances()
        match = next((i for i in found if i.get("instance_id") == instance_id), None)
        if match is None:
            raise BridgeError(NO_INSTANCE, f"no reachable instance {instance_id!r}", "call nw_connect(action='list')",
                              data=[i.get("instance_id") for i in found])
        self.pinned_id = instance_id
        return match

    def release(self) -> None:
        self.pinned_id = ""

    def resolve(self, for_write: bool = False) -> tuple[Endpoint, dict[str, Any], str]:
        """Pick the instance for a call. Reads may take the newest and say so; writes never guess."""
        found, _ = self.instances()
        if not found:
            raise BridgeError(NO_INSTANCE, "no Navisworks instance with the add-in is reachable",
                              "open Navisworks with the navis-mcp add-in loaded, or start the simulator")
        if self.pinned_id:
            match = next((i for i in found if i.get("instance_id") == self.pinned_id), None)
            if match is None:
                raise BridgeError(NO_INSTANCE, "the selected instance is gone",
                                  "call nw_connect(action='list') and select again")
            return Endpoint.parse(match["endpoint"]), match, ""
        if len(found) == 1:
            return Endpoint.parse(found[0]["endpoint"]), found[0], ""
        if for_write:
            raise BridgeError(AMBIGUOUS, "several Navisworks instances are open and none is selected",
                              "choose one with nw_connect(action='select', target=...) before writing",
                              data=[{"instance_id": i.get("instance_id"), "doc": (i.get("doc") or {}).get("title")}
                                    for i in found])
        newest = max(found, key=lambda i: i.get("started", 0))
        return (Endpoint.parse(newest["endpoint"]), newest,
                f"{len(found)} instances open; read from the most recent ({newest.get('instance_id')})")

    def call(self, method: str, params: dict[str, Any] | None = None, *, for_write: bool = False,
             timeout: float | None = None) -> tuple[Any, dict[str, Any], str]:
        ep, info, note = self.resolve(for_write)
        return self.call_at(ep, method, params, timeout), info, note

    # ---- jobs
    def wait_job(self, ep: Endpoint, job_id: str, wait: float, poll: float = 0.2) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            status = self.call_at(ep, "job.status", {"job_id": job_id})
            if status.get("state") in ("completed", "failed", "cancelled", "partial") or time.monotonic() >= deadline:
                return status
            time.sleep(poll)
