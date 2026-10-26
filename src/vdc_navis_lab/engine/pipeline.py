"""analyze(): ClashSet in, ranked issues, causes, decisions and coverage out.

    tag -> filter -> cluster -> crowding -> score -> causes -> decisions -> rank

Tagging is first (everything keys off discipline). Filtering precedes clustering so that
noise cannot inflate a cluster into a fake systemic problem. Congestion is measured on
issues, not raw clashes, so one messy crossing does not read as a crowded zone.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import product

from .. import texts
from ..model import CLEARANCE, HARD, Clash, ClashSet, Element, Point, dist
from ..profile import PRIORITIES, Profile
from .causes import Cause, detect
from .cluster import cluster, pair_key
from .screen import Screened, NoiseScreen
from .scoring import Scorer
from .tagging import Tagger

_NEIGHBOURS = list(product((-1, 0, 1), repeat=3))
_ID_SUFFIX = re.compile(r',\s*#\d+\s*$')


def level_label(raw: str) -> str:
    """`Level "2th FLOOR", #9946` -> `2th FLOOR`."""
    text = _ID_SUFFIX.sub("", (raw or "").strip()).strip().strip('"').strip()
    if text.lower().startswith("level "):
        rest = text[6:].strip().strip('"').strip()
        if rest and not rest.isdigit():
            text = rest
    return text


@dataclass(slots=True)
class Issue:
    id: str
    identity: str
    clashes: list[Clash]
    pair: tuple[str, str]
    level: str
    centroid: Point
    span: float
    score: float
    priority: str
    components: dict[str, float]
    reasons: list[tuple[str, dict]]
    responsible: str
    anchor: str
    element_pairs: list[tuple[str, str]]
    cause_ids: list[str] = field(default_factory=list)

    @property
    def rep(self) -> Clash:
        return max(self.clashes, key=lambda c: (c.depth, -c.distance))

    @property
    def max_depth(self) -> float:
        return max((c.depth for c in self.clashes), default=0.0)

    @property
    def rank_key(self) -> tuple[int, float, str]:
        return (PRIORITIES.index(self.priority), -self.score, self.id)


@dataclass(slots=True)
class Decision:
    id: str
    cause_id: str
    issue_ids: list[str]
    priority: str
    score: float


@dataclass(slots=True)
class Coverage:
    tests_count: int = 0
    tests_ran: int = 0
    never_run: list[str] = field(default_factory=list)
    expected_pairs: list[str] = field(default_factory=list)
    pairs_without_results: list[str] = field(default_factory=list)
    silenced_tests: list[str] = field(default_factory=list)
    unclassified: dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    skipped: int = 0  # results dropped because an element no longer exists in the model
    skipped_open: int | None = None  # of those, the ones still open; None when the source did not say
    sleeves_modeled: int | None = None  # modeled sleeve/opening elements found; None when it was not checked

    @property
    def complete(self) -> bool:
        return not (self.never_run or self.pairs_without_results or self.silenced_tests
                    or self.truncated or (self.skipped if self.skipped_open is None else self.skipped_open))


@dataclass(slots=True)
class AnalysisResult:
    analysis_id: str
    created: float
    lang: str
    profile_name: str
    profile_hash: str
    source: str
    document: dict
    raw_count: int
    filtering: Counter
    issues: list[Issue]
    causes: list[Cause]
    decisions: list[Decision]
    coverage: Coverage
    clashset: ClashSet

    def issue(self, issue_id: str) -> Issue | None:
        wanted = issue_id.strip().upper()
        return next((i for i in self.issues if i.id.upper() == wanted), None)

    def per_band(self) -> dict[str, int]:
        count = Counter(i.priority for i in self.issues)
        return {p: count.get(p, 0) for p in PRIORITIES}


def _identity(pairs: list[tuple[str, str]]) -> str:
    return hashlib.sha1("|".join(f"{a}~{b}" for a, b in pairs).encode("utf-8")).hexdigest()


def _congestion(groups: list[list[Clash]], radius: float, saturation: float) -> list[tuple[float, int]]:
    """Per group: (0..1 crowding, distinct disciplines within `radius` of its centre)."""
    centres = []
    for g in groups:
        n = len(g)
        centres.append((sum(c.point[0] for c in g) / n, sum(c.point[1] for c in g) / n, sum(c.point[2] for c in g) / n))
    cell = max(radius, 1e-6)
    grid: dict[tuple, list[int]] = defaultdict(list)
    for i, p in enumerate(centres):
        grid[tuple(math.floor(v / cell) for v in p)].append(i)
    out = []
    for i, p in enumerate(centres):
        cx, cy, cz = (math.floor(v / cell) for v in p)
        discs: set[str] = set(pair_key(groups[i][0]))
        for dx, dy, dz in _NEIGHBOURS:
            for j in grid.get((cx + dx, cy + dy, cz + dz), ()):
                if dist(p, centres[j]) <= radius:
                    discs.update(pair_key(groups[j][0]))
        discs.discard("OTHER")
        span = max(1.0, saturation - 2)
        out.append((max(0.0, min(1.0, (len(discs) - 2) / span)), len(discs)))
    return out


def _coverage(cs: ClashSet, profile: Profile, flt: Screened, unclassified: dict[str, int],
              seen_pairs: set[tuple[str, str]]) -> Coverage:
    cov = Coverage(truncated=cs.truncated, skipped=cs.skipped, skipped_open=cs.skipped_open,
                   sleeves_modeled=cs.sleeves_modeled,
                   unclassified=dict(sorted(unclassified.items(), key=lambda kv: -kv[1])[:8]))
    cov.tests_count = len(cs.tests)
    for t in cs.tests:
        if t.status == "new" and t.count == 0:
            cov.never_run.append(t.name)
        else:
            cov.tests_ran += 1
    required = [tuple(sorted(str(p).split("-"))) for p in profile.raw.get("expected_pairs", [])]
    cov.expected_pairs = ["-".join(p) for p in required]
    cov.pairs_without_results = ["-".join(p) for p in required if p not in seen_pairs]
    cov.silenced_tests = flt.silenced_tests()
    return cov


def analyze(cs: ClashSet, profile: Profile, lang: str | None = None) -> AnalysisResult:
    lang = lang or profile.lang
    for c in cs.clashes:  # a profile change must be able to re-tag the same data
        c.a.discipline = c.b.discipline = ""
    unclassified = Tagger(profile).tag(cs.clashes)
    flt = NoiseScreen(profile).run(cs.clashes)
    seen_pairs = {pair_key(c) for c in cs.clashes}

    eps = profile.num("cluster", "eps_m", default=1.5)
    max_span = profile.num("cluster", "max_span_m", default=12.0)
    groups = cluster(flt.passed, eps, max_span)

    radius = profile.num("score", "params", "crowd_radius_m", default=5.0)
    sat = profile.num("score", "params", "crowd_saturation", default=5)
    crowd = _congestion(groups, radius, sat)
    scorer = Scorer(profile, cs.tests)
    scorer.sleeves_modeled = cs.sleeves_modeled

    issues: list[Issue] = []
    used: set[str] = set()
    for group, (cong, n_disc) in zip(groups, crowd):
        verdict = scorer.score(group, cong, n_disc)
        pairs = sorted({tuple(sorted((c.a.key, c.b.key))) for c in group})
        identity = _identity(pairs)
        issue_id = f"NW-{identity[:6].upper()}"
        while issue_id in used:
            issue_id += "x"
        used.add(issue_id)
        levels = Counter(level_label(c.level or c.a.level or c.b.level) for c in group)
        levels.pop("", None)
        n = len(group)
        issues.append(Issue(
            id=issue_id, identity=identity, clashes=group, pair=pair_key(group[0]),
            level=levels.most_common(1)[0][0] if levels else "",
            centroid=(sum(c.point[0] for c in group) / n, sum(c.point[1] for c in group) / n,
                      sum(c.point[2] for c in group) / n),
            span=_span(group), score=verdict.score, priority=verdict.priority, components=verdict.components,
            reasons=verdict.reasons, responsible=verdict.responsible, anchor=verdict.anchor, element_pairs=pairs,
        ))

    causes = detect(issues, profile)
    decisions = _decisions(issues, causes)
    issues.sort(key=lambda i: i.rank_key)

    return AnalysisResult(
        analysis_id=uuid.uuid4().hex[:10], created=time.time(), lang=lang, profile_name=profile.name,
        profile_hash=profile.checksum, source=cs.source, document=cs.document, raw_count=len(cs.clashes),
        filtering=flt.reasons, issues=issues, causes=causes, decisions=decisions,
        coverage=_coverage(cs, profile, flt, unclassified, seen_pairs), clashset=cs,
    )


def _span(group: list[Clash]) -> float:
    pts = [c.point for c in group]
    return round(max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)), 2)


def _decisions(issues: list[Issue], causes: list[Cause]) -> list[Decision]:
    """Fold issues that one cause explains into a single decision; the rest stand alone."""
    by_id = {i.id: i for i in issues}
    chosen: dict[str, Cause] = {}
    for cause in causes:  # already ordered by confidence x reach
        for iid in cause.issue_ids:
            chosen.setdefault(iid, cause)
        for iid in cause.issue_ids:
            by_id[iid].cause_ids.append(cause.id)
    grouped: dict[str, list[str]] = defaultdict(list)
    for issue in issues:
        cause = chosen.get(issue.id)
        grouped[cause.id if cause else issue.id].append(issue.id)
    decisions = []
    for key, ids in grouped.items():
        members = [by_id[i] for i in ids]
        best = min(members, key=lambda m: m.rank_key)
        decisions.append(Decision(id=key, cause_id=key if key.startswith("C") else "", issue_ids=sorted(ids),
                                  priority=best.priority, score=best.score))
    decisions.sort(key=lambda d: (PRIORITIES.index(d.priority), -d.score, d.id))
    return decisions
