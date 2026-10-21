"""Where the server may write. Roots come from the environment, never from tool arguments."""

from __future__ import annotations

import os
import re
from pathlib import Path

_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>"|?*\x00-\x1f]')


class PathError(ValueError):
    pass


def home() -> Path:
    base = os.environ.get("VDC_NAVIS_LAB_HOME")
    root = Path(base) if base else Path.home() / ".vdc_navis_lab"
    root.mkdir(parents=True, exist_ok=True)
    return root


def output_roots() -> list[Path]:
    raw = os.environ.get("VDC_NAVIS_LAB_OUTPUT_ROOTS", "")
    roots = [Path(p).resolve() for p in raw.split(os.pathsep) if p.strip()]
    default = (home() / "exports")
    default.mkdir(parents=True, exist_ok=True)
    roots.append(default.resolve())
    return roots


def resolve_output(requested: str, default_name: str, overwrite: bool = False) -> Path:
    """Resolve and authorise an output path. A bare file name lands in the default export folder."""
    text = (requested or default_name).strip()
    if _BAD_CHARS.search(text):
        raise PathError("path contains forbidden characters")
    if text.startswith(("\\\\", "//")):
        raise PathError("UNC and device paths are not allowed")
    if ":" in re.sub(r"^[A-Za-z]:", "", text):
        raise PathError("alternate data streams are not allowed")
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_roots()[-1] / candidate
    if candidate.stem.lower() in _RESERVED:
        raise PathError("reserved device name")
    resolved = candidate.resolve()
    if not any(resolved == r or r in resolved.parents for r in output_roots()):
        raise PathError("outside the allowed output folders (set VDC_NAVIS_LAB_OUTPUT_ROOTS to add one)")
    if resolved.exists() and not overwrite:
        raise PathError("file exists; pass overwrite=true to replace it")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
