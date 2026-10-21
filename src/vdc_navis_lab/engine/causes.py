"""Root causes: patterns that turn many issues into one decision.

Two detectors, each with a stated confidence and the evidence behind it:
* shared_element: one *movable* element is the party to many issues (reroute it once);
* repeated_detail: the same crossing signature recurs on several levels (fix the typical detail).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..profile import Profile

if TYPE_CHECKING:
    from .pipeline import Issue


@dataclass(slots=True)
class Cause:
    id: str
    kind: str
    confidence: float
    issue_ids: list[str]
    params: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)


def _h(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6].upper()


def _signature(issue: "Issue") -> str:
    rep = issue.rep
    sides = sorted(f"{s.category or '?'}/{s.family or s.name or '?'}" for s in (rep.a, rep.b))
    return " x ".join(sides)


def detect(issues: list["Issue"], profile: Profile) -> list[Cause]:
    shared_min = int(profile.num("causes", "shared_element_min", default=4))
    repeat_min = int(profile.num("causes", "repeat_levels_min", default=3))
    causes: list[Cause] = []

    # shared movable element
    by_element: dict[str, dict] = defaultdict(lambda: {"issues": set(), "name": "", "model": ""})
    for issue in issues:
        for clash in issue.clashes:
            for el in (clash.a, clash.b):
                if el.discipline == issue.responsible:
                    slot = by_element[el.key]
                    slot["issues"].add(issue.id)
                    slot["name"] = slot["name"] or el.name or el.family or el.key
                    slot["model"] = slot["model"] or el.model
    for key, slot in by_element.items():
        n = len(slot["issues"])
        if n >= shared_min:
            causes.append(Cause(
                id=f"CS-{_h(key)}", kind="shared_element",
                confidence=round(min(0.95, 0.45 + 0.05 * n), 2),
                issue_ids=sorted(slot["issues"]),
                params={"element": slot["name"], "n": n},
                evidence={"element_id": key, "model": slot["model"]},
            ))

    # repeated detail across levels
    by_sig: dict[tuple, list] = defaultdict(list)
    for issue in issues:
        by_sig[(issue.pair, _signature(issue))].append(issue)
    for (pair, sig), members in by_sig.items():
        levels = {m.level for m in members if m.level}
        if len(levels) >= repeat_min and len(members) >= repeat_min:
            causes.append(Cause(
                id=f"CR-{_h('|'.join(pair) + sig)}", kind="repeated_detail",
                confidence=round(min(0.9, 0.3 + 0.12 * len(levels)), 2),
                issue_ids=sorted(m.id for m in members),
                params={"signature": sig, "n": len(levels)},
                evidence={"pair": "-".join(pair), "levels": sorted(levels)},
            ))

    # Greedy set cover by reach. A shared element is the more actionable finding (one reroute),
    # so it wins ties against a repeated detail that covers the same issues.
    def weight(c: Cause) -> float:
        return c.confidence * len(c.issue_ids) * (1.5 if c.kind == "shared_element" else 1.0)

    causes.sort(key=lambda c: (-weight(c), c.id))
    return causes
