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
    sim = Simulator(seed=args.seed, port=args.port)
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
    from .server import mcp
    for t in asyncio.run(mcp.list_tools()):
        title = t.annotations.title if t.annotations and t.annotations.title else ""
        print(f"{t.name:<13} {title}")
    return 0


def _cmd_call(args: argparse.Namespace) -> int:
    """One stateless call. State (analysis, plans) lives in the server process, so use `demo` for flows."""
    from .server import mcp
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
    scratch = tempfile.TemporaryDirectory(prefix="navis-mcp-demo-")  # the demo never touches your own data folder
    os.environ["NAVIS_MCP_HOME"] = scratch.name
    os.environ["NAVIS_MCP_ENDPOINT"] = sim.start()
    os.environ["NAVIS_MCP_READ_ONLY"] = "0"
    app = App()

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
        done = app.apply(None, plan["plan_id"], False)
        print(f"    {done['state']}; {'verificado' if es else 'verified'}: {done['verified']}")

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


def _desktop_config_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _server_command() -> str:
    exe = "navis-mcp.exe" if sys.platform == "win32" else "navis-mcp"
    beside = Path(sys.executable).parent / exe  # the venv this command runs from
    return str(beside) if beside.exists() else (shutil.which("navis-mcp") or str(beside))


def _cmd_desktop_config(args: argparse.Namespace) -> int:
    """Print the Claude Desktop entry, or merge it into the config file without touching anything else."""
    entry = {"command": _server_command(), "env": {"NAVIS_MCP_READ_ONLY": "0" if args.allow_writes else "1"}}
    path = Path(args.config) if args.config else _desktop_config_path()
    if not args.write:
        print(f"Config file: {path}")
        print("Add this INSIDE the existing \"mcpServers\" object (comma after the previous entry), or run again with --write:\n")
        print(json.dumps({"navis-mcp": entry}, indent=2)[2:-2])
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
    data.setdefault("mcpServers", {})["navis-mcp"] = entry
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"navis-mcp added to {path}. Quit Claude Desktop completely and open it again.")
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
    parser = argparse.ArgumentParser(prog="navis-mcp-cli", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse a .json/.xml/.csv clash export and print a report")
    a.add_argument("file")
    a.add_argument("--profile", default=None)
    a.add_argument("--lang", choices=["es", "en"], default=None)
    a.add_argument("--top", type=int, default=15)
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=_cmd_analyze)
    s = sub.add_parser("sample", help="write the synthetic tower as a navis-mcp JSON export")
    s.add_argument("path")
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=_cmd_sample)
    m = sub.add_parser("simulate", help="run a fake Navisworks add-in for demos and development")
    m.add_argument("--seed", type=int, default=7)
    m.add_argument("--port", type=int, default=0)
    m.set_defaults(fn=_cmd_simulate)
    d = sub.add_parser("demo", help="guided walk-through against a simulated Navisworks, no setup needed")
    d.add_argument("--lang", choices=["es", "en"], default="es")
    d.set_defaults(fn=_cmd_demo)
    tl = sub.add_parser("tools", help="list the MCP tools")
    tl.set_defaults(fn=_cmd_tools)
    ca = sub.add_parser("call", help="call one tool once: navis-mcp-cli call nw_profile '{\"action\":\"show\"}'")
    ca.add_argument("tool")
    ca.add_argument("args", nargs="?", default="")
    ca.set_defaults(fn=_cmd_call)
    dc = sub.add_parser("desktop-config", help="print or safely merge the Claude Desktop entry for this install")
    dc.add_argument("--write", action="store_true", help="merge into the config file (a backup is made first)")
    dc.add_argument("--allow-writes", action="store_true", help="do not set NAVIS_MCP_READ_ONLY=1")
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
