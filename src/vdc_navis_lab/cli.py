"""Command line: analyse an export offline, write a sample, run the simulator, validate a profile."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import exports, ingest, views
from .bridge.simulator import Simulator
from .engine import analyze
from .plugins import load_plugins
from .profile import Profile, ProfileError
from .sample.generator import build


def _cmd_analyze(args: argparse.Namespace) -> int:
    profile = Profile.load(args.profile)
    result = analyze(ingest.load(args.file), profile, args.lang)
    if args.json:
        print(json.dumps(views.summary(result, profile, args.top), ensure_ascii=False, indent=2))
    else:
        print(exports.to_markdown(result, profile, args.top))
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    cs, _ = build(args.seed)
    Path(args.path).write_text(json.dumps(cs.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(cs.clashes)} clashes to {args.path}")
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    clashset = None
    if args.infra:
        from .sample.generator import build_infra
        parts = [int(x) for x in args.infra.split(":")]
        clashset = build_infra(parts[0], parts[1], args.seed, per_place=parts[2] if len(parts) > 2 else 6)
    sim = Simulator(seed=args.seed, port=args.port, clashset=clashset, page_delay=args.page_delay)
    endpoint = sim.start(register=True)
    print(f"Navisworks simulator listening on {endpoint} (document {sim.title}). Ctrl-C to stop.")
    print("Start the MCP server in another terminal: it discovers this instance automatically.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
    return 0


def _cmd_tools(args: argparse.Namespace) -> int:
    from .server import init_plugins, mcp
    init_plugins()
    for t in asyncio.run(mcp.list_tools()):
        title = t.annotations.title if t.annotations and t.annotations.title else ""
        print(f"{t.name:<13} {title}")
    return 0


def _cmd_call(args: argparse.Namespace) -> int:
    """One stateless call. State (analysis, plans) lives in the server process, so use `demo` for flows."""
    from .server import init_plugins, mcp
    init_plugins()
    try:
        params = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as exc:
        print(f"error: the arguments are not valid JSON ({exc.msg})", file=sys.stderr)
        return 2
    try:
        res = asyncio.run(mcp.call_tool(args.tool, params))
    except Exception as exc:  # unknown tool or invalid arguments
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(res.content[0].text if res.content else "")
    return 1 if res.is_error else 0


def _cmd_demo(args: argparse.Namespace) -> int:
    """Whole flow in one process against the simulator: status, analyze, preview, execute, verify."""
    from .service import App, ToolFault
    es = args.lang == "es"
    sim = Simulator(job_delay=0.05)
    scratch = tempfile.TemporaryDirectory(prefix="vdc-navis-lab-demo-")  # the demo never touches your own data folder
    os.environ["VDC_NAVIS_LAB_HOME"] = scratch.name
    os.environ["VDC_NAVIS_LAB_ENDPOINT"] = sim.start()
    os.environ["VDC_NAVIS_LAB_READ_ONLY"] = "0"
    app = App()
    load_plugins(app)

    def step(n: int, es_text: str, en_text: str) -> None:
        print(f"\n[{n}] {es_text if es else en_text}")

    try:
        step(1, "Estado: ¿hay un Navisworks conectado?", "Status: is a Navisworks connected?")
        st = app.status()
        t = st["tests"]
        print(f"    {'conectado' if es else 'connected'}: {st['bridge']['instances'][0]['document']}; "
              f"{t['count']} tests, {'nunca ejecutados' if es else 'never run'}: {', '.join(t['never_run']) or '-'}")

        step(2, "Análisis: de clashes crudos a problemas priorizados", "Analysis: from raw clashes to ranked issues")
        a = app.analyze("", None, 3, 20, "", args.lang)
        print(f"    {a['raw_count']} {'cruces' if es else 'clashes'} -> {a['issues']} "
              f"{'problemas' if es else 'issues'}; {a['per_band']}")
        for item in a["top"]:
            print(f"    {item.get('id')}  {str(item.get('priority')).upper():<8} {item.get('pair', '')} "
                  f"{item.get('level', '')}  score {item.get('score')}")
        for w in a.get("coverage", {}).get("warnings", [])[:3]:
            print(f"    ! {w}")

        step(3, "Plan de escritura (simulación, no cambia nada)", "Write plan (preview, changes nothing)")
        plan = app.apply([{"op": "group", "issues": "top:3"}], "", True)
        print(f"    plan_id {plan['plan_id']}: {plan['issues']} {'problemas' if es else 'issues'}, "
              f"{'vence en' if es else 'expires in'} {plan['expires_in_s']} s")

        step(4, "Ejecución del plan y verificación por relectura", "Execute the plan and verify by re-reading")
        try:
            done = app.apply(None, plan["plan_id"], False)
            print(f"    {done['state']}; {'verificado' if es else 'verified'}: {done['verified']}")
        except ToolFault as exc:
            if exc.code != "pro_required":
                raise
            print("    " + ("Ejecutar planes es una capacidad Pro (pro_required): aquí solo se ve la vista previa; el análisis y los informes siguen disponibles."
                            if es else "Executing plans is a Pro capability (pro_required): only the preview runs here; analysis and reports keep working."))

        step(5, "Instantánea de la entrega", "Snapshot of the delivery")
        sn = app.snapshot("save", "demo", "")
        print(f"    {'guardada' if es else 'saved'}: demo ({sn.get('issues')} {'problemas' if es else 'issues'})")
        print("\n" + ("Listo. Todo esto ocurrió contra un Navisworks simulado." if es
                      else "Done. All of this ran against a simulated Navisworks."))
        return 0
    except ToolFault as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        sim.stop()
        scratch.cleanup()


def _cmd_verify(args: argparse.Namespace) -> int:
    """Self-check, safe to paste: PASS/FAIL and figures only (names never printed)."""
    from . import verify
    from .service import App
    sim = None
    scratch = None
    if args.simulate:
        sim = Simulator(job_delay=0.05)
        scratch = tempfile.TemporaryDirectory(prefix="vdc-navis-lab-verify-home-")
        os.environ["VDC_NAVIS_LAB_HOME"] = scratch.name
        os.environ["VDC_NAVIS_LAB_ENDPOINT"] = sim.start()
    if args.writes:
        os.environ["VDC_NAVIS_LAB_READ_ONLY"] = "0"
    try:
        print(f"vdc-navis-lab verify ({'simulator' if args.simulate else 'live Navisworks'}, "
              f"writes {'ON' if args.writes else 'off'})")
        app = App()
        load_plugins(app)
        rep = verify.run(app, writes=args.writes, wait_s=args.wait)
        if rep.nw_peak_mb is not None:
            print(f"Navisworks peak memory: {rep.nw_peak_mb} MB")
        note = f" ({rep.skipped} skipped: Pro capability not available, so not proven)" if rep.skipped else ""
        print("RESULT: " + (f"ALL PASS{note}" if rep.ok else f"{sum(not c.ok for c in rep.checks)} FAILED (details in verify.log in the data folder)"))
        return 0 if rep.ok else 1
    finally:
        if sim:
            sim.stop()
        if scratch:
            scratch.cleanup()


def _cmd_field_test(args: argparse.Namespace) -> int:
    """One command for the machine under test: versions, verify, bench --live, nw_analyze, and a report with no names."""
    from . import field_test
    from .service import App
    try:
        equipo, modelo = field_test.check_id(args.equipo, "--equipo"), field_test.check_id(args.modelo, "--modelo")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sim = scratch = None
    if args.simulate:
        sim = Simulator(job_delay=0.05)
        scratch = tempfile.TemporaryDirectory(prefix="vdc-navis-lab-field-")
        os.environ["VDC_NAVIS_LAB_HOME"] = scratch.name
        os.environ["VDC_NAVIS_LAB_ENDPOINT"] = sim.start()
    writes = False
    if args.sin_escrituras:
        pass
    elif args.confirmo_copia:
        writes = True
    elif sys.stdin is not None and sys.stdin.isatty():
        print("\nLa prueba de escritura crea un grupo, un estado y un punto de vista en el modelo abierto (en memoria, no guarda).")
        print("Hágala solo sobre una COPIA del modelo, nunca sobre el original.")
        ans = input(f"Escriba {field_test.COPY_WORD} si el modelo abierto es una copia (Enter para omitir las escrituras): ")
        writes = ans.strip().upper() == field_test.COPY_WORD
    if writes:
        os.environ["VDC_NAVIS_LAB_READ_ONLY"] = "0"
    try:
        app = App()
        load_plugins(app)
        report, paths = field_test.run(app, equipo=equipo, modelo=modelo, writes=writes, wait_s=args.wait, bench_wait_s=args.bench_wait,
                                       out_dir=Path(args.out) if args.out else None)
        print("\n----- copiar desde aquí (sin nombres de proyecto, modelo, archivo, prueba ni ruta) -----\n")
        print(paths[1].read_text(encoding="utf-8"))
        print("----- hasta aquí -----")
        print(f"Archivos del informe (JSON y markdown) en la carpeta {paths[0].parent.name} dentro de la carpeta de datos, o en la indicada con --out.")
        return 0 if report["verdict"] == "PASS" else 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if sim:
            sim.stop()
        if scratch:
            scratch.cleanup()


def _cmd_bench(args: argparse.Namespace) -> int:
    """Scale measurement. Prints figures only (no names), so it is safe to paste."""
    from . import bench
    if args.paged:
        bench.run_paged(args.tests, args.per_test, args.seed, args.per_place, args.wait)
        return 0
    if args.live:
        from .service import App, ToolFault
        if args.writes:
            os.environ["VDC_NAVIS_LAB_READ_ONLY"] = "0"
        try:
            app = App()
            load_plugins(app)
            bench.run_live(app, wait_s=args.wait)
        except ToolFault as exc:
            print(f"error: {exc.code}", file=sys.stderr)
            return 1
        return 0
    if args.file:
        bench.run_file(args.file)
    else:
        bench.run_synthetic(args.tests, args.per_test, args.seed, args.per_place)
    return 0


def _cmd_llm_eval(args: argparse.Namespace) -> int:
    """Tool-calling evaluation of a model served on an OpenAI-compatible endpoint (LM Studio), against the simulator."""
    from . import llm_eval
    from .paths import home
    chat = llm_eval.http_chat(args.base_url, args.model, args.api_key)
    print(f"llm-eval: model {args.model} at {args.base_url}; {args.reps} repetitions per scenario, simulator only")
    runs, scenarios = llm_eval.evaluate(chat, args.reps, args.only or None)
    rows = llm_eval.summarise(runs, scenarios)
    print()
    llm_eval.print_table(rows)
    path = llm_eval.write_results(Path(args.out) if args.out else home() / "llm_eval", args.model, args.hardware, runs, rows)
    print(f"\nResults and transcripts (simulator data only): {path}")
    return 0 if all(r["correct_pct"] == 100 for r in rows) else 1


LEGACY_NAME = "navis" + "-mcp"


def _desktop_config_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _lmstudio_config_path() -> Path:
    return Path.home() / ".lmstudio" / "mcp.json"   # %USERPROFILE%\\.lmstudio\\mcp.json on Windows


def _server_command() -> str:
    exe = "vdc-navis-lab.exe" if sys.platform == "win32" else "vdc-navis-lab"
    beside = Path(sys.executable).parent / exe  # the venv this command runs from
    return str(beside) if beside.exists() else (shutil.which("vdc-navis-lab") or str(beside))


def _cmd_desktop_config(args: argparse.Namespace) -> int:
    """Print the Claude Desktop entry, or merge it into the config file without touching anything else."""
    entry = {"command": _server_command(), "env": {"VDC_NAVIS_LAB_READ_ONLY": "0" if args.allow_writes else "1"}}
    lm = getattr(args, "client", "claude") == "lmstudio"
    path = Path(args.config) if args.config else (_lmstudio_config_path() if lm else _desktop_config_path())
    app_name = "LM Studio" if lm else "Claude Desktop"
    if not args.write:
        print(f"Config file: {path}")
        print("Add this INSIDE the existing \"mcpServers\" object (comma after the previous entry), or run again with --write:\n")
        print(json.dumps({"vdc-navis-lab": entry}, indent=2)[2:-2])
        return 0
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
        except json.JSONDecodeError as exc:
            print(f"error: {path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg}). Nothing was written; "
                  "fix or restore the file first.", file=sys.stderr)
            return 1
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
            print(f"error: {path} does not have the expected shape. Nothing was written.", file=sys.stderr)
            return 1
        backup = path.with_name(path.name + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
        shutil.copy2(path, backup)
        print(f"backup: {backup}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    servers = data.setdefault("mcpServers", {})
    legacy = servers.get(LEGACY_NAME)  # the entry from before the project was renamed
    if isinstance(legacy, dict) and LEGACY_NAME in str(legacy.get("command", "")):
        del servers[LEGACY_NAME]
        print(f"removed the old '{LEGACY_NAME}' entry (replaced by 'vdc-navis-lab')")
    servers["vdc-navis-lab"] = entry
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if lm:
        print(f"vdc-navis-lab added to {path}. In LM Studio open the Program tab, check that the server shows up and load a model with tool use. "
              "Keep 'always allow' off for nw_apply, nw_setup and nw_document: LM Studio then asks before each write.")
    else:
        print(f"vdc-navis-lab added to {path}. Quit {app_name} completely and open it again.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        p = Profile.load(args.path)
    except ProfileError as exc:
        print(f"invalid: {exc}")
        return 1
    print(f"profile '{p.name}' is valid: {len(p.disciplines)} disciplines, checksum {p.checksum}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vdc-navis-lab-cli", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse a .json/.xml/.csv clash export and print a report")
    a.add_argument("file")
    a.add_argument("--profile", default=None)
    a.add_argument("--lang", choices=["es", "en"], default=None)
    a.add_argument("--top", type=int, default=15)
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=_cmd_analyze)
    s = sub.add_parser("sample", help="write the synthetic tower as a vdc-navis-lab JSON export")
    s.add_argument("path")
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=_cmd_sample)
    m = sub.add_parser("simulate", help="run a fake Navisworks add-in for demos and development")
    m.add_argument("--seed", type=int, default=7)
    m.add_argument("--port", type=int, default=0)
    m.add_argument("--infra", default="", help="serve a synthetic infrastructure federation, TESTS:RESULTS_PER_TEST[:PER_PLACE], instead of the tower")
    m.add_argument("--page-delay", type=float, default=0.0, help=argparse.SUPPRESS)
    m.set_defaults(fn=_cmd_simulate)
    d = sub.add_parser("demo", help="guided walk-through against a simulated Navisworks, no setup needed")
    d.add_argument("--lang", choices=["es", "en"], default="es")
    d.set_defaults(fn=_cmd_demo)
    tl = sub.add_parser("tools", help="list the MCP tools")
    tl.set_defaults(fn=_cmd_tools)
    vf = sub.add_parser("verify", help="self-check against Navisworks (or --simulate); prints PASS/FAIL and figures only")
    vf.add_argument("--simulate", action="store_true", help="use the built-in simulator instead of a live Navisworks")
    vf.add_argument("--writes", action="store_true", help="also test writing a group, a status and a viewpoint (changes the open document in memory; never saves)")
    vf.add_argument("--wait", type=float, default=900.0, help="seconds to wait for slow steps such as the census")
    vf.set_defaults(fn=_cmd_verify)
    bn = sub.add_parser("bench", help="measure time and memory at scale; prints figures only (synthetic, --file, or --live)")
    bn.add_argument("--tests", type=int, default=240, help="synthetic: number of tests")
    bn.add_argument("--per-test", type=int, default=3000, help="synthetic: results per test")
    bn.add_argument("--per-place", type=int, default=6, help="synthetic: results per place (6 sparse; 100 or more is a congested corridor)")
    bn.add_argument("--seed", type=int, default=11)
    bn.add_argument("--file", default="", help="measure an exported clash file instead of generating one")
    bn.add_argument("--live", action="store_true", help="measure the whole path against the Navisworks that is open now")
    bn.add_argument("--paged", action="store_true", help="whole path (pipe, paged extraction, analysis) against the simulator serving the synthetic federation")
    bn.add_argument("--wait", type=float, default=1800.0, help="--live, --paged: seconds to wait for the extraction")
    bn.add_argument("--writes", action="store_true", help=argparse.SUPPRESS)
    bn.set_defaults(fn=_cmd_bench)
    ft = sub.add_parser("field-test", help="field test on this machine: versions, verify, bench --live, nw_analyze; writes a report of figures with no names")
    ft.add_argument("--equipo", default="E1", help="generic identifier of this machine in the campaign (E1, E2, ...)")
    ft.add_argument("--modelo", default="M1", help="generic identifier of the open model (M1, M2, ...); never its name")
    ft.add_argument("--confirmo-copia", action="store_true", help="the open model is a copy: allow the write test (without it, it is asked on the keyboard)")
    ft.add_argument("--sin-escrituras", action="store_true", help="read-only run, skip the write test")
    ft.add_argument("--simulate", action="store_true", help="rehearse against the built-in simulator instead of a live Navisworks")
    ft.add_argument("--out", default="", help="folder for the report files (default: field-test inside the data folder)")
    ft.add_argument("--wait", type=float, default=900.0, help="seconds to wait for slow steps")
    ft.add_argument("--bench-wait", type=float, default=1800.0, help="seconds to wait for the extraction in bench --live")
    ft.set_defaults(fn=_cmd_field_test)
    le = sub.add_parser("llm-eval", help="evaluate a model's tool use against the simulator (LM Studio or any OpenAI-compatible endpoint)")
    le.add_argument("--model", required=True, help="model name as the server lists it")
    le.add_argument("--base-url", default="http://localhost:1234/v1", help="LM Studio's default")
    le.add_argument("--api-key", default="lm-studio")
    le.add_argument("--reps", type=int, default=5, help="repetitions per scenario (the plan uses 5)")
    le.add_argument("--only", nargs="*", help="scenario keys: estado top10 explicar dos_pasos informe ambigua masiva")
    le.add_argument("--hardware", default="", help="free text recorded with the results (CPU, RAM, GPU, VRAM)")
    le.add_argument("--out", default="", help="folder for results (default: the data folder, outside git)")
    le.set_defaults(fn=_cmd_llm_eval)
    ca = sub.add_parser("call", help="call one tool once: vdc-navis-lab-cli call nw_profile '{\"action\":\"show\"}'")
    ca.add_argument("tool")
    ca.add_argument("args", nargs="?", default="")
    ca.set_defaults(fn=_cmd_call)
    dc = sub.add_parser("desktop-config", help="print or safely merge the MCP client entry (Claude Desktop or LM Studio) for this install")
    dc.add_argument("--client", choices=["claude", "lmstudio"], default="claude",
                    help="which MCP client's config to print or merge (LM Studio reads ~/.lmstudio/mcp.json)")
    dc.add_argument("--write", action="store_true", help="merge into the config file (a backup is made first)")
    dc.add_argument("--allow-writes", action="store_true", help="do not set VDC_NAVIS_LAB_READ_ONLY=1")
    dc.add_argument("--config", default=None, help="config file path (default: the Claude Desktop location)")
    dc.set_defaults(fn=_cmd_desktop_config)
    c = sub.add_parser("check-profile", help="validate a profile .toml")
    c.add_argument("path", nargs="?", default=None)
    c.set_defaults(fn=_cmd_check)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (ProfileError, ingest.IngestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
