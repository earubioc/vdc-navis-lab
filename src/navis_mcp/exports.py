"""File outputs: CSV (formula-safe), Markdown report, BCF 2.1 zip."""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from . import texts
from .engine.pipeline import AnalysisResult
from .profile import Profile
from .views import action_text, coverage_view, pair_label, reasons_text

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value):
    """Strings that a spreadsheet would run as a formula get a leading apostrophe. Numbers are untouched."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def to_csv(result: AnalysisResult, profile: Profile) -> bytes:
    lang = result.lang
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "priority", "score", "pair", "level", "responsible", "anchor", "clashes", "max_depth_mm",
                "tests", "causes", "action", "element_a", "element_b", "x", "y", "z"])
    for i in result.issues:
        rep = i.rep
        w.writerow([csv_cell(v) for v in [
            i.id, i.priority, i.score, "-".join(i.pair), i.level, i.responsible, i.anchor, len(i.clashes),
            round(i.max_depth * 1000), ";".join(sorted({c.test for c in i.clashes})), ";".join(i.cause_ids),
            action_text(i, profile, lang), f"{rep.a.model}:{rep.a.name or rep.a.id}", f"{rep.b.model}:{rep.b.name or rep.b.id}",
            round(i.centroid[0], 3), round(i.centroid[1], 3), round(i.centroid[2], 3)]])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def to_markdown(result: AnalysisResult, profile: Profile, limit: int = 25) -> str:
    from .views import cause_text
    lang = result.lang
    es = lang == "es"
    cov = coverage_view(result, lang)
    pr = result.per_band()
    lines = [f"# {'Informe de coordinación' if es else 'Coordination report'}", ""]
    doc = result.document.get("title") or result.source
    lines += [f"**{'Documento' if es else 'Document'}:** {doc}  ",
              f"**{'Perfil' if es else 'Profile'}:** {result.profile_name} ({result.profile_hash})  ",
              f"**{'Cruces crudos' if es else 'Raw clashes'}:** {result.raw_count}, "
              f"**{'problemas' if es else 'issues'}:** {len(result.issues)}, "
              f"**{'decisiones' if es else 'decisions'}:** {len(result.decisions)}", "",
              " · ".join(f"{texts.PRIORITY[lang][p]} {n}" for p, n in pr.items()), ""]
    if cov["warnings"]:
        lines += [f"## {'Alcance de la evidencia' if es else 'Evidence scope'}", ""] + [f"- {w}" for w in cov["warnings"]] + [""]
    if result.causes:
        lines += [f"## {'Causas raíz' if es else 'Root causes'}", ""]
        for c in result.causes[:8]:
            t = cause_text(c, lang)
            lines.append(f"- **{t['title']}** ({c.confidence:.0%}). {t['action']}")
        lines.append("")
    lines += [f"## {'Principales problemas' if es else 'Top issues'}", ""]
    for i in result.issues[:limit]:
        lines.append(f"### {i.id} · {texts.PRIORITY[lang][i.priority]} · {i.score}")
        lines.append(f"{pair_label(i, profile, lang)}, {i.level or ('sin nivel' if es else 'no level')}, "
                     f"{len(i.clashes)} {'cruces' if es else 'clashes'}")
        lines += [f"- {r}" for r in reasons_text(i, profile, lang, 4)]
        lines += [f"- **{'Acción' if es else 'Action'}:** {action_text(i, profile, lang)}", ""]
    return "\n".join(lines)


_BCF_PRIORITY = {"critical": "Critical", "high": "High", "medium": "Normal", "low": "Low"}


def to_bcf(result: AnalysisResult, profile: Profile, limit: int = 200) -> bytes:
    """BCF 2.1: one topic per issue, assigned to the discipline that has to move."""
    lang = result.lang
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Version VersionId="2.1">\n  <DetailedVersion>2.1</DetailedVersion>\n</Version>\n')
        for i in result.issues[:limit]:
            guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"navis-mcp/{i.identity}"))
            title = f"[{texts.PRIORITY[lang][i.priority]}] {pair_label(i, profile, lang)} {i.level} {i.id}".replace("  ", " ")
            desc = "\n".join(reasons_text(i, profile, lang, 6) + [action_text(i, profile, lang)])
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Markup xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
                f'  <Topic Guid="{guid}" TopicType="Clash" TopicStatus="Open">\n'
                f"    <Title>{escape(title)}</Title>\n"
                f"    <Priority>{_BCF_PRIORITY[i.priority]}</Priority>\n"
                f"    <Labels>{escape('-'.join(i.pair))}</Labels>\n"
                f"    <CreationDate>{now}</CreationDate>\n"
                "    <CreationAuthor>navis-mcp</CreationAuthor>\n"
                f"    <AssignedTo>{escape(i.responsible)}</AssignedTo>\n"
                f"    <Description>{escape(desc)}</Description>\n"
                "  </Topic>\n</Markup>\n"
            )
            z.writestr(f"{guid}/markup.bcf", xml)
    return buf.getvalue()
