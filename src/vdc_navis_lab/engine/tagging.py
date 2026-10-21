"""Assign each element to a discipline. File name beats category: the file says who owns it."""

from __future__ import annotations

import re
import unicodedata

from ..model import Clash
from ..profile import Profile

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def _tokens(file_name: str) -> list[str]:
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    return [t for t in _TOKEN_SPLIT.split(_fold(stem)) if t]


def _pattern_hits(pattern: str, tokens: list[str]) -> bool:
    p = _fold(pattern)
    return any(t == p or (len(p) >= 4 and t.startswith(p)) for t in tokens)


class Tagger:
    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self._by_category: dict[str, str] = {}
        for code, d in profile.disciplines.items():
            for cat in d.categories:
                self._by_category.setdefault(_fold(cat), code)

    def discipline_of_file(self, file_name: str) -> str:
        if not file_name:
            return ""
        override = self.profile.overrides.get(file_name)
        if override:
            return override
        tokens = _tokens(file_name)
        for code, d in self.profile.disciplines.items():
            if any(_pattern_hits(p, tokens) for p in d.name_patterns):
                return code
        return ""

    def discipline_of(self, category: str, file_name: str, path: list[str] | tuple[str, ...] = ()) -> str:
        """File name first, then the category, then any level of the selection tree (a federated model keeps the
        source file and the Revit category as tree levels even when no property says so)."""
        found = self.discipline_of_file(file_name) or self._by_category.get(_fold(category), "")
        if found:
            return found
        for seg in path:
            if "." in seg and _fold(seg.rsplit(".", 1)[1]).isalnum() and len(seg.rsplit(".", 1)[1]) <= 5:
                found = self.discipline_of_file(seg)
                if found:
                    return found
        for seg in reversed(path):
            found = self._by_category.get(_fold(seg), "")
            if found:
                return found
        return "OTHER"

    def tag(self, clashes: list[Clash]) -> dict[str, int]:
        """Tags every element in place. Returns how many clashes ended up with an OTHER side."""
        unclassified: dict[str, int] = {}
        for clash in clashes:
            for el in (clash.a, clash.b):
                if not el.discipline:
                    el.discipline = self.discipline_of(el.category, el.model, el.path)
                if el.discipline == "OTHER":
                    label = el.category or (el.path[-2] if len(el.path) > 1 else "") or "(no category)"
                    unclassified[label] = unclassified.get(label, 0) + 1
        return unclassified
