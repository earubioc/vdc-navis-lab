"""Deterministic synthetic project: a 5-level tower with every situation the engine must handle.

Used by the tests, by the simulator that stands in for Navisworks, and by `vdc-navis-lab-cli sample`.
Nothing here is real project data.
"""

from __future__ import annotations

import random

from ..model import CLEARANCE, HARD, SCHEMA, Clash, ClashSet, Element, Point, TestInfo

MODELS = {
    "STR": "TORRE-EST.nwc", "ARC": "TORRE-ARQ.nwc", "HVAC": "TORRE-HVAC.nwc",
    "PLB": "TORRE-HID.nwc", "ELE": "TORRE-ELE.nwc", "FIRE": "TORRE-RCI.nwc",
}
FLOOR_H = 3.2


def _box(center: Point, size: Point):
    return ((center[0] - size[0] / 2, center[1] - size[1] / 2, center[2] - size[2] / 2),
            (center[0] + size[0] / 2, center[1] + size[1] / 2, center[2] + size[2] / 2))


class _Builder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.elements: dict[str, Element] = {}
        self.clashes: list[Clash] = []
        self.n = 0

    def el(self, disc: str, eid: str, cat: str, name: str, family: str, level: str, center: Point, size: Point,
           host: str = "", system: str = "") -> Element:
        e = Element(id=f"{MODELS[disc]}:{eid}", name=name, category=cat, family=family, model=MODELS[disc],
                    level=level, host_id=f"{MODELS[disc]}:{host}" if host else "", system=system,
                    props={"Id": eid}, bbox=_box(center, size))
        self.elements[e.id] = e
        return e

    def clash(self, test: str, a: Element, b: Element, point: Point, depth: float, level: str,
              status: str = "new", kind: str = HARD, distance: float | None = None) -> Clash:
        self.n += 1
        d = distance if distance is not None else -depth
        c = Clash(id=f"c{self.n:04d}", test=test, name=f"Clash{self.n}", status=status, kind=kind, distance=d,
                  point=point, a=a, b=b, level=level)
        self.clashes.append(c)
        return c


