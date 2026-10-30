"""Turn an AnalysisResult into compact, language-aware structures for tools and reports."""

from __future__ import annotations

from typing import Any

from . import texts
from .engine.pipeline import AnalysisResult, Cause, Issue
from .engine.plan import hotspots, matrix
from .profile import Profile

FILTER_LABELS = texts.FILTER


_LABEL_KEYS = ("a", "b", "anchor", "mover")


def reasons_text(issue: Issue, profile: Profile, lang: str, limit: int = 4) -> list[str]:
    """Reasons carry discipline codes; labels are resolved here, in the requested language."""
    out = []
    for code, args in issue.reasons[:limit]:
        args = {k: (profile.label(v, lang) if k in _LABEL_KEYS else v) for k, v in args.items()}
        out.append(texts.render(texts.REASONS, lang, code, args))
    return out


def action_text(issue: Issue, profile: Profile, lang: str) -> str:
    mover, anchor = profile.label(issue.responsible, lang), profile.label(issue.anchor, lang)
    codes = {c for c, _ in issue.reasons}
    if all(c.kind == "clearance" for c in issue.clashes):
        code = "clearance"
    elif "model_error" in codes:
        code = "model_error"
    elif any(c.startswith("beam_pass_") and c not in ("beam_pass_ok", "beam_pass_level") for c in codes):
        code = "beam_pass_fail"
    elif "beam_pass_ok" in codes:
        code = "beam_pass_ok"
    elif "embedded_small" in codes:
        code = "embedded"
    elif "sleeve_missing" in codes:
        code = "sleeve_missing"
    elif "sleeve_candidate" in codes:
        code = "sleeve_check"
    else:
        code = f"move_{issue.responsible}"
        if code not in texts.ACTIONS.get(lang, texts.ACTIONS["en"]):
            code = "move"
    return texts.render(texts.ACTIONS, lang, code, {"mover": mover, "anchor": anchor})


def cause_text(cause: Cause, lang: str) -> dict[str, str]:
    action_code = "cause_shared" if cause.kind == "shared_element" else "cause_repeat"
    return {
        "title": texts.render(texts.CAUSES, lang, cause.kind, cause.params),
        "action": texts.render(texts.ACTIONS, lang, action_code, cause.params),
    }


def pair_label(issue: Issue, profile: Profile, lang: str) -> str:
    a, b = issue.pair
    return f"{profile.label(a, lang)} x {profile.label(b, lang)}"


def brief(issue: Issue, profile: Profile, lang: str) -> dict[str, Any]:
    return {
        "id": issue.id, "priority": issue.priority, "label": texts.PRIORITY[lang][issue.priority],
        "score": issue.score, "pair": "-".join(issue.pair), "pair_label": pair_label(issue, profile, lang),
        "level": issue.level, "clashes": len(issue.clashes), "max_depth_mm": round(issue.max_depth * 1000),
        "responsible": issue.responsible, "why": reasons_text(issue, profile, lang, 3),
        "action": action_text(issue, profile, lang), "causes": issue.cause_ids,
    }


def detail(issue: Issue, result: AnalysisResult, profile: Profile, lang: str, clash_limit: int = 15) -> dict[str, Any]:
    causes = {c.id: c for c in result.causes}
    rep = issue.rep
    out = brief(issue, profile, lang)
    out.update({
        "why": reasons_text(issue, profile, lang, 10),
        "components": issue.components,
        "anchor": issue.anchor,
        "centroid": [round(v, 2) for v in issue.centroid], "span_m": round(issue.span, 2),
        "tests": sorted({c.test for c in issue.clashes}),
        "representative": {"a": rep.a.to_dict(), "b": rep.b.to_dict(), "clash_id": rep.id},
        "clash_ids": [c.id for c in issue.clashes][:clash_limit],
        "clashes_total": len(issue.clashes),
        "cause_details": [{"id": cid, "kind": causes[cid].kind, "confidence": causes[cid].confidence,
                           **cause_text(causes[cid], lang)} for cid in issue.cause_ids if cid in causes],
    })
    return out


