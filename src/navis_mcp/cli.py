"""Command line: analyse an export offline, write a sample, run the simulator, validate a profile."""

from __future__ import annotations

import argparse
import json
import sys
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
