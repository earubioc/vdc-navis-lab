"""Compare two analyses by what the issues are made of, not by their ids.

Issues are matched by the overlap (Jaccard) of the element pairs they contain, so an issue
survives a re-clustering. An issue that disappears is reported as ``absent``, never as
``resolved``: the elements may have been deleted, hidden, or simply not tested this time.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..profile import PRIORITIES

MATCH_MIN = 0.5


def snapshot_of(result) -> dict[str, Any]:
    return {
        "schema": "vdc_navis_lab.snapshot/1",
        "created": result.created,
        "analysis_id": result.analysis_id,
        "source": result.source,
        "profile": {"name": result.profile_name, "checksum": result.profile_hash},
        "document": {k: v for k, v in result.document.items() if k in ("title", "fingerprint")},
        "tests": sorted(t.name for t in result.clashset.tests if not (t.status == "new" and t.count == 0)),
        "issues": [
            {"id": i.id, "pair": "-".join(i.pair), "level": i.level, "priority": i.priority, "score": i.score,
             "clashes": len(i.clashes), "element_pairs": [list(p) for p in i.element_pairs]}
            for i in result.issues
        ],
    }


def _jaccard(a: set, b: set) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    prev = before["issues"]
    cur = after["issues"]
    prev_sets = [{tuple(p) for p in i["element_pairs"]} for i in prev]
    cur_sets = [{tuple(p) for p in i["element_pairs"]} for i in cur]

    index: dict[tuple, list[int]] = defaultdict(list)
    for n, s in enumerate(prev_sets):
        for p in s:
            index[p].append(n)

    candidates = []
    for ci, cs in enumerate(cur_sets):
        seen = {pi for p in cs for pi in index.get(p, ())}
        for pi in seen:
            j = _jaccard(cs, prev_sets[pi])
            if j >= MATCH_MIN:
                candidates.append((j, ci, pi))
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    cur_to_prev: dict[int, int] = {}
    used_prev: set[int] = set()
    for j, ci, pi in candidates:
        if ci not in cur_to_prev and pi not in used_prev:
            cur_to_prev[ci] = pi
            used_prev.add(pi)

    persisting, new = [], []
    for ci, issue in enumerate(cur):
        if ci in cur_to_prev:
            old = prev[cur_to_prev[ci]]
            persisting.append({
                "id": issue["id"], "was": old["id"], "priority": issue["priority"], "was_priority": old["priority"],
                "score_delta": round(issue["score"] - old["score"], 1),
                "escalated": PRIORITIES.index(issue["priority"]) < PRIORITIES.index(old["priority"]),
                "clash_delta": issue["clashes"] - old["clashes"],
            })
        else:
            new.append({"id": issue["id"], "pair": issue["pair"], "level": issue["level"], "priority": issue["priority"]})
    absent = [
        {"id": old["id"], "pair": old["pair"], "level": old["level"], "priority": old["priority"]}
        for pi, old in enumerate(prev) if pi not in used_prev
    ]

    tests_before, tests_after = set(before.get("tests", [])), set(after.get("tests", []))
    coverage_shift = tests_before != tests_after
    notes = []
    if coverage_shift:
        notes.append("the set of tests with results differs between deliveries; 'absent' may mean 'not tested'")
    if before.get("profile", {}).get("checksum") != after.get("profile", {}).get("checksum"):
        notes.append("the profile changed between deliveries; scores are not strictly comparable")
    return {
        "before": {"analysis_id": before.get("analysis_id"), "issues": len(prev), "source": before.get("source")},
        "after": {"analysis_id": after.get("analysis_id"), "issues": len(cur), "source": after.get("source")},
        "new": new, "persisting_count": len(persisting),
        "escalated": [p for p in persisting if p["escalated"]],
        "worsened": sorted([p for p in persisting if p["score_delta"] >= 5], key=lambda p: -p["score_delta"])[:10],
        "absent": absent,
        "note_absent": "absent is not resolved: verify in the model before closing",
        "coverage_shift": coverage_shift, "notes": notes,
    }
