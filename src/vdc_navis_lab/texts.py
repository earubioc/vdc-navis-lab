"""Human-readable text. Engine results carry codes; wording lives here."""

from __future__ import annotations

from typing import Any

PRIORITY = {
    "es": {"critical": "CRÍTICO", "high": "ALTO", "medium": "MEDIO", "low": "BAJO"},
    "en": {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"},
}

REASONS = {
    "es": {
        "depth_rel": "penetra {depth_mm:.0f} mm, el {pct:.0f}% de la dimensión menor del elemento",
        "depth_abs": "penetra {depth_mm:.0f} mm (sin caja envolvente para dimensionarlo)",
        "pair": "{a} contra {b} es un cruce de criticidad {crit:.0%}",
        "anchor": "{anchor} casi no puede moverse; le corresponde a {mover} ajustarse",
        "size": "{count} cruces colapsan en este problema",
        "crowding": "{n} disciplinas coinciden en un radio de {radius:.0f} m",
        "clearance": "viola la holgura exigida (a {dist_mm:.0f} mm de {tol_mm:.0f} mm)",
        "gate": "regla de piso: {pair} con {depth_mm:.0f} mm de penetración no baja de {floor}",
    },
    "en": {
        "depth_rel": "penetrates {depth_mm:.0f} mm, {pct:.0f}% of the element's smallest dimension",
        "depth_abs": "penetrates {depth_mm:.0f} mm (no bounding box to size it against)",
        "pair": "{a} against {b} is a {crit:.0%} criticality crossing",
        "anchor": "{anchor} can hardly move; {mover} has to adjust",
        "size": "{count} clashes collapse into this issue",
        "crowding": "{n} disciplines meet within {radius:.0f} m",
        "clearance": "violates required clearance ({dist_mm:.0f} mm of {tol_mm:.0f} mm)",
        "gate": "floor rule: {pair} at {depth_mm:.0f} mm penetration is never below {floor}",
    },
}

ACTIONS = {
    "es": {
        "move": "{mover} debe reencaminarse o desplazarse; {anchor} se mantiene.",
        "clearance": "Restituir la holgura de mantenimiento: {mover} debe separarse de {anchor}.",
        "cause_shared": "Resolver {element} en una sola decisión cierra {n} problemas.",
        "cause_repeat": "Corregir el detalle tipo ({signature}) una vez y replicarlo en {n} niveles.",
    },
    "en": {
        "move": "{mover} must reroute or shift; {anchor} stays.",
        "clearance": "Restore the maintenance clearance: {mover} must move away from {anchor}.",
        "cause_shared": "Resolving {element} in one decision closes {n} issues.",
        "cause_repeat": "Fix the typical detail ({signature}) once and replicate it on {n} levels.",
    },
}

CAUSES = {
    "es": {
        "shared_element": "{element} interviene como elemento móvil en {n} problemas",
        "repeated_detail": "El mismo cruce ({signature}) se repite en {n} niveles",
    },
    "en": {
        "shared_element": "{element} is the movable party in {n} issues",
        "repeated_detail": "The same crossing ({signature}) repeats on {n} levels",
    },
}

FILTER = {
    "es": {
        "shallow": "profundidad menor que la tolerancia",
        "self_assembly": "elemento contra su propio ensamble",
        "designed_opening": "abertura prevista contenida en su anfitrión",
        "closed": "ya aprobado o resuelto",
    },
    "en": {
        "shallow": "depth below tolerance",
        "self_assembly": "element against its own assembly",
        "designed_opening": "designed opening contained in its host",
        "closed": "already approved or resolved",
    },
}


def render(table: dict[str, dict[str, str]], lang: str, code: str, args: dict[str, Any]) -> str:
    template = table.get(lang, table["en"]).get(code) or table["en"].get(code, code)
    try:
        return template.format(**args)
    except (KeyError, ValueError):
        return template
