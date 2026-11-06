"""Removes anything that could identify a project, a model, a file, a test or a person from text that will leave the
computer (the field-test report). Two layers: patterns for what looks like a path, a file name or an e-mail, and the
exact names the run saw (document title, test names, set names, user and computer names).

It is a safety net: the report is built from numbers and fixed words, and this makes sure that a surprise (a name inside a
message, a path inside an error) cannot reach the paste. It never prints or returns what it removed, only how many times.
"""

from __future__ import annotations

import ast
import inspect
import re
from types import ModuleType
from typing import Any, Iterable

MASK = "[omitido]"
MIN_TERM = 4
# Words that are not identifying and would make the report unreadable if masked (the user or the computer may be called "test").
HARMLESS = {"user", "users", "test", "tests", "admin", "home", "temp", "tmp", "windows", "python", "navisworks", "autodesk",
            "program", "files", "data", "document", "documents", "desktop", "downloads", "local", "roaming", "none", "true", "false", "vdc navis lab", "vdc navis", "navis lab", "field test", "vdc-navis-lab"}

_FILE_EXT = r"(?:nwd|nwf|nwc|nwp|rvt|rfa|rte|ifc|dwg|dxf|dgn|rcp|skp|3dm|pdf|xlsx?|docx?|csv|tsv|json|xml|bcf|bcfzip|md|txt|log|msi|mcpb|token|zip|png|jpe?g|toml|ps1|py|exe|dll)"
PATTERNS = [
    re.compile(r"\\\\[^\s\"'<>|]+"),                                   # UNC
    re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*"),                          # C:\... or C:/...
    re.compile(r"(?<![\w.:])/(?:[\w.\-~ ]+/)+[\w.\-~]*"),               # /home/x/y
    re.compile(r"(?<![\w.])~[\\/][^\s\"'<>|]*"),                        # ~/x
    re.compile(r"[\w.\-()\[\]]+(?: [\w.\-()\[\]]+)*\." + _FILE_EXT + r"\b", re.I),  # name.ext (with spaces inside)
    re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"),                     # e-mail
]


def norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s.lower()).strip()


def _term_regex(term: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in re.split(r"[\s_\-]+", term.strip()) if p]
    return re.compile(r"[\s_\-]+".join(parts), re.I)


class Sanitizer:
    def __init__(self, terms: Iterable[str] = ()) -> None:
        self._terms: dict[str, re.Pattern[str]] = {}
        self.redactions = 0
        self.add(*terms)

    def add(self, *terms: str | None) -> None:
        for t in terms:
            if not t:
                continue
            t = str(t).strip()
            if len(t) < MIN_TERM or norm(t) in HARMLESS:
                continue
            self._terms.setdefault(norm(t), _term_regex(t))
            stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", t)  # "Model A.nwd" also masks "Model A"
            if stem != t and len(stem) >= MIN_TERM and norm(stem) not in HARMLESS:
                self._terms.setdefault(norm(stem), _term_regex(stem))

    def known(self) -> int:
        return len(self._terms)

    def clean(self, text: str) -> str:
        # longest terms first, so "Tower A level 3" is masked as a whole before "Tower A"
        for key in sorted(self._terms, key=len, reverse=True):
            text, n = self._terms[key].subn(MASK, text)
            self.redactions += n
        for pat in PATTERNS:
            text, n = pat.subn(MASK, text)
            self.redactions += n
        return text

    def clean_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.clean(obj)
        if isinstance(obj, dict):
            return {self.clean(str(k)): self.clean_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.clean_obj(v) for v in obj]
        return obj

    def leaks(self, text: str) -> int:
        """How many known names are still in `text` after cleaning (must be 0). Never says which."""
        n = norm(text)
        return sum(1 for key in self._terms if key in n)


def numbers_only(d: Any, depth: int = 2) -> Any:
    """Keeps numbers, booleans and short lowercase codes; drops every other string. For structures whose keys are known
    but whose string values might carry a name (coverage details)."""
    if isinstance(d, bool) or isinstance(d, (int, float)) or d is None:
        return d
    if isinstance(d, str):
        return d if re.fullmatch(r"[a-z][a-z0-9_]{0,31}", d) else None
    if depth <= 0:
        return None
    if isinstance(d, dict):
        out = {str(k): numbers_only(v, depth - 1) for k, v in d.items() if re.fullmatch(r"[a-z][a-z0-9_]{0,31}", str(k))}
        return {k: v for k, v in out.items() if v is not None}
    if isinstance(d, (list, tuple)):
        return [x for x in (numbers_only(v, depth - 1) for v in d) if x is not None]
    return None


# ---------------------------------------------------------------- allow-list for free text our own code produces
_WORD = re.compile(r"[A-Za-z\u00c0-\u00ff_]{2,}")


def vocabulary(*modules: ModuleType, extra: Iterable[str] = ()) -> frozenset[str]:
    """Every word that appears in a string literal of these modules, lowercased. Text that our code builds from numbers and its
    own templates only uses these words; a name that came from a model, a test or a person never does."""
    words: set[str] = {w.lower() for w in extra}
    for m in modules:
        try:
            tree = ast.parse(inspect.getsource(m))
        except (OSError, TypeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 400:
                words |= {w.lower() for w in _WORD.findall(node.value)}
    return frozenset(words)


class Scrubber:
    """Masks every alphabetic word that is not in the vocabulary. Numbers, punctuation and short symbols pass."""

    def __init__(self, vocab: frozenset[str]) -> None:
        self.vocab = vocab
        self.redactions = 0

    def scrub(self, text: str) -> str:
        def sub(m: re.Match[str]) -> str:
            if m.group(0).lower() in self.vocab:
                return m.group(0)
            self.redactions += 1
            return MASK
        return _WORD.sub(sub, text)
