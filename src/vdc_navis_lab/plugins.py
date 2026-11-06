"""Plugin discovery by entry points (group `vdc_navis_lab.plugins`) and the version policy (D-14).

A plugin package declares in its pyproject.toml:

    [project.entry-points."vdc_navis_lab.plugins"]
    pro = "vdc_navis_lab_pro:register"

and depends on the core with `vdc-navis-lab>=N.M,<N.(M+1)`: Pro N.M needs core N.M.x. The server checks that
requirement from the package metadata, before importing the plugin, so an incompatible plugin is never loaded
halfway. `register(mcp, app)` may add tools (prefix `nwp_`) and provides capabilities with
`app.capabilities.provide`; `mcp` is None outside the server (CLI, tests). A failing plugin never stops the server:
it is listed as failed in nw_status with its cause.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Iterable

from . import __version__
from .capabilities import DISABLED_ENV, plugins_disabled

GROUP = "vdc_navis_lab.plugins"
CORE_DIST = "vdc-navis-lab"


@dataclass
class PluginInfo:
    name: str
    version: str = ""
    core_requires: str = ""
    provides: tuple[str, ...] = ()
    state: str = "loaded"  # loaded | failed | incompatible | disabled
    detail: Any = field(default_factory=dict)  # a dict, or a function returning one (evaluated on every nw_status)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "version": self.version, "state": self.state,
                               "core_requires": self.core_requires, "provides": list(self.provides)}
        out.update(self.detail() if callable(self.detail) else self.detail)
        return out


def parse_version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in re.split(r"[.\-+]", text.strip()):
        m = re.match(r"^(\d+)", piece)
        if not m:
            break
        parts.append(int(m.group(1)))
        if m.group(0) != piece:
            break
    return tuple(parts) or (0,)


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def satisfies(version: str, spec: str) -> bool:
    """True when `version` meets every comparator of a spec like '>=1.1,<1.2' (numeric versions only)."""
    v = parse_version(version)
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"^(>=|<=|==|!=|>|<)\s*(.+)$", raw)
        if not m:
            return False
        op, want = m.group(1), parse_version(m.group(2))
        c = _cmp(v, want)
        if not {">=": c >= 0, "<=": c <= 0, "==": c == 0, "!=": c != 0, ">": c > 0, "<": c < 0}[op]:
            return False
    return True


def core_requirement(requires: Iterable[str] | None) -> str | None:
    """The version spec a package declares for the core, read from its metadata (None if it declares none)."""
    for req in requires or ():
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*\(?([^;()]*)\)?", req)
        if m and re.sub(r"[-_.]+", "-", m.group(1)).lower() == CORE_DIST:
            return m.group(2).strip() or ""
    return None


def _entry_points() -> list[Any]:
    return list(metadata.entry_points(group=GROUP))


def load_plugins(app: Any, mcp: Any = None, entry_points: Iterable[Any] | None = None,
                 core_version: str = __version__) -> list[PluginInfo]:
    """Discover and register plugins on `app` (and add their tools to `mcp` when given). Never raises."""
    infos: list[PluginInfo] = []
    if plugins_disabled():
        app.capabilities.disabled = True
        app.plugins = [PluginInfo(name="*", state="disabled", detail={"why": f"{DISABLED_ENV} is set"})]
        return app.plugins
    for ep in (_entry_points() if entry_points is None else list(entry_points)):
        dist = getattr(ep, "dist", None)
        info = PluginInfo(name=ep.name, version=getattr(dist, "version", "") or "")
        infos.append(info)
        spec = core_requirement(getattr(dist, "requires", None))
        info.core_requires = spec or ""
        if spec is None or not spec or not satisfies(core_version, spec):
            info.state = "incompatible"
            info.detail = {"why": f"needs vdc-navis-lab {spec or '(no requirement declared)'}, this core is {core_version}"}
            continue
        try:
            before = set(app.capabilities._providers)
            returned = ep.load()(mcp, app)
            after = set(app.capabilities._providers)
            info.provides = tuple(sorted(after - before))
            if isinstance(returned, PluginInfo):
                info.version = returned.version or info.version
                info.detail = returned.detail
        except Exception as exc:  # a plugin must not take the server down
            info.state = "failed"
            info.detail = {"why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    app.plugins = infos
    return infos
