"""Profile: the single place where coordination criteria live (TOML)."""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA = "vdc_navis_lab.profile/1"
MAX_PROFILE_BYTES = 256 * 1024
PRIORITIES = ("critical", "high", "medium", "low")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,11}$")


class ProfileError(ValueError):
    pass


@dataclass(slots=True)
class Discipline:
    code: str
    label: dict[str, str]
    mobility: float
    name_patterns: list[str]
    categories: frozenset[str]


@dataclass(slots=True)
class Profile:
    raw: dict[str, Any]
    name: str
    lang: str
    disciplines: dict[str, Discipline]
    checksum: str
    overrides: dict[str, str] = field(default_factory=dict)  # file name -> discipline, set at runtime

    # ---- loading
    @classmethod
    def default(cls) -> "Profile":
        text = resources.files("vdc_navis_lab").joinpath("profiles/default.toml").read_text(encoding="utf-8")
        return cls.from_text(text)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Profile":
        if path is None or str(path) == "":
            return cls.default()
        p = Path(path)
        if p.suffix.lower() != ".toml":
            raise ProfileError("profile files must be .toml")
        if not p.is_file():
            raise ProfileError("profile file not found")
        if p.stat().st_size > MAX_PROFILE_BYTES:
            raise ProfileError("profile file is too large")
        return cls.from_text(p.read_text(encoding="utf-8"))

    @classmethod
    def from_text(cls, text: str) -> "Profile":
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ProfileError(f"invalid TOML: {exc}") from None
        disciplines = {}
        for code, spec in (raw.get("disciplines") or {}).items():
            disciplines[code] = Discipline(
                code=code,
                label=dict(spec.get("label") or {"es": code, "en": code}),
                mobility=float(spec.get("mobility", 0.5)),
                name_patterns=[str(x).lower() for x in spec.get("name_patterns", [])],
                categories=frozenset(str(x).lower() for x in spec.get("categories", [])),
            )
        profile = cls(
            raw=raw,
            name=str(raw.get("name", "unnamed")),
            lang=str(raw.get("lang", "es")),
            disciplines=disciplines,
            checksum=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        )
        problems = profile.validate()
        if problems:
            raise ProfileError("; ".join(problems))
        return profile

    # ---- access helpers
    def section(self, *path: str) -> dict[str, Any]:
        node: Any = self.raw
        for key in path:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        return node if isinstance(node, dict) else {}

    def num(self, *path: str, default: float) -> float:
        node: Any = self.raw
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        return float(node) if isinstance(node, (int, float)) and not isinstance(node, bool) else default

    def label(self, code: str, lang: str | None = None) -> str:
        spec = self.disciplines.get(code)
        if spec is None:
            return code
        lang = lang or self.lang
        return spec.label.get(lang) or spec.label.get("en") or code

    def mobility(self, code: str) -> float:
        spec = self.disciplines.get(code)
        return spec.mobility if spec else 0.5

    def criticality(self, a: str, b: str) -> float:
        table = self.section("score", "criticality")
        value = table.get(f"{a}-{b}", table.get(f"{b}-{a}", table.get("default", 0.5)))
        return min(1.0, max(0.0, float(value)))

    def weights(self) -> dict[str, float]:
        w = self.section("score", "weights")
        return {k: float(v) for k, v in w.items() if isinstance(v, (int, float))}

    # ---- validation
    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.raw.get("schema") != SCHEMA:
            problems.append(f"schema must be {SCHEMA!r}")
        if self.lang not in ("es", "en"):
            problems.append("lang must be 'es' or 'en'")
        if not self.disciplines:
            problems.append("no disciplines defined")
        for code, d in self.disciplines.items():
            if not _CODE.match(code):
                problems.append(f"discipline code {code!r} must be 2-12 chars A-Z, 0-9, _")
            if not 0.0 <= d.mobility <= 1.0:
                problems.append(f"{code}: mobility must be between 0 and 1")
        if "OTHER" not in self.disciplines:
            problems.append("an OTHER discipline is required for unclassified elements")
        weights = self.weights()
        if not weights or sum(weights.values()) <= 0 or any(v < 0 for v in weights.values()):
            problems.append("score.weights must be non-negative with a positive sum")
        bands = self.section("score", "bands")
        if not all(isinstance(bands.get(k), (int, float)) for k in ("critical", "high", "medium")):
            problems.append("score.bands needs critical, high and medium")
        elif not bands["critical"] > bands["high"] > bands["medium"] > 0:
            problems.append("score.bands must satisfy critical > high > medium > 0")
        for key in self.section("score", "criticality"):
            if key == "default":
                continue
            parts = key.split("-")
            if len(parts) != 2 or any(p not in self.disciplines for p in parts):
                problems.append(f"criticality key {key!r} must name two known disciplines, as A-B")
        for pair in self.raw.get("expected_pairs", []):
            parts = str(pair).split("-")
            if len(parts) != 2 or any(p not in self.disciplines for p in parts):
                problems.append(f"expected_pairs entry {pair!r} references unknown disciplines")
        for gate in self.raw.get("score", {}).get("gates", []):
            if gate.get("floor") not in PRIORITIES:
                problems.append(f"gate floor {gate.get('floor')!r} is not a priority")
        return problems

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name, "lang": self.lang, "checksum": self.checksum,
            "disciplines": {c: self.label(c) for c in self.disciplines},
            "overrides": dict(self.overrides),
        }