def coverage_view(result: AnalysisResult, lang: str) -> dict[str, Any]:
    cov = result.coverage
    warnings = []
    es = lang == "es"
    if cov.never_run:
        warnings.append((f"{len(cov.never_run)} prueba(s) nunca ejecutada(s): su ausencia de resultados NO significa limpio"
                         if es else f"{len(cov.never_run)} test(s) never run: no results does NOT mean clean"))
    if cov.pairs_without_results:
        warnings.append((f"sin resultados para los pares requeridos: {', '.join(cov.pairs_without_results)} "
                         "(limpios o sin probar; verificar)" if es else
                         f"no results for required pairs: {', '.join(cov.pairs_without_results)} (clean or untested; verify)"))
    if cov.silenced_tests:
        warnings.append((f"el filtro descartó todos los resultados de: {', '.join(cov.silenced_tests)}"
                         if es else f"the filter rejected every result of: {', '.join(cov.silenced_tests)}"))
    if cov.truncated:
        warnings.append("la exportación fue truncada; el análisis es parcial" if es else "export was truncated; analysis is partial")
    if cov.skipped:
        if cov.skipped_open is None:
            warnings.append((f"{cov.skipped} resultado(s) omitido(s): su(s) elemento(s) ya no existen en el modelo (no se analizaron)"
                             if es else f"{cov.skipped} result(s) skipped: their element(s) no longer exist in the model (not analysed)"))
        elif cov.skipped_open:
            warnings.append((f"{cov.skipped} resultado(s) omitido(s) porque su elemento ya no existe en el modelo; "
                             f"{cov.skipped_open} seguían abiertos (nuevos o activos) y no se analizaron"
                             if es else f"{cov.skipped} result(s) skipped because their element no longer exists in the model; "
                             f"{cov.skipped_open} were still open (new or active) and were not analysed"))
        else:
            warnings.append((f"{cov.skipped} resultado(s) omitido(s) porque su elemento ya no existe en el modelo; "
                             "todos estaban ya cerrados (revisados, aprobados o resueltos), no afectan el análisis"
                             if es else f"{cov.skipped} result(s) skipped because their element no longer exists in the model; "
                             "all were already closed (reviewed, approved or resolved), so the analysis is unaffected"))
    if cov.sleeves_modeled == 0:
        warnings.append(("no hay manguitos ni aberturas modeladas (se buscaron por nombre y categoría): los pasos por losas y muros "
                         "se tratan como pendientes de manguito"
                         if es else "no sleeves or openings are modelled (searched by name and category): passages through floors "
                         "and walls are treated as still needing a sleeve"))
    if cov.unclassified:
        top = ", ".join(f"{k} ({v})" for k, v in list(cov.unclassified.items())[:4])
        warnings.append((f"elementos sin disciplina por categoría: {top}; ajustar perfil o asignar archivos"
                         if es else f"elements with no discipline: {top}; adjust the profile or assign files"))
    return {"complete": cov.complete, "tests": f"{cov.tests_ran}/{cov.tests_count}", "never_run": cov.never_run,
            "pairs_without_results": cov.pairs_without_results, "skipped": cov.skipped, "skipped_open": cov.skipped_open, "sleeves_modeled": cov.sleeves_modeled, "warnings": warnings}


def summary(result: AnalysisResult, profile: Profile, top: int = 10, lang: str | None = None) -> dict[str, Any]:
    lang = lang or result.lang
    filt = {texts.render(FILTER_LABELS, lang, k, {}): v for k, v in result.filtering.most_common()}
    folded = len(result.issues) - len(result.decisions)
    return {
        "analysis_id": result.analysis_id, "source": result.source,
        "document": result.document.get("title", ""),
        "profile": f"{result.profile_name}@{result.profile_hash}",
        "raw_count": result.raw_count, "filtered": filt,
        "issues": len(result.issues), "decisions": len(result.decisions), "folded_into_decisions": folded,
        "compression": round(result.raw_count / len(result.issues), 1) if result.issues else 0,
        "per_band": result.per_band(),
        "coverage": coverage_view(result, lang),
        "causes": [{"id": c.id, "kind": c.kind, "confidence": c.confidence, "issues": len(c.issue_ids),
                    **cause_text(c, lang)} for c in result.causes[:5]],
        "top": [brief(i, profile, lang) for i in result.issues[:top]],
        "hotspots": hotspots(result, limit=3),
        "matrix": dict(list(matrix(result).items())[:8]),
    }
