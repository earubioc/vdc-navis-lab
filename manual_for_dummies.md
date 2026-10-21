# navis-mcp: manual for dummies

A short, jargon-free guide to installing and trying navis-mcp. Current state: **v0.1**. It works with exported files and with a simulated Navisworks. The connection to a real Navisworks is not ready yet (the add-in is uncompiled), so today it cannot read or change your open model.

## 1. What it is, in one sentence

A bridge between an AI assistant (Claude, for example) and Navisworks clash detection results. The AI does not receive thousands of raw rows: it gets a list of issues ranked by priority, with the reason for each, who has to move, and what has not been checked.

## 2. Installation (once)

You need Python 3.11 or newer. Open PowerShell in the project folder and create a private environment:

```powershell
cd D:\IA_WORK\MCP_NAVIS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**Important:** always use the `.venv` environment. Without it, pip puts the dependencies into your general Python and can break other programs. This happened once: `mcp` brings newer versions of `starlette` and `websockets`, while other packages on the machine (for example `gradio` or `fastapi`) ask for older ones. The "dependency conflicts" warning says exactly that. It does not affect navis-mcp, only those other applications. If one of them broke, run this outside the `.venv` environment:

```powershell
pip install "starlette<0.49" "websockets<12"
```

That should bring `fastapi` and `gradio` back to normal (not checked on your machine). From then on, use navis-mcp only inside `.venv`.

Every time you open a new terminal, activate the environment again: `.\.venv\Scripts\Activate.ps1`.

## 3. The easiest test: the guided walk-through

```powershell
navis-mcp-cli demo
```

In a few seconds it goes through the whole flow against a fake Navisworks: status, analysis, change plan, execution and verification. It needs nothing else and does not touch your data. For Spanish: `navis-mcp-cli demo --lang es`.

Other useful commands:

| Command | What it does |
|---|---|
| `navis-mcp-cli tools` | Lists the 14 tools |
| `navis-mcp-cli call nw_status` | Calls a single tool |
| `navis-mcp-cli sample examples\tower.json` | Creates a sample file (a 5-level tower) |
| `navis-mcp-cli analyze examples\tower.json --lang en` | Analyzes a file and prints the report |

## 4. Why `navis-mcp` and `navis-mcp-cli simulate` look frozen

They are not. They are programs that **wait**:

- `navis-mcp` is the server. It is not operated by hand: an assistant (Claude Desktop or Claude Code) starts it and talks to it behind the scenes. If you open it in a terminal, it now prints a note and exits.
- `navis-mcp-cli simulate` is the fake Navisworks. It waits for connections until you press `Ctrl+C`. You only need it if you want an assistant to use it.

## 5. Connecting an assistant

### Claude Desktop

The safe way, with the `.venv` environment active:

```powershell
navis-mcp-cli desktop-config --write
```

It backs up the file, adds `navis-mcp` without touching your other servers, and refuses to write if the file is already broken. Then quit Claude Desktop completely (also from the system tray) and open it again. Without `--write` it only shows the entry that would be added.

By hand: open `%APPDATA%\Claude\claude_desktop_config.json`. If the file already has `"mcpServers"`, **do not paste the whole block**: add only the `"navis-mcp": {...}` entry inside that object, with a comma after the previous entry. Pasting a new block after the final closing brace `}` makes the file invalid and Claude Desktop will not start ("Unexpected non-whitespace character after JSON"). The full block is for an empty file only (adjust the path if your folder differs):

```json
{
  "mcpServers": {
    "navis-mcp": {
      "command": "D:\\IA_WORK\\MCP_NAVIS\\.venv\\Scripts\\navis-mcp.exe",
      "env": { "NAVIS_MCP_READ_ONLY": "1" }
    }
  }
}
```

Quit Claude Desktop completely and open it again. The `nw_*` tools will appear.

### Claude Code

```powershell
claude mcp add navis-mcp -- D:\IA_WORK\MCP_NAVIS\.venv\Scripts\navis-mcp.exe
```

### With the fake Navisworks

Keep a terminal open with `navis-mcp-cli simulate` and connect the assistant as above. It finds the simulator by itself.

## 6. What to ask the assistant

- "Check the Navisworks status."
- "Analyze the file `D:\...\clash.xml` and give me the five worst issues."
- "Which disciplines have no results? Which tests never ran?"
- "Show me the detail of issue NW-9504F9."
- "Produce a CSV report and a BCF one."
- "Group the 20 worst issues." (it first shows a plan; nothing changes until you confirm)

To analyze your own clashes without a live Navisworks: in Navisworks, Clash Detective, Report tab, XML format, and give the assistant the file path. CSV files and navis-mcp JSON files work too. Real exports vary between versions; if one fails, keep it and report it, that is useful information to improve the reader.

## 7. Safety: what to know

- `NAVIS_MCP_READ_ONLY=1` blocks every write to Navisworks. Leave it on while testing.
- Reports are saved only under `%USERPROFILE%\.navis_mcp\exports`, unless you set `NAVIS_MCP_OUTPUT_ROOTS`.
- Changing anything in Navisworks is always two steps: a plan (which modifies nothing) and its execution by `plan_id`.

## 8. When something fails

| Symptom | What to do |
|---|---|
| `navis-mcp` is not recognized as a command | Activate the environment: `.\.venv\Scripts\Activate.ps1` |
| The assistant does not see the tools | Check the `.exe` path in the configuration and fully restart the assistant |
| "no Navisworks instance" | Expected without Navisworks: use a file (`path=`) or start `simulate` |
| An XML is not read | Try CSV, or report the case |
| Results say "never run" | That test was not run in Navisworks: no clashes does not mean clean |

## 9. What it does not do yet

Read or modify a real open Navisworks, create viewpoints, color the model or produce PDF. See [docs/ROADMAP.md](docs/ROADMAP.md).
