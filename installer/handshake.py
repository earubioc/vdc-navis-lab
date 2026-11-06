"""Handshake with an MCP server over stdio, the way a client does: initialize, list tools, call nw_status.

  uv run --with mcp python installer/handshake.py <dir of the unzipped .mcpb> [expected tools]

It launches the server exactly as the manifest says (uv run --directory <dir> run_server.py), with a private data folder so
it does not touch the real one. Prints PASS/FAIL lines and nothing about any model.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(folder: str, expected: int) -> int:
    manifest = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    cfg = manifest["server"]["mcp_config"]
    data = tempfile.mkdtemp(prefix="vdc-navis-lab-handshake-")
    env = dict(os.environ)  # a real host also passes the user's environment (proxy, certificates, uv cache)
    env.update({k: v.replace("${user_config.read_only}", "true") for k, v in cfg.get("env", {}).items()})
    env["VDC_NAVIS_LAB_HOME"] = data
    args = [a.replace("${__dirname}", str(Path(folder).resolve())) for a in cfg["args"]]
    ok = True

    def check(name: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name:<28} {detail}")

    params = StdioServerParameters(command=cfg["command"], args=args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            init = await asyncio.wait_for(s.initialize(), 300)
            check("initialize", True, f"{init.server_info.name} {init.server_info.version}")
            tools = (await s.list_tools()).tools
            check("tools/list", len(tools) == expected, f"{len(tools)} tools (expected {expected})")
            res = await s.call_tool("nw_status", {})
            text = "".join(getattr(c, "text", "") for c in res.content)
            body = json.loads(text)
            check("nw_status without Navisworks", not res.is_error and isinstance(body, dict), f"keys: {', '.join(sorted(body))[:80]}")
            # the user_config switch must reach the server: read_only=true means a clash run is refused before anything else
            w = await s.call_tool("nw_run", {})
            wtext = "".join(getattr(c, "text", "") for c in w.content)
            check("read_only reaches the server", w.is_error and "read_only" in wtext, "nw_run was refused" if w.is_error else "nw_run was NOT refused")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 16)))
