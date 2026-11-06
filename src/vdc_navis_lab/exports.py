"""Markdown report and the shared colour table. File formats (CSV, BCF, PDF, handoff, JSON) are Pro capabilities."""

from __future__ import annotations

from . import texts
from .engine.pipeline import AnalysisResult
from .profile import Profile
from .views import action_text, coverage_view, pair_label, reasons_text

PRIORITY_COLORS = {"critical": "#C62828", "high": "#E8710A", "medium": "#C79100", "low": "#2E7D32"}


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
