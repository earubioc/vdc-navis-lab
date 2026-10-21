"""MCP server: 14 tools, `nw_` prefix. Thin wrappers over service.App."""

from __future__ import annotations

import functools
import json
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .bridge import BridgeError
from .ingest import IngestError
from .paths import PathError
from .profile import ProfileError
from .service import App, ToolFault

INSTRUCTIONS = """\
navis-mcp coordinates clashes from Autodesk Navisworks Manage. Typical flow:
1. nw_status: is Navisworks reachable, is there an analysis, is it stale.
2. nw_run (only if tests never ran), then nw_analyze: ranked issues, root causes, coverage warnings.
   No Navisworks? nw_analyze(path=...) reads a Clash Detective XML/CSV or navis-mcp JSON export.
3. nw_issues / nw_issue to drill down; nw_report for markdown, csv, bcf, plan.
4. Writes are two steps: nw_apply(ops=[...]) previews and returns a plan_id; nw_apply(plan_id=...) executes
   and reports what was VERIFIED by re-reading the document.
Heavy data never enters the conversation: results are summaries or file paths.
Read the coverage warnings before claiming a discipline pair is clean: no results can mean never tested.
"""

mcp = MCPServer("navis-mcp", version=__version__, instructions=INSTRUCTIONS)
APP = App()


def _ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=True, open_world_hint=False)


def _add(title: str, idempotent: bool = False) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=False, destructive_hint=False,
                           idempotent_hint=idempotent, open_world_hint=False)


def _mutating(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, read_only_hint=False, destructive_hint=True, open_world_hint=False)


