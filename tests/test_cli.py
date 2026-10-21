import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")


def run(*args, stdin=None):
    env = {**os.environ, "PYTHONPATH": SRC}
    return subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, timeout=60, env=env, stdin=stdin)


def test_demo_runs_end_to_end_in_both_languages():
    for lang, marker in (("es", "Listo."), ("en", "Done.")):
        r = run("navis_mcp.cli", "demo", "--lang", lang)
        assert r.returncode == 0, r.stderr
        assert marker in r.stdout and "completed" in r.stdout and "'groups': 3" in r.stdout


def test_demo_never_touches_the_users_data_folder(tmp_path):
    env = {**os.environ, "PYTHONPATH": SRC, "NAVIS_MCP_HOME": str(tmp_path / "mine")}
    subprocess.run([sys.executable, "-m", "navis_mcp.cli", "demo"], env=env, check=True, capture_output=True, timeout=60)
    assert not (tmp_path / "mine" / "snapshots").exists()


def test_tools_lists_the_fourteen():
    r = run("navis_mcp.cli", "tools")
    names = [line.split()[0] for line in r.stdout.splitlines()]
    assert r.returncode == 0 and len(names) == 14 and all(n.startswith("nw_") for n in names)


def test_call_one_tool_and_fail_cleanly():
    ok = run("navis_mcp.cli", "call", "nw_profile", '{"action":"show"}')
    assert ok.returncode == 0 and json.loads(ok.stdout)["name"] == "default"
    bad = run("navis_mcp.cli", "call", "nw_nope")
    assert bad.returncode == 1 and "Unknown tool" in bad.stderr
    badjson = run("navis_mcp.cli", "call", "nw_status", "{oops")
    assert badjson.returncode == 2


@pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")
def test_server_in_a_terminal_explains_itself_instead_of_hanging():
    import pty
    master, slave = pty.openpty()
    try:
        env = {**os.environ, "PYTHONPATH": SRC}
        p = subprocess.run([sys.executable, "-m", "navis_mcp.server"], stdin=slave, capture_output=True, text=True,
                           timeout=30, env=env)
    finally:
        os.close(master)
        os.close(slave)
    assert p.returncode == 0 and p.stdout == "" and "navis-mcp-cli demo" in p.stderr


def test_desktop_config_merges_without_touching_other_servers(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x", "args": ["1"]}}}), encoding="utf-8")
    r = run("navis_mcp.cli", "desktop-config", "--write", "--config", str(cfg))
    assert r.returncode == 0, r.stderr
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark" and data["mcpServers"]["other"] == {"command": "x", "args": ["1"]}
    assert data["mcpServers"]["navis-mcp"]["env"]["NAVIS_MCP_READ_ONLY"] == "1"
    assert list(tmp_path.glob("claude_desktop_config.json.bak-*")), "a backup must be made"
    again = run("navis_mcp.cli", "desktop-config", "--write", "--config", str(cfg), "--allow-writes")
    assert again.returncode == 0 and json.loads(cfg.read_text())["mcpServers"]["navis-mcp"]["env"]["NAVIS_MCP_READ_ONLY"] == "0"


def test_desktop_config_refuses_a_broken_file_and_writes_nothing(tmp_path):
    cfg = tmp_path / "c.json"
    broken = '{"mcpServers": {}}\n"navis-mcp": {"command": "x"}\n'
    cfg.write_text(broken, encoding="utf-8")
    r = run("navis_mcp.cli", "desktop-config", "--write", "--config", str(cfg))
    assert r.returncode == 1 and "not valid JSON" in r.stderr and "line 2" in r.stderr
    assert cfg.read_text(encoding="utf-8") == broken and not list(tmp_path.glob("*.bak-*"))


def test_desktop_config_creates_the_file_and_prints_a_snippet(tmp_path):
    cfg = tmp_path / "new" / "c.json"
    assert run("navis_mcp.cli", "desktop-config", "--write", "--config", str(cfg)).returncode == 0
    assert "navis-mcp" in json.loads(cfg.read_text())["mcpServers"]
    shown = run("navis_mcp.cli", "desktop-config", "--config", str(cfg))
    assert shown.returncode == 0 and '"navis-mcp": {' in shown.stdout and "INSIDE" in shown.stdout