def build(seed: int = 7, levels: int = 5) -> tuple[ClashSet, list[Element]]:
    b = _Builder(seed)
    rng = b.rng
    riser = None
    for lv in range(1, levels + 1):
        z0 = (lv - 1) * FLOOR_H
        lname = f'Level "L{lv}", #{9000 + lv}' if lv % 2 else f"Level L{lv}"
        slab = b.el("STR", f"slab{lv}", "Floors", f"Slab L{lv}", "Floor:Concrete 200", lname,
                    (15, 15, z0), (40, 40, 0.2))
        beams = [b.el("STR", f"beam{lv}-{k}", "Structural Framing", f"Beam {lv}.{k}", "Concrete-Rectangular Beam",
                      lname, (15, 4 + 6 * k, z0 + 2.8), (30, 0.3, 0.5)) for k in range(3)]

        # a branch duct crossing three beams: three separate places
        duct = b.el("HVAC", f"duct{lv}", "Ducts", f"Supply duct L{lv}", "Rectangular Duct", lname,
                    (8, 10, z0 + 2.75), (0.4, 20, 0.3), system="Supply Air 1")
        for k, beam in enumerate(beams):
            depth = 0.30 if (lv, k) == (3, 0) else rng.uniform(0.05, 0.18)  # one duct cuts clean through a beam
            b.clash("STR vs HVAC", beam, duct, (8, 4 + 6 * k, z0 + 2.7), depth, lname)

        # a pipe rack: five pipes 0.4 m apart cross one duct, which is ONE issue
        if lv == 2:
            d2 = b.el("HVAC", "duct-rack", "Ducts", "Duct over rack", "Rectangular Duct", lname,
                      (22, 12, z0 + 2.2), (0.5, 6, 0.4), system="Supply Air 2")
            for p in range(5):
                pipe = b.el("PLB", f"rack{p}", "Pipes", f"Rack pipe {p}", "Pipe Types:Steel 100", lname,
                            (21 + 0.4 * p, 12, z0 + 2.2), (0.1, 6, 0.1), system="CHW")
                b.clash("HVAC vs PLB", d2, pipe, (21 + 0.4 * p, 12, z0 + 2.2), rng.uniform(0.04, 0.08), lname)

        # same detail on every level: copper pipe against a cable tray
        pipe = b.el("PLB", f"cu{lv}", "Pipes", f"Copper 50 L{lv}", "Pipe Types:Copper 50", lname,
                    (30, 10, z0 + 2.5), (0.05, 8, 0.05), system="DHW")
        tray = b.el("ELE", f"tray{lv}", "Cable Trays", f"Tray L{lv}", "Cable Tray:200x60", lname,
                    (30, 10, z0 + 2.5), (6, 0.2, 0.06))
        b.clash("ELE vs PLB", tray, pipe, (30, 10, z0 + 2.5), 0.03, lname)

        # riser duct through every slab: the same movable element, one decision
        if riser is None:
            riser = b.el("HVAC", "riser", "Ducts", "Riser duct R1", "Rectangular Duct", lname,
                         (35, 35, levels * FLOOR_H / 2), (0.6, 0.6, levels * FLOOR_H), system="Exhaust")
        b.clash("STR vs HVAC", slab, riser, (35, 35, z0), 0.06, lname)

        # a doorway: designed opening inside its wall (filtered)
        wall = b.el("ARC", f"wall{lv}", "Walls", f"Wall L{lv}", "Basic Wall", lname, (12, 20, z0 + 1.5), (0.2, 8, 3.0))
        door = b.el("ARC", f"door{lv}", "Doors", f"Door L{lv}", "Single-Flush", lname, (12, 20, z0 + 1.05), (0.2, 0.9, 2.1))
        b.clash("ARC vs STR", wall, door, (12, 20, z0 + 1.05), 0.2, lname)
        # a conduit through that wall with no opening modelled: a real issue
        cond = b.el("ELE", f"cond{lv}", "Conduits", f"Conduit L{lv}", "Conduit:EMT 25", lname,
                    (12, 24, z0 + 1.6), (0.03, 3, 0.03))
        b.clash("ELE vs ARC", cond, wall, (12, 24, z0 + 1.6), 0.025, lname)

    # tolerance noise, same-assembly hits, closed results, clearance, fire gate, a test never run
    last = f"Level L{levels}"
    ref_beam = next(e for e in b.elements.values() if e.id.endswith("beam1-0"))
    for k in range(4):
        thin = b.el("PLB", f"thin{k}", "Pipes", f"Thin pipe {k}", "Pipe Types:PVC 25", "Level L1",
                    (3 + k, 4, 2.8), (0.03, 3, 0.03))
        b.clash("STR vs PLB", ref_beam, thin, (3 + k, 4, 2.8), 0.002, "Level L1")
    for k in range(3):
        fit_host = b.el("PLB", f"asm{k}", "Pipes", f"Assembly pipe {k}", "Pipe Types:Steel 50", "Level L1",
                        (40, 5 + k, 1), (0.05, 2, 0.05))
        fit = b.el("PLB", f"asm{k}f", "Pipe Fittings", f"Elbow {k}", "Pipe Fittings:Elbow", "Level L1",
                   (40, 6 + k, 1), (0.08, 0.08, 0.08), host=f"asm{k}")
        fit_host.host_id = f"{MODELS['PLB']}:asm{k}"
        b.clash("HVAC vs PLB", fit_host, fit, (40, 6 + k, 1), 0.04, "Level L1")
    for k in range(3):
        old = b.el("ELE", f"old{k}", "Conduits", f"Old conduit {k}", "Conduit:EMT 20", "Level L1",
                   (45, 5 + k * 2, 2.8), (0.03, 2, 0.03))
        b.clash("STR vs HVAC", ref_beam, old, (45, 5 + k * 2, 2.8), 0.09, "Level L1", status="approved")
    for k in range(3):
        ele = b.el("ELE", f"clr{k}", "Cable Trays", f"Clearance tray {k}", "Cable Tray:300x60", last,
                   (5 + 6 * k, 30, 13), (4, 0.3, 0.06))
        hv = b.el("HVAC", f"clrd{k}", "Ducts", f"Clearance duct {k}", "Rectangular Duct", last,
                  (5 + 6 * k, 30.33, 13), (0.4, 5, 0.3))
        b.clash("HVAC vs ELE clearance", hv, ele, (5 + 6 * k, 30, 13), 0, last, kind=CLEARANCE, distance=0.02)
    sprk = b.el("FIRE", "sprk1", "Pipes", "Sprinkler main", "Pipe Types:Black steel 65", "Level L2",
                (3, 8, 5.8), (0.07, 6, 0.07), system="Fire")
    b.clash("FIRE vs STR", ref_beam, sprk, (3, 8, 5.8), 0.03, "Level L2")

    for k in range(30):  # inventory that never clashes, so counts mean something
        disc, cat = rng.choice([("HVAC", "Ducts"), ("PLB", "Pipes"), ("ELE", "Cable Trays"), ("ARC", "Walls"),
                                ("STR", "Structural Framing")])
        b.el(disc, f"fill{k}", cat, f"Filler {k}", "Generic", f"Level L{rng.randint(1, levels)}",
             (rng.uniform(0, 40), rng.uniform(0, 40), rng.uniform(0, 14)), (1, 1, 0.3))

    tests = [
        TestInfo("STR vs HVAC", HARD, "active", 0.0), TestInfo("HVAC vs PLB", HARD, "active", 0.0),
        TestInfo("STR vs PLB", HARD, "active", 0.0), TestInfo("ELE vs PLB", HARD, "reviewed", 0.0),
        TestInfo("ARC vs STR", HARD, "active", 0.0), TestInfo("ELE vs ARC", HARD, "active", 0.0),
        TestInfo("HVAC vs ELE clearance", CLEARANCE, "active", 0.05), TestInfo("FIRE vs STR", HARD, "active", 0.0),
        TestInfo("ELE vs STR", HARD, "new", 0.0),  # never run
    ]
    for t in tests:
        t.count = sum(1 for c in b.clashes if c.test == t.name)
    cs = ClashSet(clashes=b.clashes, tests=tests, models=sorted(MODELS.values()),
                  document={"title": "TORRE-DEMO.nwf", "fingerprint": "sim-torre-demo-0001"}, source="synthetic")
    return cs, list(b.elements.values())
