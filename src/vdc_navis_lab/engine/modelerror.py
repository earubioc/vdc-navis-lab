"""Elements that were modelled in a way that cannot be built are modelling errors, not coordination conflicts.

Two kinds, both profile-driven:

* ``through``: an element that runs through the structure on both sides (see below);
* ``finish``: an architectural floor finish that overlaps structure (a column, a beam, a slab, a wall) instead of
  being cut around it. Nobody builds a finish through a column, but it makes quantities unreliable.

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
    kind: str = "through"          # through | finish


def check(profile: Profile, a: Element, b: Element) -> ModelError | None:
    p = profile.section("score", "model_error")
    elements = {str(c).lower() for c in p.get("element_categories", [])}
    hosts = {str(c).lower() for c in p.get("host_categories", [])}
    disciplines = {str(d) for d in p.get("disciplines", [])}
    minimum = float(p.get("min_overhang_m", 1.0))
    for el, host in ((a, b), (b, a)):
        if not elements or not hosts:
            break
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
    finishes = {str(c).lower() for c in p.get("finish_categories", [])}
    finish_hosts = {str(c).lower() for c in p.get("finish_host_categories", [])}
    host_disciplines = {str(d) for d in p.get("finish_host_disciplines", [])}
    if finishes and finish_hosts:
        for el, host in ((a, b), (b, a)):
            if el.category.lower() in finishes and host.category.lower() in finish_hosts \
                    and (not disciplines or el.discipline in disciplines) \
                    and (not host_disciplines or host.discipline in host_disciplines):
                return ModelError(el, host, 0.0, 0.0, "finish")
    return None
