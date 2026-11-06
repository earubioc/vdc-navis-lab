"""Capability catalogue: named places where an installed package can provide what the core does not contain.

The core declares the names and asks for them with `call`. A plugin registers an implementation with `provide`.
No provider means `pro_required`, never a crash: previews, analysis, markdown reports and every read-only tool
keep working. The commercial gate lives here, in the server. The Navisworks add-in speaks an open protocol and
cannot be gated (see docs/PROTOCOL.md).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from .errors import ToolFault

# name -> what the core asks for. Names never change inside a minor version; adding one is compatible.
CATALOG: dict[str, str] = {
    "writes.execute": "execute a nw_apply plan in Navisworks and verify it by rereading",
    "setup.execute": "execute a nw_setup plan (sets and clash tests) and verify it",
    "document.save": "save the open Navisworks document (save, save_as), after a preview",
    "report.csv": "CSV of the issues",
    "report.bcf": "BCF 2.1 export",
    "report.pdf": "PDF coordination report",
    "report.handoff": "CSV for the model authors, one row per element to change",
    "report.json": "re-readable JSON export of the analysis",
    "report.image": "PNG framed on one issue",
    "snapshot.compare": "diff of two analyses by what the issues are made of",
    "profiles.packs": "calibrated profile packs (TOML files)",
}

DISABLED_ENV = "VDC_NAVIS_LAB_NO_PLUGINS"


def plugins_disabled() -> bool:
    return os.environ.get(DISABLED_ENV, "").lower() in ("1", "true", "yes")


class Capabilities:
    def __init__(self, on_call: Callable[[str, str], None] | None = None) -> None:
        self._providers: dict[str, tuple[Callable[..., Any], str, Callable[[], bool] | None]] = {}
        self._on_call = on_call
        self.disabled = False  # set by load_plugins when VDC_NAVIS_LAB_NO_PLUGINS is on

    def provide(self, name: str, fn: Callable[..., Any], plugin: str = "",
                available: Callable[[], bool] | None = None) -> None:
        """`available` tells whether the provider would run right now (for example, its license is valid)."""
        if name not in CATALOG:
            raise ValueError(f"unknown capability {name!r}")
        if name in self._providers:
            raise ValueError(f"capability {name!r} already provided by {self._providers[name][1]!r}")
        self._providers[name] = (fn, plugin, available)

    def has(self, name: str) -> bool:
        """True when a provider exists and says it would run now. `call` works even when this is False: a provider that
        is present but unavailable (an expired license) explains itself with its own pro_required message."""
        entry = self._providers.get(name)
        if entry is None:
            return False
        try:
            return True if entry[2] is None else bool(entry[2]())
        except Exception:
            return False

    def names(self) -> dict[str, list[str]]:
        have = sorted(n for n in CATALOG if self.has(n))
        return {"available": have, "missing": sorted(n for n in CATALOG if n not in have)}

    def _note(self, name: str, outcome: str) -> None:
        if self._on_call is not None:
            self._on_call(name, outcome)

    def missing_fault(self, name: str) -> ToolFault:
        if self.disabled:
            why = "plugins are disabled in this server (VDC_NAVIS_LAB_NO_PLUGINS is set)"
        else:
            why = "the Pro package is not installed in this server"
        return ToolFault(
            "pro_required", f"{name!r} is a Pro capability: {why}",
            "analysis, previews, markdown reports and every read-only tool still work; do not retry and do not "
            "claim that the change was made", {"capability": name})

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in CATALOG:
            raise ValueError(f"unknown capability {name!r}")
        entry = self._providers.get(name)
        if entry is None:
            self._note(name, "pro_required")
            raise self.missing_fault(name)
        try:
            out = entry[0](*args, **kwargs)
        except ToolFault as exc:
            self._note(name, "pro_required" if exc.code == "pro_required" else f"fault:{exc.code}")
            raise
        except Exception:
            self._note(name, "error")
            raise
        self._note(name, "ok")
        return out
