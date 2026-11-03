"""Model audit: checks that decide whether a clash analysis can be trusted at all.

Pure function over the model census. A model that is empty, unclassified, far from the others or in other units
makes every clash result involving it suspect, so these checks run before anybody reads a priority.
"""

from __future__ import annotations

import statistics
from typing import Any

from ..profile import Profile

_T = {
    "es": {
        "empty": "el modelo no tiene elementos: no aporta resultados",
        "unclassified": "sin disciplina: sus cruces quedan como 'Sin clasificar' (asígnela con nw_profile action=assign)",
        "disagree": "el nombre del archivo ({file}) y sus categorías ({cats}) apuntan a disciplinas distintas",
        "far": "está a {d:.0f} m del centro de los demás modelos: posible origen o coordenadas compartidas distintas",
        "no_overlap": "su caja no se superpone con la de ningún otro modelo",
        "size": "su tamaño ({e:.0f} m) es {r:.0f} veces el típico: posible unidad distinta",
        "huge": "su extensión ({e:.0f} m) es mayor que {m:.0f} m: posible unidad distinta o elementos perdidos lejos del edificio",
        "dup": "el archivo aparece cargado más de una vez",
        "missing": "no hay ningún modelo de {code}: los cruces {pairs} no tendrán resultados",
        "no_bbox": "el modelo no entregó su caja envolvente: no se pudo comprobar la co-ubicación",
        "ok": "sin hallazgos",
    },
    "en": {
        "empty": "the model has no elements: it contributes no results",
        "unclassified": "no discipline: its clashes stay 'Unclassified' (assign it with nw_profile action=assign)",
        "disagree": "the file name ({file}) and its categories ({cats}) point to different disciplines",
        "far": "it is {d:.0f} m from the centre of the other models: possible origin or shared-coordinates mismatch",
        "no_overlap": "its box does not overlap any other model's box",
        "size": "its size ({e:.0f} m) is {r:.0f} times the typical one: possible unit mismatch",
        "huge": "its extent ({e:.0f} m) exceeds {m:.0f} m: possible unit mismatch or stray elements far from the building",
        "dup": "the file is loaded more than once",
        "missing": "there is no {code} model: the {pairs} pairs will have no results",
        "no_bbox": "the model gave no bounding box: co-location could not be checked",
        "ok": "no findings",
    },
}


def _extent(b: list) -> float:
    (x0, y0, _), (x1, y1, _) = b
    return max(abs(x1 - x0), abs(y1 - y0))


def _centre(b: list) -> tuple[float, float]:
    (x0, y0, _), (x1, y1, _) = b
    return (x0 + x1) / 2, (y0 + y1) / 2


def _overlap(a: list, b: list) -> bool:
    (ax0, ay0, _), (ax1, ay1, _) = a
    (bx0, by0, _), (bx1, by1, _) = b
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def audit_models(models: list[dict[str, Any]], profile: Profile, lang: str) -> dict[str, Any]:
    t = _T[lang]
    max_offset = profile.num("audit", "max_offset_m", default=2000.0)
    max_extent = profile.num("audit", "max_extent_m", default=5000.0)
    size_ratio = profile.num("audit", "size_ratio", default=50.0)

    boxes = {m["name"]: m["bbox"] for m in models if m.get("bbox") and m.get("elements", 0) > 0}
    centres = {n: _centre(b) for n, b in boxes.items()}
    med = (statistics.median(c[0] for c in centres.values()), statistics.median(c[1] for c in centres.values())) if centres else None
    med_extent = statistics.median(_extent(b) for b in boxes.values()) if boxes else 0.0
    seen: dict[str, int] = {}
    for m in models:
        seen[m["name"]] = seen.get(m["name"], 0) + 1

    rows: list[dict[str, Any]] = []
    for m in models:
        name = m["name"]
        flags: list[dict[str, str]] = []

        def add(level: str, code: str, text: str) -> None:
            flags.append({"level": level, "code": code, "detail": text})

        if m.get("elements", 0) == 0:
            add("error", "empty", t["empty"])
        if seen[name] > 1:
            add("error", "duplicate", t["dup"])
        if m.get("proposed") == "OTHER":
            add("warn", "unclassified", t["unclassified"])
        if not m.get("agree", True):
            cats = ", ".join(f"{k} {int(v * 100)}%" for k, v in (m.get("by_categories") or {}).items())
            add("warn", "disagree", t["disagree"].format(file=m.get("by_file_name"), cats=cats))
        if m.get("elements", 0) > 0:
            b = boxes.get(name)
            if b is None:
                add("info", "no_bbox", t["no_bbox"])
            else:
                ext = _extent(b)
                if ext > max_extent:
                    add("warn", "huge", t["huge"].format(e=ext, m=max_extent))
                if med_extent > 0 and ext > 0 and len(boxes) >= 3:
                    ratio = max(ext / med_extent, med_extent / ext)
                    if ratio >= size_ratio:
                        add("warn", "size", t["size"].format(e=ext, r=ratio))
                if med is not None and len(boxes) >= 3:
                    c = centres[name]
                    dist = ((c[0] - med[0]) ** 2 + (c[1] - med[1]) ** 2) ** 0.5
                    if dist > max_offset:
                        add("warn", "far", t["far"].format(d=dist))
                    others = [o for o in boxes if o != name]
                    if others and not any(_overlap(b, boxes[o]) for o in others):
                        add("warn", "no_overlap", t["no_overlap"])
        rows.append({"name": name, "elements": m.get("elements", 0), "discipline": m.get("proposed"),
                     "findings": flags or [{"level": "ok", "code": "ok", "detail": t["ok"]}]})

    present = {m.get("proposed") for m in models if m.get("elements", 0) > 0}
    gaps = []
    for pair in profile.raw.get("expected_pairs", []):
        a, b = str(pair).split("-")
        miss = [c for c in (a, b) if c not in present]
        if miss:
            gaps.append({"pair": pair, "missing": miss})
    findings_global = []
    by_code: dict[str, list[str]] = {}
    for g in gaps:
        for code in g["missing"]:
            by_code.setdefault(code, []).append(g["pair"])
    for code, pairs in sorted(by_code.items()):
        findings_global.append({"level": "warn", "code": "missing_discipline",
                                "detail": t["missing"].format(code=code, pairs=", ".join(pairs))})

    levels = [f["level"] for r in rows for f in r["findings"]] + [f["level"] for f in findings_global]
    status = "fail" if "error" in levels else ("warn" if "warn" in levels else "ok")
    return {"status": status, "models": rows, "global": findings_global,
            "counts": {"error": levels.count("error"), "warn": levels.count("warn")}}
