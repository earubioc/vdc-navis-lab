"""Neutral data model shared by every input (live bridge, XML, CSV, JSON).

All lengths are metres. ``Clash.distance`` follows the Navisworks sign
convention: negative means interpenetration (the magnitude is the depth),
positive means a clearance test found two elements closer than its tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "navis_mcp.clashset/1"

Point = tuple[float, float, float]
BBox = tuple[Point, Point]

HARD, CLEARANCE, DUPLICATE = "hard", "clearance", "duplicate"
OPEN_STATUSES = frozenset({"new", "active", "reviewed"})
CLOSED_STATUSES = frozenset({"approved", "resolved"})


@dataclass(slots=True)
class Element:
    id: str
    name: str = ""
    category: str = ""
    family: str = ""
    model: str = ""
    level: str = ""
    host_id: str = ""
    system: str = ""
    props: dict[str, str] = field(default_factory=dict)
    bbox: BBox | None = None
    discipline: str = ""

    @property
    def key(self) -> str:
        """Identity used to collapse clashes: the assembly if there is one."""
        return self.host_id or self.id

    @property
    def min_dim(self) -> float | None:
        if self.bbox is None:
            return None
        lo, hi = self.bbox
        dims = [abs(hi[i] - lo[i]) for i in range(3)]
        positive = [d for d in dims if d > 1e-6]
        return min(positive) if positive else None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name, "category": self.category}
        for attr in ("family", "model", "level", "host_id", "system"):
            value = getattr(self, attr)
            if value:
                out[attr] = value
        if self.props:
            out["props"] = self.props
        if self.bbox:
            out["bbox"] = [list(self.bbox[0]), list(self.bbox[1])]
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Element":
        bbox = raw.get("bbox")
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "") or ""),
            category=str(raw.get("category", "") or ""),
            family=str(raw.get("family", "") or ""),
            model=str(raw.get("model", "") or ""),
            level=str(raw.get("level", "") or ""),
            host_id=str(raw.get("host_id", "") or ""),
            system=str(raw.get("system", "") or ""),
            props={str(k): str(v) for k, v in (raw.get("props") or {}).items()},
            bbox=(_pt(bbox[0]), _pt(bbox[1])) if bbox else None,
        )


@dataclass(slots=True)
class Clash:
    id: str
    test: str
    name: str
    status: str
    kind: str
    distance: float
    point: Point
    a: Element
    b: Element
    level: str = ""
    grid: str = ""

    @property
    def depth(self) -> float:
        return max(0.0, -self.distance)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "id": self.id, "test": self.test, "name": self.name, "status": self.status,
            "kind": self.kind, "distance": self.distance, "point": list(self.point),
            "a": self.a.to_dict(), "b": self.b.to_dict(),
        }
        if self.level:
            out["level"] = self.level
        if self.grid:
            out["grid"] = self.grid
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Clash":
        return cls(
            id=str(raw["id"]),
            test=str(raw.get("test", "")),
            name=str(raw.get("name", "")),
            status=str(raw.get("status", "new")).lower(),
            kind=str(raw.get("kind", HARD)).lower(),
            distance=float(raw.get("distance", 0.0)),
            point=_pt(raw.get("point", (0, 0, 0))),
            a=Element.from_dict(raw["a"]),
            b=Element.from_dict(raw["b"]),
            level=str(raw.get("level", "") or ""),
            grid=str(raw.get("grid", "") or ""),
        )


@dataclass(slots=True)
class TestInfo:
    __test__ = False  # not a pytest class

    name: str
    kind: str = HARD
    status: str = "new"
    tolerance: float = 0.0
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "status": self.status,
                "tolerance": self.tolerance, "count": self.count}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TestInfo":
        return cls(str(raw.get("name", "")), str(raw.get("kind", HARD)).lower(),
                   str(raw.get("status", "new")).lower(),
                   float(raw.get("tolerance", 0.0) or 0.0), int(raw.get("count", 0) or 0))


@dataclass(slots=True)
class ClashSet:
    clashes: list[Clash] = field(default_factory=list)
    tests: list[TestInfo] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    document: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA, "source": self.source, "document": self.document,
            "models": self.models, "truncated": self.truncated,
            "tests": [t.to_dict() for t in self.tests],
            "clashes": [c.to_dict() for c in self.clashes],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ClashSet":
        if raw.get("schema") != SCHEMA:
            raise ValueError(f"unsupported schema {raw.get('schema')!r}, expected {SCHEMA!r}")
        return cls(
            clashes=[Clash.from_dict(c) for c in raw.get("clashes", [])],
            tests=[TestInfo.from_dict(t) for t in raw.get("tests", [])],
            models=[str(m) for m in raw.get("models", [])],
            document=dict(raw.get("document") or {}),
            source=str(raw.get("source", "")),
            truncated=bool(raw.get("truncated", False)),
        )


def _pt(raw: Any) -> Point:
    x, y, z = raw
    return (float(x), float(y), float(z))


def dist(p: Point, q: Point) -> float:
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2) ** 0.5
