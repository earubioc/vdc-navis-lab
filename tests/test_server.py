"""End-to-end: a real MCP client over stdio against the server process, talking to the simulator."""
import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SRC = str(Path(__file__).resolve().parents[1] / "src")
EXPECTED = {"nw_status", "nw_connect", "nw_job", "nw_profile", "nw_model", "nw_query", "nw_run",
            "nw_analyze", "nw_issues", "nw_issue", "nw_report", "nw_apply", "nw_snapshot", "nw_document", "nw_view"}


def _text(result):
    return result.content[0].text


def _err(result):
    """The SDK prefixes tool errors with 'Error executing tool x: '; the payload after it is our JSON."""
    assert result.is_error
    text = _text(result)
    return json.loads(text[text.index("{"):])


async def _session(env, body):
    params = StdioServerParameters(command=sys.executable, args=["-m", "vdc_navis_lab.server"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await body(s)


def _env(sim, tmp_path, **extra):
    env = {**os.environ, "PYTHONPATH": SRC, "VDC_NAVIS_LAB_ENDPOINT": sim.endpoint,
           "VDC_NAVIS_LAB_HOME": str(tmp_path / "home")}
    env.update(extra)
    return env


def test_tool_list_annotations_and_full_write_flow(sim, tmp_path):
    async def body(s):
        tools = (await s.list_tools()).tools
        assert {t.name for t in tools} == EXPECTED
        by = {t.name: t for t in tools}
        assert by["nw_issues"].annotations.read_only_hint is True
        assert by["nw_run"].annotations.destructive_hint is True
        assert all(t.description and len(t.description) > 40 for t in tools)

        st = json.loads(_text(await s.call_tool("nw_status", {})))
        assert st["bridge"]["connected"] is True

        a = json.loads(_text(await s.call_tool("nw_analyze", {"top": 3})))
        assert a["issues"] > 0 and len(a["top"]) == 3

        hv = json.loads(_text(await s.call_tool("nw_issues", {"responsible": "HVAC", "limit": 3})))
        assert hv["total"] > 0 and all(i["responsible"] == "HVAC" for i in hv["items"])

        plan = json.loads(_text(await s.call_tool("nw_apply", {"ops": [{"op": "group", "issues": "top:3"}]})))
        assert plan["dry_run"] is True
        done = json.loads(_text(await s.call_tool("nw_apply", {"plan_id": plan["plan_id"], "dry_run": False})))
        assert done["state"] == "completed" and done["verified"]["groups"] == 3

        bad = await s.call_tool("nw_issue", {"id": "NW-NOPE"})
        assert _err(bad)["error"] == "not_found"

    anyio.run(_session, _env(sim, tmp_path), body)


def test_read_only_flag_reaches_the_process(sim, tmp_path):
    async def body(s):
        await s.call_tool("nw_analyze", {})
        plan = json.loads(_text(await s.call_tool("nw_apply", {"ops": [{"op": "group", "issues": "top:1"}]})))
        res = await s.call_tool("nw_apply", {"plan_id": plan["plan_id"], "dry_run": False})
        assert _err(res)["error"] == "read_only"

    anyio.run(_session, _env(sim, tmp_path, VDC_NAVIS_LAB_READ_ONLY="1"), body)


def test_offline_mode_without_navisworks(tmp_path):
    from vdc_navis_lab.sample.generator import build
    f = tmp_path / "export.json"
    f.write_text(json.dumps(build()[0].to_dict()), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": SRC, "VDC_NAVIS_LAB_HOME": str(tmp_path / "home"),
           "VDC_NAVIS_LAB_ENDPOINT": ""}

    async def body(s):
        st = json.loads(_text(await s.call_tool("nw_status", {})))
        assert st["bridge"]["connected"] is False
        a = json.loads(_text(await s.call_tool("nw_analyze", {"path": str(f), "top": 2})))
        assert a["issues"] > 0
        live = await s.call_tool("nw_run", {})
        assert _err(live)["error"] == "no_instance"

    anyio.run(_session, env, body)
