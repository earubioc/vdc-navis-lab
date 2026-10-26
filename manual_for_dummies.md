# vdc-navis-lab: manual for dummies

A step-by-step guide to installing and trying vdc-navis-lab. Every step says **where** to type it (which terminal) and **what you should see**.

Current state: **v0.2**. It works with exported files, with a simulated Navisworks and with a real Navisworks Manage 2026: it reads Clash Detective tests, analyses them, and writes back (grouping, status, save) verified by re-reading the document (see section 10).

## 0. How to open a terminal ready for work

Repeat this **every time you open a new terminal**. Each terminal is independent: one with the environment active shares nothing with another.

1. Start menu, type `PowerShell`, Enter.
2. Type and press Enter:
   ```powershell
   cd D:\IA_WORK\MCP_NAVIS
   ```
3. Activate the environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   **You should see** the line start with `(.venv)`. If it does not, the `vdc-navis-lab...` commands will not work or will use the general Python.

If step 3 says script execution is disabled, type `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, answer `Y`, and repeat step 3.

## 1. What it is, in one sentence

A bridge between an AI assistant (Claude, for example) and Navisworks clash detection results. The AI does not receive thousands of raw rows: it gets a list of issues ranked by priority, with the reason for each, who has to move, and what has not been checked.

## 2. Installation (once)

You need Python 3.11 or newer. With a terminal open in the project folder (steps 1 and 2 of section 0, no environment yet):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

**You should see** `(.venv)` at the start of the line and, at the end, `Successfully installed ... vdc-navis-lab-0.3.1`.

**Why always `.venv`:** without it, pip puts the dependencies into your general Python and can break other programs. This happened once: `mcp` brings newer versions of `starlette` and `websockets`, while other packages on the machine (for example `gradio` or `fastapi`) ask for older ones. The "dependency conflicts" warning says exactly that. It does not affect vdc-navis-lab, only those other applications. If one of them broke, open a terminal **without** an active environment (no `(.venv)`) and run:

```powershell
pip install "starlette<0.49" "websockets<12"
```

That should bring `fastapi` and `gradio` back to normal (not checked on your machine).

## 3. Updating to the latest version

### 3.1 If you come from the version called `navis-mcp` (once)

The product is now called `vdc-navis-lab`. The commands changed: `navis-mcp` became `vdc-navis-lab` and `navis-mcp-cli` became `vdc-navis-lab-cli`. Do it in this order, in **a prepared terminal** (section 0, with `(.venv)`):

1. Quit Claude Desktop completely (`^` arrow next to the clock, right-click the Claude icon, Quit) and stop any terminal running `simulate` with `Ctrl+C`.
2. Uninstall the old package:
   ```powershell
   pip uninstall -y navis-mcp
   ```
3. Pull the new code:
   ```powershell
   git pull origin main
   ```
   If it says local changes or untracked files would be overwritten, type `git fetch origin` and then `git reset --hard origin/main`. It is safe: your copy has no edits of its own and it does not touch your ignored files (`CLAUDE.md`, `contexto`, `historial.md`, `.venv`).
4. Install under the new name:
   ```powershell
   pip install -e ".[dev]"
   ```
   **You should see** `Successfully installed ... vdc-navis-lab-0.3.1`.
5. Replace the old Claude Desktop entry with the new one:
   ```powershell
   vdc-navis-lab-cli desktop-config --write
   ```
   **You should see** `removed the old 'navis-mcp' entry` and `vdc-navis-lab added to ...`.
6. Open Claude Desktop. The connector list should show **vdc-navis-lab** (and no `navis-mcp`).
7. Try `vdc-navis-lab-cli demo`.

### 3.2 Normal updates

When an improvement is published, in a prepared terminal (section 0):

```powershell
git pull origin main
git log --oneline -1
```

The second line shows the commit you are on. No reinstall is needed: the environment points straight at the folder. Type `git pull origin main` in full, because a bare `git pull` does not know where to pull from.

## 4. The easiest test: the guided walk-through

In a prepared terminal (section 0):

```powershell
vdc-navis-lab-cli demo
```

In a few seconds it goes through the whole flow against a fake Navisworks: status, analysis, change plan, execution and verification. **You should see** five numbered steps and, at the end, "Done.". It needs nothing else and does not touch your data. For Spanish: `vdc-navis-lab-cli demo --lang es`.

**This already proves everything works.** Connecting Claude Desktop (section 5) is the next step and is optional.

Other commands, in the same terminal:

| Command | What it does |
|---|---|
| `vdc-navis-lab-cli tools` | Lists the 14 tools |
| `vdc-navis-lab-cli call nw_status` | Calls a single tool |
| `vdc-navis-lab-cli sample examples\tower.json` | Creates a sample file (a 5-level tower) |
| `vdc-navis-lab-cli analyze examples\tower.json --lang en` | Analyzes a file and prints the report |

## 5. Connecting Claude Desktop, step by step

**What you run and what you do not.** You only type `desktop-config` (once) and `simulate` (each time you want to try the fake Navisworks). **Never type `vdc-navis-lab`** in a terminal: it is the server and Claude Desktop starts it by itself. If you type it by mistake it prints a note and exits; no harm done.

### 5.1 Register vdc-navis-lab in Claude Desktop (once)

1. Open a prepared terminal (section 0).
2. Type:
   ```powershell
   vdc-navis-lab-cli desktop-config --write
   ```
   **You should see** `backup: ...` and `vdc-navis-lab added to ...claude_desktop_config.json`. The command saves a backup copy of the file and does not touch your other servers.
3. If it says `is not valid JSON (line N ...)` instead, the configuration file has a previous error and **nothing was written**. Fix it: close Claude Desktop, type `notepad "$env:APPDATA\Claude\claude_desktop_config.json"`, go to the indicated line with `Ctrl+G`, fix or delete the extra text, save, and repeat step 2.
4. Close Claude Desktop **completely**: click the `^` arrow next to the Windows clock, right-click the Claude icon, Quit. Closing only the window is not enough.
5. Open Claude Desktop again.

### 5.2 Using it with the fake Navisworks (every time)

1. Open a prepared terminal (section 0) and type:
   ```powershell
   vdc-navis-lab-cli simulate
   ```
   **You should see** `Navisworks simulator listening on tcp://127.0.0.1:...` and nothing else. That is normal: the program is waiting for Claude to ask, it is not stuck. **Leave that terminal open**, typing nothing else in it.
