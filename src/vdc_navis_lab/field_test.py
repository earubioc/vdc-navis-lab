"""Field test: `vdc-navis-lab-cli field-test`. One command on the machine under test.

It detects the versions, runs `verify` (with the write plan only when the person confirms that the open model is a copy),
`bench --live` and `nw_analyze`, and writes a report of aggregate figures as JSON and markdown, ready to paste into a
conversation. The report is built from numbers and fixed words, and then passed through the sanitizer (sanitize.py), so it
holds no project, model, file, test or path names. Nothing leaves the computer by itself: the person pastes it.
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import platform
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import bench, verify
from .paths import home
from .sanitize import Sanitizer, Scrubber, numbers_only, vocabulary
from .service import App, ToolFault

REPORT_VERSION = 1
# Words that our own text may contain besides the ones in verify.py and this module (Navisworks reports its product name).
EXTRA_WORDS = ("navisworks", "autodesk", "manage", "simulate", "freedom", "unknown", "simulator", "windows", "linux", "darwin",
               "true", "false", "none", "cap", "cancelled", "time", "memory", "memory_server", "memory_addin",
               "groups", "statuses", "viewpoints", "sets")  # values formatted into our text
CODE_SHAPE = re.compile(r"[A-Za-z_]{1,40}")  # an error code or an exception class: what a failed check is allowed to say
ID_RE = re.compile(r"[A-Z][0-9]{1,2}")  # E1, M2: generic identifiers, the only free text allowed into the report
COPY_WORD = "COPIA"


def check_id(value: str, what: str) -> str:
    v = (value or "").strip().upper()
    if not ID_RE.fullmatch(v):
        raise ValueError(f"{what}: use a generic identifier such as E1 or M1 (a letter and one or two digits), not a name")
    return v


def _vocab() -> frozenset[str]:
    from . import field_test as me
    return vocabulary(verify, me, extra=EXTRA_WORDS)


def safe_version(text: Any, scrub: Scrubber) -> str | None:
    s = str(text or "").strip()
    return scrub.scrub(s)[:60] if re.fullmatch(r"[0-9A-Za-z .\-+()_]{1,80}", s) else None


# ---------------------------------------------------------------- the machine
def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = Mem()
            m.dwLength = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 2**30, 1)
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as f:
                return round(int(f.readline().split()[1]) / 2**20, 1)
    except Exception:
        return None
    return None


def installed_navisworks(program_files: Path | None = None) -> dict[str, Any]:
    """Navisworks Manage years found under Program Files and, for each, whether the add-in is in its Plugins folder with
    which file version. Years and versions only: no path leaves this function."""
    base = program_files or Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"
    years: dict[str, Any] = {}
    try:
        entries = sorted(base.glob("Navisworks Manage *"))
    except OSError:
        entries = []
    for d in entries:
        m = re.fullmatch(r"Navisworks Manage (\d{4})", d.name)
        if not m:
            continue
        dll = d / "Plugins" / "VdcNavisLab" / "VdcNavisLab.dll"
        info: dict[str, Any] = {"addin_installed": dll.is_file(), "addin_file_version": None}
        if dll.is_file():
            info["addin_file_version"] = _file_version(dll)
        years[m.group(1)] = info
    return years


def _file_version(dll: Path) -> str | None:
    if sys.platform != "win32":
        return None
    import subprocess
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{dll}').VersionInfo.ProductVersion"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return out if re.fullmatch(r"[0-9.]{1,20}", out) else None
    except (OSError, subprocess.SubprocessError):
        return None


def environment(app: App, program_files: Path | None = None) -> dict[str, Any]:
    from . import __version__
    ext = app.status().get("extensions", {})
    plugins = []
    for p in ext.get("plugins", []):
        plugins.append({"name": p.get("name") if re.fullmatch(r"[a-z0-9_.\-]{1,40}", str(p.get("name"))) else "plugin",
                        "version": p.get("version") if re.fullmatch(r"[0-9A-Za-z.+\-]{1,20}", str(p.get("version"))) else None,
                        "state": p.get("state") if re.fullmatch(r"[a-z_]{1,32}", str(p.get("state"))) else None,
                        "license": {k: v for k, v in (p.get("license") or {}).items()
                                    if k in ("state", "kind", "days_left") and (isinstance(v, int) or re.fullmatch(r"[a-z_]{1,32}", str(v)))}})
    system, release = platform.system(), platform.release()
    osname = f"{system} {release}" if system == "Windows" and re.fullmatch(r"\d{1,2}", release) else system  # a kernel string is noise
    return {"os": osname if re.fullmatch(r"(Windows \d{1,2}|Windows|Linux|Darwin)", osname) else "otro", "python": platform.python_version(),
            "cpu_logical": os.cpu_count(), "ram_gb": _ram_gb(), "server": __version__,
            "navisworks_installed": installed_navisworks(program_files),
            "plugins": plugins, "capabilities_available": len(ext.get("available", [])),
            "capabilities_missing": len(ext.get("missing", [])), "read_only_default": app.read_only}


# ---------------------------------------------------------------- names the run saw (to be masked, never printed)
def collect_terms(app: App, extra: list[str] | None = None) -> list[str]:
    terms: list[str] = list(extra or [])
    for fn in (getpass.getuser, socket.gethostname, lambda: Path.home().name, lambda: Path.cwd().name, lambda: platform.node()):
        try:
            terms.append(fn())
        except Exception:
            pass
    try:
        st = app.status()
        for i in st["bridge"]["instances"]:
            terms += [i.get("document") or ""]
        t = st.get("tests") or {}
        terms += [it.get("name", "") for it in t.get("items", [])] + list(t.get("never_run", []))
    except Exception:
        pass
    try:
        s = app.setup("list", None, "", True)
        terms += [str(s.get("document") or "")] + [str(x.get("name", "")) for x in s.get("tests", [])]
        terms += [str(x.get("name", x) if isinstance(x, dict) else x) for x in s.get("sets", [])]
    except Exception:
        pass
    try:
        ep, _, _ = app.bridge.resolve(False)
        info = app.bridge.call_at(ep, "doc.info", None, 60.0)
        terms += [str(info.get("title") or "")] + [str(m) for m in info.get("models", [])]
        terms += [Path(str(m).replace("\\", "/")).name for m in info.get("models", [])]
    except Exception:
        pass
    return [t for t in terms if t]


# ---------------------------------------------------------------- sections
def _coverage(cov: dict[str, Any]) -> dict[str, Any]:
    ex = cov.get("extraction") or {}
    part = cov.get("partial") or {}
    return {
        "complete": bool(cov.get("complete")), "tests": cov.get("tests") if re.fullmatch(r"\d+/\d+", str(cov.get("tests", ""))) else None,
        "never_run": len(cov.get("never_run") or []), "pairs_without_results": len(cov.get("pairs_without_results") or []),
        "silenced_tests": len(cov.get("silenced_tests") or []), "skipped": cov.get("skipped"), "skipped_open": cov.get("skipped_open"),
        "sleeves_modeled": cov.get("sleeves_modeled"),
        "extraction": numbers_only(ex) if ex else None,
        "partial": ({"reasons": [r.get("code") for r in part.get("reasons", []) if re.fullmatch(r"[a-z_]{1,32}", str(r.get("code", "")))],
                     "open_extracted": part.get("open_extracted"), "open_available": part.get("open_available"),
                     "tests_partial": part.get("tests_partial"), "tests_total": part.get("tests_total")} if part else None),
    }


def _code(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or type(exc).__name__)
    return code if re.fullmatch(r"[A-Za-z_]{1,32}", code) else "error"


def analyze_section(app: App, wait_s: float) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        a = verify._wait(lambda: app.analyze("", None, 5, 45, "", None), wait_s)
        if a.get("state") == "running":
            a = verify._wait(lambda: app.analyze("", None, 5, 45, a.get("job_id", ""), None), wait_s)
    except Exception as exc:  # ToolFault, BridgeError: the report says the code, never the message
        return {"state": "error", "code": _code(exc), "seconds": round(time.monotonic() - t0, 1)}
    if a.get("state") == "running":
        return {"state": "running", "seconds": round(time.monotonic() - t0, 1)}
    return {"state": "done", "seconds": round(time.monotonic() - t0, 1), "raw_results": a["raw_count"], "issues": a["issues"],
            "decisions": a.get("decisions"), "compression": a.get("compression"), "bands": numbers_only(a["per_band"]),
            "filtered_total": sum(int(v) for v in (a.get("filtered") or {}).values()), "causes": len(a.get("causes") or []),
            "coverage": _coverage(a.get("coverage") or {})}


def bench_section(app: App, wait_s: float) -> dict[str, Any]:
    quiet: Callable[[str], None] = lambda _s: None  # the figures come from the returned dict, not from the printed lines
    try:
        out = bench.run_live(app, wait_s, quiet)
    except Exception as exc:
        return {"state": "error", "code": _code(exc)}
    keep = {k: out.get(k) for k in ("results", "tests", "analysis_s", "peak_mb", "nw_peak_mb", "finished", "raw", "issues", "complete",
                                   "skipped", "capped", "full_hello_ms")}
    keep["extraction"] = numbers_only(out.get("extraction")) if out.get("extraction") else None
    keep["pings"] = numbers_only(out.get("pings")) if out.get("pings") else None
    partial = out.get("partial")
    keep["partial"] = {"open_extracted": partial.get("open_extracted"), "open_available": partial.get("open_available"),
                       "reasons": [r.get("code") for r in partial.get("reasons", []) if re.fullmatch(r"[a-z_]{1,32}", str(r.get("code", "")))]} if partial else None
    keep["state"] = "done" if out.get("finished", True) else "running"
    return {k: v for k, v in keep.items() if v is not None}


def verify_section(rep: verify.Report, writes: str, scrub: Scrubber) -> dict[str, Any]:
    def detail(c: verify.Check) -> str:
        if c.ok:
            return scrub.scrub(c.detail)  # our own template and figures: only words our code uses survive
        return c.detail if CODE_SHAPE.fullmatch(c.detail or "") else "error"  # a failure says its code, never free text
    checks = [{"name": scrub.scrub(c.name), "status": "SKIP" if c.skipped else ("PASS" if c.ok else "FAIL"), "seconds": round(c.seconds, 1),
               "detail": detail(c)} for c in rep.checks]
    failed = sum(not c.ok for c in rep.checks)
    return {"result": "ALL PASS" if rep.ok else f"{failed} FAILED", "failed": failed, "skipped": rep.skipped, "writes": writes,
            "navisworks_peak_mb": rep.nw_peak_mb, "figures": rep.figures, "checks": checks}


def verdict(v: dict[str, Any], b: dict[str, Any], a: dict[str, Any]) -> str:
    if v["failed"] or b.get("state") == "error" or a.get("state") == "error":
        return "FAIL"
    if b.get("state") == "running" or a.get("state") == "running":
        return "INCOMPLETE"
    return "PASS"


# ---------------------------------------------------------------- markdown
def to_markdown(r: dict[str, Any]) -> str:
    e, v, b, a = r["environment"], r["verify"], r.get("bench", {}), r.get("analyze", {})
    nw = r["navisworks"]
    lines = [f"## Prueba de campo {r['equipo']} / {r['modelo']}: {r['verdict']}", "",
             f"Fecha {r['date']}. Servidor {e['server']}, add-in {nw.get('addin_version') or 'sin dato'}, Navisworks {nw.get('version') or 'sin dato'}. "
             f"Python {e['python']}, {e['os']}, {e['cpu_logical']} núcleos, {e['ram_gb']} GB de RAM.", ""]
    pro = next((p for p in e["plugins"] if p["name"] == "pro"), None)
    if pro:
        lic = pro.get("license") or {}
        left = f", vence en {lic['days_left']} días" if lic.get("state") == "valid" and "days_left" in lic else ""
        lines.append(f"Pro {pro['version']} ({pro['state']}); licencia {lic.get('state', 'sin dato')}{left}.")
    else:
        lines.append("Pro: no instalado (Community).")
    lines += [f"Escrituras: {v['writes']}. Capacidades disponibles {e['capabilities_available']}, ausentes {e['capabilities_missing']}.", "",
              f"### verify: {v['result']}" + (f" ({v['skipped']} omitidas por Pro)" if v["skipped"] else ""), "",
              "| Paso | Estado | s | Detalle |", "|---|---|---:|---|"]
    for c in v["checks"]:
        lines.append(f"| {c['name']} | {c['status']} | {c['seconds']} | {c['detail']} |")
    f = v.get("figures", {})
    if f:
        lines += ["", f"Conteos: {f.get('tests', '?')} pruebas, {f.get('results', '?')} resultados, {f.get('models', '?')} modelos, "
                      f"{f.get('elements', '?')} elementos; {f.get('issues', '?')} problemas; bandas crítica {(f.get('bands') or {}).get('critical', '?')}, "
                      f"alta {(f.get('bands') or {}).get('high', '?')}, media {(f.get('bands') or {}).get('medium', '?')}, baja {(f.get('bands') or {}).get('low', '?')}."]
    if v.get("navisworks_peak_mb"):
        lines.append(f"Memoria máxima de Navisworks durante verify: {v['navisworks_peak_mb']} MB.")
    lines += ["", f"### bench --live: {b.get('state', 'sin dato')}"]
    if b.get("state") in ("done", "running"):
        lines.append(f"{b.get('results', '?')} resultados en {b.get('tests', '?')} pruebas; extracción y análisis {b.get('analysis_s', '?')} s; "
                     f"{b.get('raw', '?')} resultados crudos a {b.get('issues', '?')} problemas; completo {b.get('complete', '?')}. "
                     f"Memoria: servidor {b.get('peak_mb', '?')} MB, Navisworks {str(b['nw_peak_mb']) + ' MB' if b.get('nw_peak_mb') else 'sin dato'}.")
        if b.get("extraction"):
            x = b["extraction"]
            lines.append(f"Extracción: {x.get('described', '?')} descritos en {x.get('pages', '?')} tramos ({x.get('seconds', '?')} s), "
                         f"tramo más lento {x.get('slowest_slice_s', '?')} s, {x.get('waited_for_navisworks', '?')} esperas a un Navisworks ocupado.")
        elif b.get("state") == "done":
            lines.append("El add-in instalado no tiene extracción por tramos (reinstalar el MSI de esta versión).")
        if b.get("pings"):
            p = b["pings"]
            lines.append(f"Capacidad de respuesta de Navisworks: {p.get('n', '?')} sondeos, {p.get('failed', '?')} sin respuesta, "
                         f"mediana {p.get('median_ms', '?')} ms, máximo {p.get('max_ms', '?')} ms.")
        if b.get("partial"):
            lines.append(f"PARCIAL ({', '.join(b['partial']['reasons'])}): {b['partial']['open_extracted']} de {b['partial']['open_available']} abiertos.")
    elif b.get("code"):
        lines.append(f"Error: {b['code']}.")
    lines += ["", f"### nw_analyze: {a.get('state', 'sin dato')}"]
    if a.get("state") == "done":
        bands = a.get("bands", {})
        c = a["coverage"]
        lines.append(f"{a['raw_results']} resultados crudos a {a['issues']} problemas en {a['seconds']} s; bandas crítica {bands.get('critical', 0)}, "
                     f"alta {bands.get('high', 0)}, media {bands.get('medium', 0)}, baja {bands.get('low', 0)}; filtrados {a['filtered_total']}; "
                     f"{a.get('causes', 0)} causas comunes.")
        lines.append(f"Cobertura: completa {c['complete']}; pruebas con resultados {c.get('tests')}; nunca ejecutadas {c['never_run']}; "
                     f"pares sin resultados {c['pairs_without_results']}; omitidos {c.get('skipped')}"
                     + (f"; PARCIAL ({', '.join(c['partial']['reasons'])})" if c.get("partial") else "") + ".")
    elif a.get("code"):
        lines.append(f"Error: {a['code']}.")
    lines += ["", f"Informe sin nombres de proyecto, modelo, archivo, prueba ni ruta ({r['redactions']} textos omitidos por el sanitizador)."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- the run
def run(app: App, *, equipo: str, modelo: str, writes: bool, wait_s: float = 900.0, bench_wait_s: float = 1800.0,
        say: Callable[[str], None] = print, out_dir: Path | None = None, program_files: Path | None = None,
        extra_terms: list[str] | None = None, now: datetime.datetime | None = None) -> tuple[dict[str, Any], list[Path]]:
    """`writes` is True only after the person confirmed that the open model is a copy."""
    equipo, modelo = check_id(equipo, "equipo"), check_id(modelo, "modelo")
    san = Sanitizer(collect_terms(app, extra_terms))
    scrub = Scrubber(_vocab())
    out = lambda s: say(scrub.scrub(san.clean(s)))  # noqa: E731
    now = now or datetime.datetime.now()
    env = environment(app, program_files)
    out(f"field-test {equipo}/{modelo}: servidor {env['server']}, {env['os']}, Python {env['python']}")

    out("1/3 verify" + (" con escrituras (sobre la copia)" if writes else " solo lectura"))
    rep = verify.run(app, writes=writes, wait_s=wait_s, say=out)
    wmode = ("ejecutadas sobre la copia" if writes else "no ejecutadas (copia no confirmada o desactivadas)")
    if writes and any(c.skipped and c.name.startswith("write plan") for c in rep.checks):
        wmode = "omitidas: requieren Pro con licencia vigente"
    out("2/3 bench --live")
    b = bench_section(app, bench_wait_s)
    out("3/3 nw_analyze")
    a = analyze_section(app, wait_s)
    v = verify_section(rep, wmode, scrub)
    inst = (rep.figures or {})
    report: dict[str, Any] = {
        "report_version": REPORT_VERSION, "kit": "vdc-navis-lab field-test", "date": now.strftime("%Y-%m-%d"),
        "equipo": equipo, "modelo": modelo, "environment": env,
        "navisworks": {"version": safe_version(inst.get("navisworks_version"), scrub),
                       "addin_version": inst.get("addin_version") if re.fullmatch(r"[0-9.]{1,20}|simulator|unknown", str(inst.get("addin_version"))) else None},
        "verify": v, "bench": b, "analyze": a, "verdict": verdict(v, b, a)}
    report["environment"]["read_only_default"] = bool(report["environment"].get("read_only_default"))
    clean = san.clean_obj(report)
    clean["redactions"] = san.redactions + scrub.redactions
    md = san.clean(to_markdown(clean))
    clean["redactions"] = san.redactions + scrub.redactions
    text = json.dumps(clean, ensure_ascii=False, indent=2)
    if san.leaks(text) or san.leaks(md):  # cannot happen after cleaning; if it does, nothing is written
        raise RuntimeError("the sanitizer left a known name in the report; nothing was written")
    folder = out_dir or (home() / "field-test")
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{equipo}-{modelo}-{now.strftime('%Y%m%d-%H%M')}"
    paths = [folder / f"{stem}.json", folder / f"{stem}.md"]
    paths[0].write_text(text + "\n", encoding="utf-8")
    paths[1].write_text(md, encoding="utf-8")
    return clean, paths
