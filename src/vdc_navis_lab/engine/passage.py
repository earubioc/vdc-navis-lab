"""Is a small run (conduit, pipe) crossing a concrete beam a passage structure could approve?

A passage through a beam is never "approved" here: that is a structural decision. What this module does is measure
the geometric conditions that decision usually starts from, using the oriented boxes the add-in extracted:

* the run crosses the beam transversally (not along it, not at an oblique angle);
* it crosses inside the middle third of the beam's depth and of its span;
* its diameter is no more than a fraction of the beam's depth.

A vertical run through a horizontal beam is judged on the beam's width instead of its depth. Every threshold comes
from the profile (``[score.beam_pass]``); the defaults are a starting point to confirm with the structural designer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..model import Element, Point
from ..profile import Profile


@dataclass(slots=True)
class Passage:
    kind: str                       # transversal | diagonal | longitudinal | vertical
    angle_deg: float                # between the run and the beam axis, 0..90
    along: float                    # position along the span, 0..1
    across: float                   # position across the checked dimension (depth, or width for a vertical run), 0..1
    diameter_ratio: float           # run diameter / checked dimension
    failures: list[str] = field(default_factory=list)  # codes: longitudinal, diagonal, span, zone, size
    through: float | None = None    # share of the beam depth the run covers (only measured for vertical runs)

    @property
    def ok(self) -> bool:
        return not self.failures


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _params(profile: Profile) -> dict:
    return profile.section("score", "beam_pass")


def applicable(profile: Profile, a: Element, b: Element) -> tuple[Element, Element] | None:
    """(beam, run) when this pair is a beam crossed by a run the profile covers, and both have an oriented box."""
    p = _params(profile)
    hosts = {str(c).lower() for c in p.get("host_categories", [])}
    runs = {str(c).lower() for c in p.get("crossing_categories", [])}
    if not hosts or not runs:
        return None
    for beam, run in ((a, b), (b, a)):
        if beam.category.lower() in hosts and run.category.lower() in runs and beam.obb and run.obb:
            return beam, run
    return None


def assess(profile: Profile, beam: Element, run: Element, point: Point) -> Passage | None:
    """None when the geometry cannot support a judgement (a stub, a vertical 'beam'): the clash then keeps its score."""
    p = _params(profile)
    lo, hi = (float(x) for x in p.get("middle_zone", (1 / 3, 2 / 3)))
    max_ratio = float(p.get("max_diameter_ratio", 1 / 3))
    transversal_min = float(p.get("transversal_min_angle_deg", 70.0))
    longitudinal_max = float(p.get("longitudinal_max_angle_deg", 25.0))
    min_len_ratio = float(p.get("min_run_length_ratio", 2.0))

    bu, bh, bc = beam.obb["u"], beam.obb["h"], beam.obb["c"]
    ru, rh = run.obb["u"], run.obb["h"]
    span = 2 * bh[0]
    diameter = 2 * max(rh[1], rh[2])
    if span <= 0 or diameter <= 0:
        return None
    if 2 * rh[0] < min_len_ratio * diameter:
        return None  # a stub or a fitting: its long axis says nothing reliable
    if abs(bu[0][2]) > 0.7:
        return None  # a beam standing up is a column in disguise; not this rule

    up = (0.0, 0.0, 1.0)
    # beam section axes: the more vertical one is the depth, the other the width
    if abs(_dot(bu[1], up)) >= abs(_dot(bu[2], up)):
        depth_axis, depth, width_axis, width = bu[1], 2 * bh[1], bu[2], 2 * bh[2]
    else:
        depth_axis, depth, width_axis, width = bu[2], 2 * bh[2], bu[1], 2 * bh[1]
    if depth <= 0 or width <= 0:
        return None

    cos_t = min(1.0, abs(_dot(ru[0], bu[0])))
    angle = math.degrees(math.acos(cos_t))
    run_vertical = abs(_dot(ru[0], up)) > 0.9

    rel = _sub(point, bc)
    along = _dot(rel, bu[0]) / span + 0.5

    through = None
    if run_vertical:
        # A vertical run that stops inside the beam (a drop from the slab, a box, a stub) is not a passage through
        # the beam: only one that covers its whole depth is a hole in it.
        half = sum(rh[i] * abs(_dot(ru[i], depth_axis)) for i in range(3))
        mid = _dot(_sub(run.obb["c"], bc), depth_axis)
        overlap = max(0.0, min(mid + half, depth / 2) - max(mid - half, -depth / 2))
        through = overlap / depth
        if through < float(p.get("min_through_ratio", 0.9)):
            return None
        kind = "vertical"
        across = _dot(rel, width_axis) / width + 0.5
        ratio = diameter / width
    else:
        kind = "longitudinal" if angle <= longitudinal_max else "transversal" if angle >= transversal_min else "diagonal"
        across = _dot(rel, depth_axis) / depth + 0.5
        ratio = diameter / depth

    out = Passage(kind, round(angle, 1), round(along, 3), round(across, 3), round(ratio, 3),
                  through=None if through is None else round(through, 3))
    if kind in ("longitudinal", "diagonal"):
        out.failures.append(kind)  # running inside the member or at an angle: position and size no longer matter
        return out
    if not lo <= along <= hi:
        out.failures.append("span")
    if kind in ("transversal", "vertical") and not lo <= across <= hi:
        out.failures.append("zone")
    if kind in ("transversal", "vertical") and ratio > max_ratio:
        out.failures.append("size")
    return out