def guarded(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolFault as exc:
            raise ToolError(json.dumps(exc.to_dict(), ensure_ascii=False)) from None
        except BridgeError as exc:
            raise ToolError(json.dumps(exc.to_dict(), ensure_ascii=False)) from None
        except (ProfileError, IngestError, PathError) as exc:
            raise ToolError(json.dumps({"error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False)) from None
    return wrapper


@mcp.tool(annotations=_ro("Server, Navisworks and analysis status"))
@guarded
def nw_status() -> dict[str, Any]:
    """Where things stand: reachable Navisworks instances, the selected one, the active profile, whether an
    analysis exists and whether it is stale. Never fails when Navisworks is closed. Start here."""
    return APP.status()


@mcp.tool(annotations=_add("Choose a Navisworks instance", idempotent=True))
@guarded
def nw_connect(action: str = "list", target: str = "") -> dict[str, Any]:
    """Several Navisworks instances can be open. action='list' shows them, 'select' pins one by instance_id
    (required before any write when more than one is open), 'release' unpins."""
    return APP.connect(action, target)


@mcp.tool(annotations=_mutating("Cancel or watch background jobs"))
@guarded
def nw_job(action: str = "list", job_id: str = "") -> dict[str, Any]:
    """Long Navisworks operations run as jobs. action='status' (progress), 'list', or 'cancel' (stops at a safe point)."""
    return APP.job(action, job_id)


@mcp.tool(annotations=_add("Show, load or adjust the coordination profile", idempotent=True))
@guarded
def nw_profile(action: str = "show", path: str = "", mapping: dict[str, str] | None = None) -> dict[str, Any]:
    """The profile holds every coordination criterion (disciplines, weights, tolerances). action='show', 'validate'
    or 'load' (path to a .toml), 'reset', or 'assign' with mapping={"model-file.nwc": "STR"} to fix a model's
    discipline. Loading or assigning re-ranks the current analysis instantly, without re-extracting."""
    return APP.profile_action(action, path, mapping)


@mcp.tool(annotations=_ro("Federation census with discipline proposals"))
@guarded
def nw_model() -> dict[str, Any]:
    """Models in the open federation: element counts, top categories, and the discipline each one looks like
    (by file name and by categories, flagging disagreement). Use it before analysis to catch misclassified models."""
    return APP.model()


@mcp.tool(annotations=_ro("Query and count elements"))
@guarded
def nw_query(where: list[dict[str, Any]] | None = None, group_by: str = "", limit: int = 20) -> dict[str, Any]:
    """Count and sample elements in the open model. where=[{"field":"category","op":"eq|contains|in","value":...}]
    (fields: category, model, level, family, name, system, or any property name). group_by aggregates by a field.
    Read-only and cheap: use it to answer 'how many ducts per level' without any clash data."""
    return APP.query(where, group_by, limit)


@mcp.tool(annotations=_mutating("Run clash tests"))
@guarded
def nw_run(tests: list[str] | None = None, max_wait_s: float = 25) -> dict[str, Any]:
    """Run clash tests in Navisworks (all, or the named ones). Replaces their stored results. Returns the job state;
    poll with nw_job if it is still running. Needed only when tests were never run or models changed."""
    return APP.run(tests, max_wait_s)


@mcp.tool(annotations=_ro("Analyze clashes into ranked issues"))
@guarded
def nw_analyze(path: str = "", tests: list[str] | None = None, top: int = 10, max_wait_s: float = 25,
               job_id: str = "", lang: str = "") -> dict[str, Any]:
    """Core tool. Extracts the clash results (live from Navisworks, or from path= a .xml/.csv/.json export), drops
    noise, collapses clashes into issues, scores each with reasons, finds root causes, and reports coverage. Returns a
    summary only. If extraction outlasts max_wait_s you get a job_id: call again with job_id= to collect."""
    return APP.analyze(path, tests, top, max_wait_s, job_id, lang or None)


@mcp.tool(annotations=_ro("List and filter issues"))
@guarded
def nw_issues(priority: str = "", discipline: str = "", responsible: str = "", level: str = "", cause: str = "",
              sort: str = "rank", limit: int = 20, offset: int = 0, lang: str = "") -> dict[str, Any]:
    """Filter the analysed issues. priority: critical|high|medium|low. discipline matches either side; responsible is the
    discipline that has to move. cause is a cause id from nw_analyze. sort: rank|score|clashes|level."""
    return APP.issues(priority, discipline, level, cause, responsible, sort, limit, offset, lang or None)


@mcp.tool(annotations=_ro("One issue in detail"))
@guarded
def nw_issue(id: str, lang: str = "") -> dict[str, Any]:
    """Everything about one issue: score components, reasons, the two elements, root causes, clash ids."""
    return APP.issue(id, lang or None)


@mcp.tool(annotations=_add("Produce reports and exports"))
@guarded
def nw_report(kind: str = "summary", path: str = "", overwrite: bool = False, limit: int = 25, lang: str = "") -> dict[str, Any]:
    """kind: summary | matrix | hotspots | plan (work packages) return inline; markdown returns inline unless path is
    given; csv | bcf (BCF 2.1) | json (re-readable export) write a file. Files go only under the allowed output
    folders (NAVIS_MCP_OUTPUT_ROOTS); a bare name lands in the default folder; overwrite defaults to false."""
    return APP.report(kind, path, overwrite, limit, lang or None)


@mcp.tool(annotations=_mutating("Write groups and statuses back to Navisworks"))
@guarded
def nw_apply(ops: list[dict[str, Any]] | None = None, plan_id: str = "", dry_run: bool = True) -> dict[str, Any]:
    """Two steps. (1) ops=[{"op":"group","issues":"top:20"}, {"op":"status","issues":{"priority":"low"},"status":"reviewed"}]
    previews and returns plan_id; nothing changes. issues is a list of ids, 'top:N', or a filter
    {priority, discipline, level, limit}. (2) plan_id=... executes it against the same document and reports what was
    verified by re-reading. Refused if the document changed since the analysis."""
    return APP.apply(ops, plan_id, dry_run)


@mcp.tool(annotations=_add("Save and compare coordination deliveries"))
@guarded
def nw_snapshot(action: str = "list", name: str = "", against: str = "") -> dict[str, Any]:
    """action='save' stores the current analysis under name; 'list'; 'compare' diffs the current analysis (or name)
    against a saved one by what issues are made of. Issues that vanish are 'absent', never 'resolved'."""
    return APP.snapshot(action, name, against)


@mcp.tool(annotations=_mutating("Save the open Navisworks document"))
@guarded
def nw_document(action: str = "save", path: str = "", confirm: bool = False, overwrite: bool = False) -> dict[str, Any]:
    """action='save' or 'save_as' (path under the allowed output folders). Without confirm it only previews; confirm=true
    works only right after a preview of the same action, against the same document."""
    return APP.document(action, path, confirm, overwrite)


TERMINAL_NOTE = """\
navis-mcp is an MCP server: it talks JSON over stdin/stdout and is meant to be started by an
MCP client (Claude Desktop, Claude Code, ...), not typed into a terminal. Waiting silently is
what a server does, so this window now exits instead of looking frozen.
navis-mcp es un servidor MCP: lo lanza un cliente (Claude Desktop, Claude Code...), no se usa
a mano en una terminal.

To try it by hand / para probarlo a mano:
  navis-mcp-cli demo              recorrido completo contra un Navisworks simulado
  navis-mcp-cli tools             lista las 14 herramientas
  navis-mcp-cli call nw_status    llama una herramienta
To connect a client / para conectar un cliente: see manual_para_dummies.md
To force the server in a terminal anyway: navis-mcp --serve
"""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--serve" not in args and sys.stdin.isatty():
        print(TERMINAL_NOTE, file=sys.stderr)
        return 0
    mcp.run()
    return 0


if __name__ == "__main__":
    main()
