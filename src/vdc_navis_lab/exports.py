"""File outputs: CSV (formula-safe), Markdown report, BCF 2.1 zip."""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from . import pdf, texts
from .engine.pipeline import AnalysisResult
from .engine.plan import hotspots, matrix
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


PRIORITY_COLORS = {"critical": "#C62828", "high": "#E8710A", "medium": "#C79100", "low": "#2E7D32"}


def to_pdf(result: AnalysisResult, profile: Profile, limit: int = 40) -> bytes:
    """A readable coordination report: where things stand, what to decide, who moves, where it concentrates."""
    from .views import cause_text
    lang = result.lang
    es = lang == "es"
    col = {k: pdf._hex(v) for k, v in PRIORITY_COLORS.items()}
    name = {p: texts.PRIORITY[lang][p] for p in PRIORITY_COLORS}
    chip_by_text = {name[p]: col[p] for p in PRIORITY_COLORS}
    doc_title = result.document.get("title") or result.source
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = "Informe de coordinación" if es else "Coordination report"
    d = pdf.Document(f"{title} · {doc_title}", f"vdc-navis-lab · {doc_title} · {when}")

    d.paragraph(title, 20, True)
    d.paragraph(str(doc_title), 11, False, pdf.MUTED)
    d.paragraph(f"{'Perfil' if es else 'Profile'} {result.profile_name} ({result.profile_hash}) · {when}", 8.5, False, pdf.MUTED)
    d.gap(10)
    per = result.per_band()
    d.paragraph(f"{result.raw_count} {'cruces crudos' if es else 'raw clashes'}, {len(result.issues)} "
                f"{'problemas' if es else 'issues'}, {len(result.decisions)} {'decisiones' if es else 'decisions'}", 11, True)
    d.gap(4)
    d.bar([(name[p], per[p], col[p]) for p in PRIORITY_COLORS])
    d.legend([(f"{name[p]} {per[p]}", col[p]) for p in PRIORITY_COLORS])

    cov = coverage_view(result, lang)
    if cov["warnings"]:
        d.gap(6)
        d.heading("Alcance de la evidencia" if es else "Evidence scope")
        for w in cov["warnings"]:
            d.paragraph(w, 9, bullet="•")

    by_id = {i.id: i for i in result.issues}
    causes = {c.id: c for c in result.causes}
    d.gap(6)
    d.heading("Decisiones por tomar" if es else "Decisions to make")
    rows = []
    for dec in result.decisions[:limit]:
        members = [by_id[i] for i in dec.issue_ids]
        best = min(members, key=lambda m: m.rank_key)
        cause = causes.get(dec.cause_id)
        if cause is not None:
            t = cause_text(cause, lang)
            what, action = t["title"], t["action"]
        else:
            what = pair_label(best, profile, lang) + (f" · {best.level}" if best.level else "")
            action = action_text(best, profile, lang)
        rows.append([name[dec.priority], dec.id, what, str(len(members)), action])
    d.table(["", "ID", "Qué" if es else "What", "Prob." if es else "Issues", "Acción" if es else "Action"], rows,
            [1.2, 1.7, 4.0, 0.8, 4.1], chips={0: chip_by_text})
    if len(result.decisions) > limit:
        d.paragraph(f"+ {len(result.decisions) - limit} {'decisiones más en el análisis' if es else 'more decisions in the analysis'}",
                    8.5, False, pdf.MUTED)

    d.gap(6)
    d.heading("Quién mueve qué" if es else "Who moves what")
    mrows = [[pair, str(v["critical"]), str(v["high"]), str(v["medium"]), str(v["low"]), str(v["issues"]), str(v["clashes"])]
             for pair, v in matrix(result).items()]
    d.table([("Par" if es else "Pair"), name["critical"], name["high"], name["medium"], name["low"],
             "Prob." if es else "Issues", "Cruces" if es else "Clashes"], mrows, [2.5, 1, 1, 1, 1, 1, 1])

    hs = hotspots(result, limit=5)
    if hs:
        d.gap(6)
        d.heading("Dónde se concentra" if es else "Where it concentrates")
        d.table(["Nivel" if es else "Level", "X, Y (m)", "Prob." if es else "Issues", "Puntaje" if es else "Score",
                 "Disciplinas" if es else "Disciplines"],
                [[h["level"] or "-", f"{h['center'][0]}, {h['center'][1]}", str(h["issues"]), str(h["total_score"]),
                  ", ".join(h["disciplines"])] for h in hs], [2, 2, 1, 1, 3])

    d.gap(6)
    d.heading(f"{'Principales problemas' if es else 'Top issues'} ({min(limit, len(result.issues))})")
    irows = []
    for i in result.issues[:limit]:
        why = "; ".join(reasons_text(i, profile, lang, 2))
        place = f"{i.level or '-'} · {len(i.clashes)} {'cruces' if es else 'clashes'} · {round(i.max_depth * 1000)} mm"
        irows.append([name[i.priority], i.id, pair_label(i, profile, lang) + "\n" + place,
                      why + "\n" + action_text(i, profile, lang)])
    d.table(["", "ID", "Par / lugar" if es else "Pair / place", "Por qué / acción" if es else "Why / action"], irows,
            [1.2, 1.7, 3, 5.9], chips={0: chip_by_text})
    return d.render()


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
            guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vdc-navis-lab/{i.identity}"))
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
                "    <CreationAuthor>vdc-navis-lab</CreationAuthor>\n"
                f"    <AssignedTo>{escape(i.responsible)}</AssignedTo>\n"
                f"    <Description>{escape(desc)}</Description>\n"
                "  </Topic>\n</Markup>\n"
            )
            z.writestr(f"{guid}/markup.bcf", xml)
    return buf.getvalue()
