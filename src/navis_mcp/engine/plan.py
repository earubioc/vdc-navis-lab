"""Work plan, discipline matrix and hotspots, derived from one analysis."""

from __future__ import annotations

import math
from collections import defaultdict

from ..profile import PRIORITIES, Profile
from .pipeline import AnalysisResult, Issue


def matrix(result: AnalysisResult) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for issue in result.issues:
        row = out.setdefault("-".join(issue.pair), {**{p: 0 for p in PRIORITIES}, "issues": 0, "clashes": 0})
        row[issue.priority] += 1
        row["issues"] += 1
        row["clashes"] += len(issue.clashes)
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["critical"], -kv[1]["high"], -kv[1]["issues"], kv[0])))


def hotspots(result: AnalysisResult, cell_m: float = 10.0, limit: int = 5) -> list[dict]:
    cells: dict[tuple, dict] = defaultdict(lambda: {"score": 0.0, "issues": 0, "disciplines": set()})
    for issue in result.issues:
        key = (math.floor(issue.centroid[0] / cell_m), math.floor(issue.centroid[1] / cell_m), issue.level)
        slot = cells[key]
        slot["score"] += issue.score
        slot["issues"] += 1
        slot["disciplines"].update(issue.pair)
    ranked = sorted(cells.items(), key=lambda kv: (-kv[1]["score"], kv[0][:2]))[:limit]
    return [
        {"center": [round((k[0] + 0.5) * cell_m, 1), round((k[1] + 0.5) * cell_m, 1)], "level": k[2],
         "issues": v["issues"], "total_score": round(v["score"], 1), "disciplines": sorted(v["disciplines"] - {"OTHER"})}
        for k, v in ranked
    ]


def work_packages(result: AnalysisResult, profile: Profile, package_size: int = 15) -> list[dict]:
    """One package per (responsible discipline, level), split so a coordination session stays workable."""
    lang = result.lang
    decision_of = {iid: d.id for d in result.decisions for iid in d.issue_ids}
    buckets: dict[tuple[str, str], list[Issue]] = defaultdict(list)
    for issue in result.issues:
        buckets[(issue.responsible, issue.level)].append(issue)
    packages = []
    for (resp, level), members in buckets.items():
        members.sort(key=lambda i: i.rank_key)
        chunks = [members[i:i + package_size] for i in range(0, len(members), package_size)]
        for part, chunk in enumerate(chunks, 1):
            counts = {p: sum(1 for i in chunk if i.priority == p) for p in PRIORITIES}
            where = level or ("sin nivel" if lang == "es" else "no level")
            suffix = f" ({part}/{len(chunks)})" if len(chunks) > 1 else ""
            verb = "Coordinar" if lang == "es" else "Coordinate"
            packages.append({
                "title": f"{verb} {profile.label(resp, lang)} · {where}{suffix}",
                "responsible": resp, "level": level, "issues": [i.id for i in chunk],
                "decisions": len({decision_of[i.id] for i in chunk}), "per_band": counts,
                "top_score": chunk[0].score, "_key": (PRIORITIES.index(chunk[0].priority), -sum(i.score for i in chunk)),
            })
    packages.sort(key=lambda p: p["_key"])
    for n, pkg in enumerate(packages, 1):
        pkg["id"] = f"WP-{n:02d}"
        del pkg["_key"]
    return packages
