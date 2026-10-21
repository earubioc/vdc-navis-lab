"""Noise filter. Nothing is rejected silently: each rejection is counted by reason and passed."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..model import CLOSED_STATUSES, HARD, BBox, Clash, Element
from ..profile import Profile


@dataclass(slots=True)
class Screened:
    passed: list[Clash] = field(default_factory=list)
    rejected: list[tuple[Clash, str]] = field(default_factory=list)
    reasons: Counter = field(default_factory=Counter)
    by_test_in: Counter = field(default_factory=Counter)
    by_test_kept: Counter = field(default_factory=Counter)

    def silenced_tests(self, min_input: int = 5) -> list[str]:
        """Tests whose results were ALL filtered: that pair would otherwise read as clean on no evidence."""
        return sorted(
            t for t, n in self.by_test_in.items() if n >= min_input and self.by_test_kept.get(t, 0) == 0
        )


def _volume_inside(inner: BBox, outer: BBox) -> float:
    """Fraction of ``inner``'s volume lying inside ``outer`` (flat boxes get a 1 mm floor)."""
    frac = 1.0
    for i in range(3):
        lo, hi = inner[0][i], inner[1][i]
        size = max(hi - lo, 1e-3)
        overlap = min(hi, outer[1][i]) - max(lo, outer[0][i])
        if hi - lo < 1e-3:  # degenerate axis: inside or not
            frac *= 1.0 if outer[0][i] - 1e-3 <= lo <= outer[1][i] + 1e-3 else 0.0
        else:
            frac *= max(0.0, overlap) / size
    return frac


class NoiseScreen:
    def __init__(self, profile: Profile) -> None:
        cfg = profile.section("noise")
        self.min_depth = float(cfg.get("min_depth_m", 0.005))
        self.drop_closed = bool(cfg.get("drop_closed", True))
        self.self_assembly = bool(cfg.get("self_assembly", True))
        self.opening_cats = {c.lower() for c in cfg.get("opening_categories", [])}
        self.opening_hints = [h.lower() for h in cfg.get("opening_family_hints", [])]
        self.host_cats = {c.lower() for c in cfg.get("host_types", [])}
        self.contain = float(cfg.get("opening_contain_ratio", 0.8))

    def _is_opening(self, el: Element) -> bool:
        if el.category.lower() in self.opening_cats:
            return True
        text = f"{el.family} {el.name}".lower()
        return any(h in text for h in self.opening_hints)

    def _designed_opening(self, a: Element, b: Element) -> bool:
        """An opening inside its host. A category name alone proves nothing: the geometry must agree."""
        for opening, host in ((a, b), (b, a)):
            if not self._is_opening(opening) or host.category.lower() not in self.host_cats:
                continue
            if opening.bbox is None or host.bbox is None:
                continue  # cannot prove it, so keep the clash
            if _volume_inside(opening.bbox, host.bbox) >= self.contain:
                return True
        return False

    def reason(self, clash: Clash) -> str:
        if self.drop_closed and clash.status in CLOSED_STATUSES:
            return "closed"
        if clash.kind == HARD and clash.depth < self.min_depth:
            return "shallow"
        if self.self_assembly and clash.a.key == clash.b.key and clash.a.model == clash.b.model:
            return "self_assembly"
        if self._designed_opening(clash.a, clash.b):
            return "designed_opening"
        return ""

    def run(self, clashes: list[Clash]) -> Screened:
        out = Screened()
        for clash in clashes:
            out.by_test_in[clash.test] += 1
            why = self.reason(clash)
            if why:
                out.rejected.append((clash, why))
                out.reasons[why] += 1
            else:
                out.passed.append(clash)
                out.by_test_kept[clash.test] += 1
        return out
