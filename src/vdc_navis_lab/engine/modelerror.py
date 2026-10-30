"""An element that runs through the structure on both sides is a modelling error, not a coordination conflict.

Typical case: a wall or a finish drawn from the first floor to the roof in one piece, so it crosses every slab on the
way. Nobody will build the slab and then open it to let the finish through; the author has to cut the element by
level. The clash is real in the model and must be fixed there, but it does not call for a coordination decision on
site, so it is capped (``[score.model_error]``) instead of competing with true conflicts.

The test is geometric: the element continues at least ``min_overhang_m`` above and below the host (a slab or a
beam). A normal storey-high wall that rests on a slab overlaps it by centimetres, never by a metre on each side.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Element
from ..profile import Profile


@dataclass(slots=True)
class ModelError:
    element: Element
    host: Element
    above_m: float
    below_m: float


def check(profile: Profile, a: Element, b: Element) -> ModelError | None:
    p = profile.section("score", "model_error")
    elements = {str(c).lower() for c in p.get("element_categories", [])}
    hosts = {str(c).lower() for c in p.get("host_categories", [])}
    disciplines = {str(d) for d in p.get("disciplines", [])}
    if not elements or not hosts:
        return None
    minimum = float(p.get("min_overhang_m", 1.0))
    for el, host in ((a, b), (b, a)):
        if el.category.lower() not in elements or host.category.lower() not in hosts:
            continue
        if disciplines and el.discipline not in disciplines:
            continue
        if not el.bbox or not host.bbox:
            continue
        below = host.bbox[0][2] - el.bbox[0][2]
        above = el.bbox[1][2] - host.bbox[1][2]
        if below >= minimum and above >= minimum:
            return ModelError(el, host, above, below)
    return None
