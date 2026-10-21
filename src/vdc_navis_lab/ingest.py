"""Read clash data from files: native JSON, Navisworks Clash Detective XML, or CSV.

The XML reader is deliberately tolerant (namespaces and element order vary between exports)
and refuses documents that declare a DTD or entities.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .model import CLEARANCE, DUPLICATE, HARD, Clash, ClashSet, Element, TestInfo

MAX_FILE_BYTES = 256 * 1024 * 1024
ALLOWED_SUFFIXES = {".json", ".xml", ".csv"}

_UNITS = {"m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0, "mm": 0.001, "millimeters": 0.001,
          "cm": 0.01, "centimeters": 0.01, "in": 0.0254, "inches": 0.0254, "ft": 0.3048, "feet": 0.3048}
_MODEL_EXT = (".nwc", ".nwd", ".nwf", ".rvt", ".ifc", ".dwg", ".dgn", ".skp")
_STATUS = {"new": "new", "active": "active", "reviewed": "reviewed", "approved": "approved",
           "resolved": "resolved", "ok": "new"}


class IngestError(ValueError):
    pass


def load(path: str | Path) -> ClashSet:
    p = Path(path)
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise IngestError(f"unsupported file type {p.suffix!r}; use .json, .xml or .csv")
    if not p.is_file():
        raise IngestError("file not found")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise IngestError("file exceeds the 256 MB limit")
    suffix = p.suffix.lower()
    try:
        if suffix == ".json":
            cs = ClashSet.from_dict(json.loads(p.read_text(encoding="utf-8")))
        elif suffix == ".xml":
            cs = from_navisworks_xml(p.read_text(encoding="utf-8-sig"))
        else:
            cs = from_csv(p.read_text(encoding="utf-8-sig"))
    except IngestError:
        raise
    except (ValueError, KeyError, TypeError, ET.ParseError, UnicodeDecodeError) as exc:
        # Do not echo file content in errors: the caller may be an LLM pointed at the wrong file.
        raise IngestError(f"could not parse {p.name} as {suffix[1:].upper()}: {type(exc).__name__}") from None
    cs.source = cs.source or f"file:{p.name}"
    return cs


# --------------------------------------------------------------------- XML
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _kids(node: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in node if _local(c.tag) == name]


def _first(node: ET.Element, name: str) -> ET.Element | None:
    return next(iter(_kids(node, name)), None)


def _descend(node: ET.Element, name: str) -> list[ET.Element]:
    return [n for n in node.iter() if _local(n.tag) == name]


def _text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _kind(raw: str) -> str:
    raw = (raw or "").lower()
    if "clear" in raw:
        return CLEARANCE
    if "dup" in raw:
        return DUPLICATE
    return HARD


def _pairs(node: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in _descend(node, "smarttag") + _descend(node, "objectattribute"):
        name, value = _text(_first(item, "name")), _text(_first(item, "value"))
        if name and value and name not in out:
            out[name] = value
    return out


def _object(node: ET.Element, factor: float) -> Element:
    path_nodes = [_text(n) for link in _descend(node, "pathlink") for n in _kids(link, "node")]
    props = _pairs(node)
    model = next((n for n in path_nodes if n.lower().endswith(_MODEL_EXT)), path_nodes[0] if path_nodes else "")
    name = props.get("Item Name") or props.get("Name") or (path_nodes[-1] if path_nodes else "")
    category = props.get("Category") or props.get("Item Type") or props.get("Type") or ""
    level = props.get("Level") or props.get("Reference Level") or props.get("Item Layer") or props.get("Layer") or ""
    stable = props.get("GlobalId") or props.get("Element ID") or props.get("Id") or ""
    ident = f"{model}:{stable}" if stable else "/".join(path_nodes) or name
    return Element(id=ident, name=name, category=category, family=props.get("Family", ""), model=model,
                   level=level, system=props.get("System Name", ""), props=props)


def from_navisworks_xml(text: str) -> ClashSet:
    head = text[:4096].lower()
    if "<!doctype" in head or "<!entity" in text.lower():
        raise IngestError("XML with DTD or entity declarations is refused")
    root = ET.fromstring(text)
    units = root.get("units") or next((n.get("units") for n in _descend(root, "batchtest") if n.get("units")), "m")
    factor = _UNITS.get((units or "m").lower(), 1.0)

    clashes: list[Clash] = []
    tests: list[TestInfo] = []
    models: set[str] = set()
    for test in _descend(root, "clashtest"):
        name = test.get("name", "")
        kind = _kind(test.get("test_type", ""))
        results = _descend(test, "clashresult")
        tests.append(TestInfo(name=name, kind=kind, status=_STATUS.get(test.get("status", "new").lower(), "new"),
                              tolerance=float(test.get("tolerance", 0) or 0) * factor, count=len(results)))
        for res in results:
            objs = _descend(res, "clashobject")
            if len(objs) < 2:
                continue
            pos = next(iter(_descend(res, "pos3f")), None)
            point = tuple(float(pos.get(k, 0)) * factor for k in "xyz") if pos is not None else (0.0, 0.0, 0.0)
            a, b = _object(objs[0], factor), _object(objs[1], factor)
            models.update(m for m in (a.model, b.model) if m)
            clashes.append(Clash(
                id=res.get("guid") or f"{name}/{res.get('name', len(clashes))}", test=name,
                name=res.get("name", ""), status=_STATUS.get(res.get("status", "new").lower(), "new"), kind=kind,
                distance=float(res.get("distance", 0) or 0) * factor, point=point, a=a, b=b,
                level=a.level or b.level,
            ))
    if not tests:
        raise IngestError("no clash tests found: is this a Clash Detective XML export?")
    return ClashSet(clashes=clashes, tests=tests, models=sorted(models), document={"title": root.get("filename", "")},
                    source="navisworks-xml")


# --------------------------------------------------------------------- CSV
_ALIASES = {
    "id": ("id", "guid", "clash_id"), "test": ("test", "test_name"), "name": ("name", "clash_name"),
    "status": ("status",), "kind": ("kind", "type", "test_type"), "distance": ("distance", "distance_m", "dist"),
    "x": ("x", "point_x"), "y": ("y", "point_y"), "z": ("z", "point_z"), "level": ("level",), "grid": ("grid",),
}
_SIDE = ("id", "name", "category", "family", "model", "level", "system")


def _col(row: dict[str, str], key: str) -> str:
    for alias in _ALIASES.get(key, (key,)):
        if alias in row and row[alias] != "":
            return row[alias]
    return ""


def from_csv(text: str, units: str = "m") -> ClashSet:
    factor = _UNITS.get(units.lower(), 1.0)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestError("empty CSV")
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
    clashes: list[Clash] = []
    for n, row in enumerate(reader, 1):
        def side(prefix: str) -> Element:
            vals = {k: (row.get(f"{prefix}_{k}") or "").strip() for k in _SIDE}
            return Element(id=vals["id"] or f"{prefix}{n}", name=vals["name"], category=vals["category"],
                           family=vals["family"], model=vals["model"], level=vals["level"], system=vals["system"])
        try:
            point = (float(_col(row, "x") or 0) * factor, float(_col(row, "y") or 0) * factor,
                     float(_col(row, "z") or 0) * factor)
            distance = float(_col(row, "distance") or 0) * factor
        except ValueError:
            raise IngestError(f"row {n}: non-numeric coordinate or distance") from None
        a, b = side("a"), side("b")
        clashes.append(Clash(
            id=_col(row, "id") or f"row{n}", test=_col(row, "test"), name=_col(row, "name") or f"Clash{n}",
            status=_STATUS.get(_col(row, "status").lower(), "new"), kind=_kind(_col(row, "kind")), distance=distance,
            point=point, a=a, b=b, level=_col(row, "level") or a.level or b.level, grid=_col(row, "grid"),
        ))
    tests = {}
    for c in clashes:
        t = tests.setdefault(c.test, TestInfo(name=c.test, kind=c.kind, status="active"))
        t.count += 1
    return ClashSet(clashes=clashes, tests=list(tests.values()),
                    models=sorted({m for c in clashes for m in (c.a.model, c.b.model) if m}), source="csv")
