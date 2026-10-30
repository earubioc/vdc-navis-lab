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
        "sleeve_candidate": "cruce recto de {depth_mm:.0f} mm contra {host}: candidato a paso con manguito, verificar si existe",
        "sleeve_missing": "cruce recto de {depth_mm:.0f} mm contra {host}: no hay manguitos ni aberturas modelados, el paso queda pendiente de manguito o abertura aprobada por estructura",
        "beam_pass_ok": "pase por viga ({kind}, {angle:.0f}° contra el eje): en el {along:.0f} % del vano y el {across:.0f} % del canto, diámetro {ratio:.0f} % de la dimensión; cumple la geometría, requiere aval de estructura",
        "beam_pass_longitudinal": "el elemento corre dentro de la viga, casi paralelo a su eje ({angle:.0f}°): no es un pase",
        "beam_pass_diagonal": "cruza la viga en diagonal ({angle:.0f}° contra el eje): no es un pase transversal",
        "beam_pass_span": "el pase queda al {along:.0f} % del vano, fuera del tercio medio",
        "beam_pass_zone": "el pase queda al {across:.0f} % de la sección, fuera del tercio medio",
        "beam_pass_size": "el diámetro es el {ratio:.0f} % de la dimensión de la viga, más de lo permitido para un pase",
        "beam_pass_level": "pase por viga que no cumple: se clasifica como {level}",
        "beam_end": "el tramo vertical termina {mm:.0f} mm dentro de la viga ({pct:.0f} % del canto): no la atraviesa",
        "embedded_small": "elemento de {size_mm:.0f} mm embebido en {host} de {host_mm:.0f} mm: embebido normal (no pasa de un tercio del espesor)",
        "model_error": "{element} continúa {above_m:.1f} m por encima y {below_m:.1f} m por debajo de {host}: lo atraviesa; es un error de modelado, no se construiría así",
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
        "sleeve_candidate": "clean {depth_mm:.0f} mm crossing of {host}: sleeve candidate, verify one exists",
        "sleeve_missing": "clean {depth_mm:.0f} mm crossing of {host}: no sleeves or openings are modelled, so the passage still needs a sleeve or an opening approved by structure",
        "beam_pass_ok": "beam passage ({kind}, {angle:.0f}° to the axis): at {along:.0f}% of the span and {across:.0f}% of the section, diameter {ratio:.0f}% of the dimension; meets the geometry, needs structural approval",
        "beam_pass_longitudinal": "the element runs inside the beam, nearly parallel to its axis ({angle:.0f}°): not a passage",
        "beam_pass_diagonal": "crosses the beam at an angle ({angle:.0f}° to the axis): not a transversal passage",
        "beam_pass_span": "the passage sits at {along:.0f}% of the span, outside the middle third",
        "beam_pass_zone": "the passage sits at {across:.0f}% of the section, outside the middle third",
        "beam_pass_size": "the diameter is {ratio:.0f}% of the beam dimension, more than a passage allows",
        "beam_pass_level": "beam passage that does not comply: classified as {level}",
        "beam_end": "the vertical run stops {mm:.0f} mm inside the beam ({pct:.0f}% of its depth): it does not cross it",
        "embedded_small": "{size_mm:.0f} mm run embedded in a {host_mm:.0f} mm {host}: ordinary embedding (within a third of the thickness)",
        "model_error": "{element} continues {above_m:.1f} m above and {below_m:.1f} m below the {host}: it runs through it; a modelling error, it would not be built this way",
    },
}

ACTIONS = {
    "es": {
        "move": "{mover} debe reencaminarse o desplazarse; {anchor} se mantiene.",
        "move_ELE": "{mover} reencamina el recorrido (por el afinado o fuera de la sección del elemento de {anchor}); si el paso es inevitable, pide el aval de {anchor}.",
        "move_PLB": "{mover} reencamina la tubería o cambia la cota; si el paso es inevitable, pide a {anchor} la abertura o el manguito con su aval.",
        "move_HVAC": "{mover} reencamina el ducto o ajusta su sección y cota; si el paso es inevitable, pide a {anchor} una abertura con refuerzo aprobado.",
        "move_DRN": "{mover} ajusta la pendiente y el recorrido del drenaje; si el paso es inevitable, pide a {anchor} el manguito con su aval.",
        "move_FIRE": "{mover} reencamina la red; si el paso es inevitable, pide a {anchor} el manguito o la abertura sellada con su aval.",
        "move_ARC": "{mover} ajusta el elemento o su cota; {anchor} se mantiene.",
        "beam_pass_ok": "{mover} solicita a {anchor} el aval del pase por la viga (cumple la geometría) y lo deja documentado; sin aval no se ejecuta.",
        "beam_pass_fail": "{mover} reencamina para cruzar la viga de forma transversal, en el tercio medio del canto y del vano y con el diámetro permitido, o acuerda otra solución con {anchor}; así no es aceptable.",
        "beam_end": "{mover} ajusta el tramo para que no entre en la viga; es un ajuste menor del recorrido.",
        "embedded": "Embebido normal: no requiere coordinación. {mover} deja el paso indicado en sus planos.",
        "model_error": "Error de modelado: {mover} corta o ajusta el elemento por nivel en su modelo de origen. No requiere coordinación en obra.",
        "sleeve_missing": "{mover} pide a {anchor} el manguito o la abertura de este paso, lo modela y espera su aval; no hay ninguno modelado.",
        "sleeve_check": "{mover} verifica que el paso tenga manguito o abertura aprobada por {anchor}, y lo modela si falta.",
        "clearance": "Restituir la holgura de mantenimiento: {mover} debe separarse de {anchor}.",
        "cause_shared": "Resolver {element} en una sola decisión cierra {n} problemas.",
        "cause_repeat": "Corregir el detalle tipo ({signature}) una vez y replicarlo en {n} niveles.",
    },
    "en": {
        "move": "{mover} must reroute or shift; {anchor} stays.",
        "move_ELE": "{mover} reroutes the run (through the topping or clear of the {anchor} member); if the passage is unavoidable, get {anchor}'s approval.",
        "move_PLB": "{mover} reroutes the pipe or changes its level; if the passage is unavoidable, ask {anchor} for the opening or sleeve with its approval.",
        "move_HVAC": "{mover} reroutes the duct or adjusts its size and level; if the passage is unavoidable, ask {anchor} for an opening with approved reinforcement.",
        "move_DRN": "{mover} adjusts the drain's slope and route; if the passage is unavoidable, ask {anchor} for the sleeve with its approval.",
        "move_FIRE": "{mover} reroutes the network; if the passage is unavoidable, ask {anchor} for the sleeve or sealed opening with its approval.",
        "move_ARC": "{mover} adjusts the element or its level; {anchor} stays.",
        "beam_pass_ok": "{mover} asks {anchor} to approve the passage through the beam (the geometry complies) and records it; without approval it is not built.",
        "beam_pass_fail": "{mover} reroutes to cross the beam transversally, in the middle third of its depth and span and within the allowed diameter, or agrees another solution with {anchor}; as modelled it is not acceptable.",
        "beam_end": "{mover} adjusts the run so it does not enter the beam; a minor change of route.",
        "embedded": "Ordinary embedding: no coordination needed. {mover} shows the passage on its drawings.",
        "model_error": "Modelling error: {mover} cuts or adjusts the element by level in its source model. No site coordination needed.",
        "sleeve_missing": "{mover} asks {anchor} for the sleeve or opening at this passage, models it and waits for approval; none is modelled.",
        "sleeve_check": "{mover} checks that the passage has a sleeve or an opening approved by {anchor}, and models it if missing.",
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
