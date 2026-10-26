"""Severity: a weighted sum of bounded components, renormalised over those that apply.

A clearance-only issue has no penetration and a hard-only issue has no clearance, so
dividing by the weights that apply keeps a hard clash from topping out at 90.
Every number carries a reason code; every weight lives in the profile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fnmatch import fnmatch

from ..model import CLEARANCE, HARD, Clash, Element, TestInfo
from ..profile import PRIORITIES, Profile


@dataclass(slots=True)
class Verdict:
    score: float
    priority: str
    components: dict[str, float]
    reasons: list[tuple[str, dict]] = field(default_factory=list)
    responsible: str = ""
    anchor: str = ""


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def mover_and_anchor(profile: Profile, a: str, b: str) -> tuple[str, str]:
    """Who moves: the more movable discipline. Ties resolve to code order, deterministically."""
    ma, mb = profile.mobility(a), profile.mobility(b)
    if ma == mb:
        first, second = sorted((a, b))
        return second, first
    return (a, b) if ma > mb else (b, a)


class Scorer:
    def __init__(self, profile: Profile, tests: list[TestInfo]) -> None:
        self.profile = profile
        self.weights = profile.weights()
        self.tests = {t.name: t for t in tests}
        self.size_sat = max(2.0, profile.num("score", "params", "size_saturation", default=20))
        self.ref_depth = max(0.01, profile.num("score", "params", "reference_depth_m", default=0.30))
        self.bands = profile.section("score", "bands")
        self.gates = profile.section("score").get("gates", [])

        # A small MEP run crossing a floor or wall it is expected to pass through (a riser, a feed) is
        # routed through a sleeve or opening far more often than it is a true conflict; nothing in the
        # exported geometry says whether that sleeve exists, so this only dampens the signal and says why,
        # it never drops the clash.
        sleeve = profile.section("score", "sleeve")
        self.sleeve_hosts = {str(c).lower() for c in sleeve.get("host_categories", [])}
        self.sleeve_crossings = {str(c).lower() for c in sleeve.get("crossing_categories", [])}
        self.sleeve_depth_tolerance = float(sleeve.get("depth_tolerance", 1.5))
        self.sleeve_damping = float(sleeve.get("damping", 1.0))
        self.sleeve_cap = sleeve.get("gate_floor_cap") or None
        # A conduit (or similar small run) that passes a floor or wall is normal practice when it is thin
        # compared with the host (the usual embedding rule is: outside dimension no more than a third of the
        # host thickness). Those drop to `small_cap`, not just to the sleeve cap.
        self.sleeves_modeled: int | None = None  # set by the pipeline when it checked the model for sleeves
        self.small_crossings = {str(c).lower() for c in sleeve.get("small_crossing_categories", [])}
        self.small_ratio = float(sleeve.get("small_ratio", 1 / 3))
        self.small_cap = sleeve.get("small_cap") or None

    def priority_of(self, score: float) -> str:
        if score >= self.bands["critical"]:
            return "critical"
        if score >= self.bands["high"]:
            return "high"
        if score >= self.bands["medium"]:
            return "medium"
        return "low"

    def _sleeve_host(self, a: Element, b: Element, depth: float) -> tuple[Element, Element] | None:
        """The host element, if this crossing looks like a clean through-penetration of a floor or wall
        by a small MEP run, rather than a true conflict. Proven by geometry, not just category: the depth
        has to be consistent with simply passing through the host's own thickness."""
        if not self.sleeve_hosts or not self.sleeve_crossings:
            return None
        for host, cross in ((a, b), (b, a)):
            if host.category.lower() not in self.sleeve_hosts or cross.category.lower() not in self.sleeve_crossings:
                continue
            if not host.min_dim:
                continue  # cannot prove it, so the clash keeps its full severity
            if depth <= host.min_dim * self.sleeve_depth_tolerance:
                return host, cross
        return None

    def score(self, group: list[Clash], crowding: float = 0.0, crowd: int = 0) -> Verdict:
        p = self.profile
        hard = [c for c in group if c.kind == HARD and c.depth > 0]
        clear = [c for c in group if c.kind == CLEARANCE]
        rep = max(group, key=lambda c: (c.depth, -c.distance))
        a, b = sorted((rep.a.discipline, rep.b.discipline))
        mover, anchor = mover_and_anchor(p, a, b)
        reasons: list[tuple[str, dict]] = []

        comps: dict[str, float] = {}
        applicable: set[str] = {"criticality", "immovability", "size", "crowding"}
        sleeve_cap: str | None = None

        max_depth = max((c.depth for c in hard), default=0.0)
        if hard:
            applicable.add("penetration")
            deep = max(hard, key=lambda c: c.depth)
            dims = [d for d in (deep.a.min_dim, deep.b.min_dim) if d]
            if dims:
                ratio = deep.depth / min(dims)
                comps["penetration"] = _clamp(ratio)
                reasons.append(("depth_rel", {"depth_mm": deep.depth * 1000, "pct": min(ratio, 1.0) * 100}))
            else:
                comps["penetration"] = _clamp(deep.depth / self.ref_depth)
                reasons.append(("depth_abs", {"depth_mm": deep.depth * 1000}))

            found = self._sleeve_host(deep.a, deep.b, deep.depth)
            if found is not None:
                host, cross = found
                comps["penetration"] *= self.sleeve_damping
                sleeve_cap = self.sleeve_cap
                if (self.small_cap and cross.category.lower() in self.small_crossings and cross.min_dim
                        and cross.min_dim <= host.min_dim * self.small_ratio):
                    sleeve_cap = self.small_cap
                    reasons.append(("embedded_small", {"host": host.category, "size_mm": cross.min_dim * 1000,
                                                       "host_mm": host.min_dim * 1000}))
                else:
                    code = "sleeve_missing" if self.sleeves_modeled == 0 else "sleeve_candidate"
                    reasons.append((code, {"host": host.category, "depth_mm": deep.depth * 1000}))

        crit = p.criticality(a, b)
        comps["criticality"] = crit
        reasons.append(("pair", {"a": a, "b": b, "crit": crit}))

        comps["immovability"] = 1.0 - min(p.mobility(a), p.mobility(b))
        if comps["immovability"] >= 0.6:
            reasons.append(("anchor", {"anchor": anchor, "mover": mover}))

        comps["size"] = _clamp(math.log1p(len(group)) / math.log1p(self.size_sat))
        if len(group) > 1:
            reasons.append(("size", {"count": len(group)}))

        comps["crowding"] = _clamp(crowding)
        if crowding > 0:
            radius = p.num("score", "params", "crowd_radius_m", default=5.0)
            reasons.append(("crowding", {"n": crowd, "radius": radius}))

        if clear:
            applicable.add("clearance")
            closeness = 0.0
            tight = None
            for c in clear:
                tol = self.tests[c.test].tolerance if c.test in self.tests else 0.0
                value = _clamp(1.0 - c.distance / tol) if tol > 0 else 0.5
                if value >= closeness:
                    closeness, tight = value, (c.distance, tol)
            comps["clearance"] = closeness
            if tight and tight[1] > 0:
                reasons.append(("clearance", {"dist_mm": tight[0] * 1000, "tol_mm": tight[1] * 1000}))

        total_w = sum(self.weights.get(k, 0.0) for k in applicable)
        raw = sum(self.weights.get(k, 0.0) * comps.get(k, 0.0) for k in applicable)
        score = round(100.0 * raw / total_w, 1) if total_w > 0 else 0.0

        priority = self.priority_of(score)
        for gate in self.gates:
            if self._gate_matches(gate, a, b, max_depth):
                floor = gate["floor"]
                if PRIORITIES.index(floor) < PRIORITIES.index(priority):
                    priority = floor
                    reasons.append(("gate", {"pair": f"{a}-{b}", "depth_mm": max_depth * 1000, "floor": floor}))
        if sleeve_cap and PRIORITIES.index(priority) < PRIORITIES.index(sleeve_cap):
            priority = sleeve_cap  # a sleeve candidate: no depth gate pushes it past this on its own

        return Verdict(score, priority, {k: round(v, 3) for k, v in comps.items()}, reasons, mover, anchor)

    @staticmethod
    def _gate_matches(gate: dict, a: str, b: str, depth: float) -> bool:
        pattern = str(gate.get("pair", "*-*"))
        if not (fnmatch(f"{a}-{b}", pattern) or fnmatch(f"{b}-{a}", pattern)):
            return False
        return depth >= float(gate.get("min_depth_m", 0.0))
