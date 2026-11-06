"""The saved form of an analysis (nw_snapshot save). Comparing two of them is a Pro capability."""

from __future__ import annotations

from typing import Any


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