2. In Claude Desktop open a new chat. Ask: "Check the Navisworks status and analyze the worst issues".
3. The first time Claude will ask permission to use the tool: accept. **You should see** 35 issues, one critical.
4. When done, go back to the simulator terminal and press `Ctrl+C`.

### Registering by hand (only if you cannot use the command)

Open `%APPDATA%\Claude\claude_desktop_config.json`. If it already has `"mcpServers"`, **do not paste the whole block**: add only the `"vdc-navis-lab": {...}` entry inside that object, with a comma after the previous entry. Pasting a new block after the final closing brace `}` makes the file invalid and Claude Desktop will not start ("Unexpected non-whitespace character after JSON"). The full block, for an empty file only:

```json
{
  "mcpServers": {
    "vdc-navis-lab": {
      "command": "D:\\IA_WORK\\MCP_NAVIS\\.venv\\Scripts\\vdc-navis-lab.exe",
      "env": { "VDC_NAVIS_LAB_READ_ONLY": "1" }
    }
  }
}
```

### Claude Code

In a prepared terminal (section 0):

```powershell
claude mcp add vdc-navis-lab -- D:\IA_WORK\MCP_NAVIS\.venv\Scripts\vdc-navis-lab.exe
```

## 6. What to ask the assistant

- "Check the Navisworks status."
- "Analyze the file `D:\...\clash.xml` and give me the five worst issues."
- "Which disciplines have no results? Which tests never ran?"
- "Show me the detail of issue NW-9504F9."
- "Produce a CSV report and a BCF one."
- "Group the 20 worst issues." (it first shows a plan; nothing changes until you confirm)

To analyze your own clashes without a live Navisworks: in Navisworks, Clash Detective, Report tab, XML format, and give the assistant the file path. CSV files and vdc-navis-lab JSON files work too. Real exports vary between versions; if one fails, keep it and report it, that is useful information to improve the reader.

## 7. Safety: what to know

- `VDC_NAVIS_LAB_READ_ONLY=1` blocks every write to Navisworks. `desktop-config` leaves it on; to allow writes, run the command again with `--allow-writes`.
- Reports are saved only under `%USERPROFILE%\.vdc_navis_lab\exports`, unless you set `VDC_NAVIS_LAB_OUTPUT_ROOTS`.
- Changing anything in Navisworks is always two steps: a plan (which modifies nothing) and its execution by `plan_id`.

## 8. When something fails

| Symptom | What to do |
|---|---|
| `vdc-navis-lab-cli` is not recognized as a command | The terminal has no environment: repeat section 0 |
| `invalid choice: '...'` when typing a manual command | Your copy is outdated: section 3 |
| `desktop-config` says the file is not valid JSON | Step 3 of section 5.1 |
| Claude Desktop does not show the tools | Quit it completely (step 4 of 5.1) and open it again |
| "no Navisworks instance" | Expected without Navisworks: use a file, or keep `simulate` open in another terminal |
| An XML is not read | Try CSV, or report the case |
| Results say "never run" | That test was not run in Navisworks: no clashes does not mean clean |

## 9. What it does not do yet

Running Clash Detective tests, a census of the federated model, creating viewpoints, colouring the model or producing a PDF. See [docs/ROADMAP.md](docs/ROADMAP.md).

## 10. Connecting to a real Navisworks Manage 2026

Done once per computer and Navisworks version. It needs the .NET 8 SDK (`dotnet --list-sdks` must list a version 8) and the environment from section 0.

**Step 1. Copy the Navisworks DLLs used for compiling.** In PowerShell, from any folder (adjust the project path if yours differs):

```powershell
$dst = "D:\IA_WORK\MCP_NAVIS\addin\refs\2026"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "C:\Program Files\Autodesk\Navisworks Manage 2026\Autodesk.Navisworks.*.dll" $dst
```

Listing that folder must show `Autodesk.Navisworks.Api.dll` and `Autodesk.Navisworks.Clash.dll`. These DLLs belong to Autodesk: they are not pushed to GitHub (the folder is in `.gitignore`).

**Step 2. Build, install and test with one command:**

```powershell
powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\todo.ps1
```

The script waits for you to close Navisworks, builds, installs the add-in to `%APPDATA%\Autodesk\Navisworks Manage 2026\Plugins\VdcNavisLab\`, asks you to open Navisworks and a model, and runs the checks. At the end it saves a real sample of your data and the analysis under `insumos\`.

**What you should see:** `Compilación correcta` (build succeeded), `Pipe encontrado`, `Modelo abierto. Probando...`, the status with your Clash Detective tests, and an analysis with ranked issues.

**If something fails**, run this with Navisworks open: `powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\check.ps1`. It shows whether Navisworks is running, whether the add-in is installed, the add-in log (`%LOCALAPPDATA%\vdc-navis-lab\addin.log`) and whether the pipe exists.

After this, the Claude Desktop connector (section 5) reads the open Navisworks with nothing else to change. Every time you update the project (section 3), run `todo.ps1` again to reinstall the add-in.
