# VDC Navis Lab: manual for dummies

A guide to install and test **VDC Navis Lab 1.0** from scratch on a Windows computer, with no programming knowledge. Every step says **where** to type and **what you should see**. If something does not match the manual, go to section 10 and section 11 (how to report the problem, which is useful information to improve the program).

Versión en español: [manual_para_dummies.md](manual_para_dummies.md).

## 0. Before you start

- **Time:** about 20 minutes if all goes well. Most of it is waiting for downloads.
- **Internet is needed** during the installation.
- **No administrator rights are needed** to install this program. They may be needed to install Python, .NET and Claude Desktop if they are missing.
- **An honest warning about the Navisworks version.** The add-in (the piece that talks to Navisworks) is **verified only on Navisworks Manage 2026**. For 2023, 2024 and 2025 the installer tries to build it against your Navisworks, but that has **not been tested**: it may work or it may produce errors. Section 3 explains how to find your version and what to expect. Everything that does not depend on the add-in (the demo, analysing exported files, the reports) works the same on any version.

## 1. What it is, in one sentence

A bridge between an AI assistant (Claude) and Navisworks Manage. The AI does not receive thousands of raw clash rows: it receives a list of issues ordered by priority, with the reason for each one, who should move and what is still unchecked. It can also prepare the project (search sets per discipline and Clash Detective tests), group, colour and generate reports. Anything that changes the model takes two steps: first a plan that touches nothing, then the execution, which is verified by rereading the document.

## 2. What must be installed

| Program | What for | How to check | How to install |
|---|---|---|---|
| **Python 3.11 or newer** | Runs the program | PowerShell: `python --version` (must say 3.11 or higher) | https://www.python.org/downloads/ . **Tick "Add python.exe to PATH"** on the first screen of the installer |
| **.NET 8 SDK** | Builds the Navisworks add-in | PowerShell: `dotnet --list-sdks` (one line must start with `8.`) | `winget install Microsoft.DotNet.SDK.8` or https://dotnet.microsoft.com/download |
| **Claude Desktop** | The assistant that uses the program | It is in the Start menu | https://claude.ai/download |
| **Navisworks Manage** | The BIM program | Start menu | (the one you already have) |

To open PowerShell: Start menu, type `PowerShell`, Enter. **After installing Python or .NET, close that window and open a new one**; otherwise it will not recognise the new programs.

If `python --version` opens the Microsoft Store or prints nothing, Python is not installed the way it is needed: install it from python.org with the box ticked.

## 3. Which Navisworks version do I have and what to expect

How to find out, either way:

- Look at the folders in `C:\Program Files\Autodesk`: they are called `Navisworks Manage 2025`, `Navisworks Manage 2023`, etc.
- In Navisworks: File tab, Help, About.

| Version | Status | What to do |
|---|---|---|
| **Manage 2026** | Verified on a real model | Normal installation |
| **Manage 2025** or **2024** | Untested. The installer builds against the DLLs of your version; if Autodesk changed a function the add-in uses, the build **will show errors** | Install anyway (section 5). If it builds and loads, try section 7 and report what worked. If it shows errors, keep `instalacion.log` (section 11): it is what is needed to fix it |
| **Manage 2023** or older | Untested and less likely to work | Same as above. If it fails, it is not your mistake |
| **Simulate** or **Freedom** | Do not work: no Clash Detective API | Manage is required |

**If the computer has two versions** (for example 2023 and 2025), the installer tries both and says which ones were installed. That is normal and harmless: each version uses its own folder.

**Which one to open for the test:** the newest of those that were installed. If one built and the other did not, open the one that built.

**What happens if the add-in does not work on your version:** the rest still works. You can analyse clashes by exporting the report from Clash Detective (Report tab, XML format) and giving the file path to the assistant. Writing to the model is not available, but the analysis, the priority order and the reports are.

## 4. Download the program

1. Open https://github.com/earubioc/vdc-navis-lab/releases/latest in the browser. It is the latest published version.
2. At the bottom of the page, under "Assets", click **Source code (zip)**.
3. Open the downloaded ZIP and copy the folder inside to `C:\VDC`. Create `C:\VDC` if it does not exist. **Rename the folder to `vdc-navis-lab`** (the ZIP names it with the version, for example `vdc-navis-lab-1.0.1`). The result is `C:\VDC\vdc-navis-lab`.

**Why there:** a short path with no spaces, accents or synced folders (OneDrive, Desktop) avoids problems. You may use another path that meets that; in this manual it is called "the program folder".

(If you already use git: `git clone https://github.com/earubioc/vdc-navis-lab.git`.)

## 5. Install, with one command

1. Open the program folder in File Explorer.
2. Click the address bar (where the path is), delete what is there, type `powershell` and press Enter. A blue PowerShell window opens **already in that folder**. (Alternative: open PowerShell and type `cd C:\VDC\vdc-navis-lab`.)
3. **Close Navisworks** if it is open.
4. Paste and press Enter:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
   ```
5. Wait. You will see four blocks (the installer speaks Spanish or English according to the Windows language; the examples below show the English text):

| Block | What you should see |
|---|---|
| `=== 1. Python and package` | `Python 3.12 (py)` (or your version) and, after some downloading, `Successfully installed ... vdc-navis-lab-1.0.0` |
| `=== 2. Offline test (demo)` | Five numbered steps and at the end `Listo.` (or `Done.`) |
| `=== 3. Register in Claude Desktop` | `backup: ...` and `vdc-navis-lab added to ...claude_desktop_config.json` |
| `=== 4. Navisworks add-in` | `Navisworks Manage versions: 2025` (whatever is installed), the build, and `3/3 Done. Installed in: ...\Plugins\VdcNavisLab` |

6. At the end a green box says `DONE. Next:`. That is success.

The script keeps a record of everything in `instalacion.log`, inside the program folder.

**If something shows in red**, do not repeat blindly: read the message (it almost always says what is missing, for example Python or .NET) and check the table in section 10.

### After installing

1. **Quit Claude Desktop completely.** Closing the window is not enough: click the `^` arrow next to the Windows clock, right click the Claude icon, **Quit**. Then open it again.
2. **Open Navisworks Manage** and a model with Clash Detective tests (or without them; the program can also create them).
3. Go to section 7.

## 6. If you prefer to do it by hand (or the script failed at one point)

Every line is typed in PowerShell, in the program folder.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
vdc-navis-lab-cli demo
vdc-navis-lab-cli desktop-config --write
```

- The second line must leave `(.venv)` at the start of the line. If it says script execution is disabled, type once `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y` and repeat.
- **Why `.venv`:** it installs the program in its own folder and does not mix packages with the general Python (other programs, such as `gradio` or `fastapi`, ask for different versions of some libraries).

The add-in (with Navisworks closed), replacing `2025` with your version:

```powershell
powershell -ExecutionPolicy Bypass -File .\addin\build-and-install.ps1 -Version 2025
```

It copies only the four Navisworks DLLs it needs from `C:\Program Files\Autodesk\Navisworks Manage 2025`, builds and installs into `%APPDATA%\Autodesk\Navisworks Manage 2025\Plugins\VdcNavisLab\`. Those DLLs belong to Autodesk: they are not uploaded to GitHub nor shared.

## 7. The first test

### 7.1 Without Navisworks: the demo

```powershell
.\.venv\Scripts\Activate.ps1
vdc-navis-lab-cli demo --lang en
```

**You should see** five numbered steps and `Done.`. It does not touch your data. This already proves the program works. For Spanish drop `--lang en`.

### 7.2 With real Navisworks

With Navisworks open and a model loaded, in PowerShell, in the program folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\addin\check.ps1
```

**You should see** four blocks: Navisworks running (`Roamer`), the installed plugin (`VdcNavisLab.dll`), the add-in log (`addin.log`) with recent lines, and a pipe named `vdc-navis-lab.<number>`. If all four are there, the add-in loaded.

Then, in Claude Desktop, open a new chat and type:

> Check the status of Navisworks.

The first time Claude asks permission to use the tool: accept. **You should see** the name of the open document, how many Clash Detective tests it has and whether the program is in read-only mode.

And for the big test:

> Analyse the issues and give me the top five with their reason.

(On a large model it takes a while: it reads the clashes from Clash Detective.)

## 8. What to ask the assistant

| You want | Type |
|---|---|
| Know whether it is connected | "Check the status of Navisworks." |
| See what matters | "Analyse the clashes and give me the five most serious issues." |
| Understand one issue | "Give me the detail of issue NW-9504F9." |
| Review the model | "Audit the model: are there empty or duplicated models, models far from the rest, or missing disciplines?" |
| Prepare the project | "Prepare the search sets per discipline and the clash tests between them." (it shows a plan first; nothing changes until you confirm) |
| Run the tests | "Run the clash tests." |
| Organise | "Group the issues by level." / "Group by discipline pair and level." |
| See it in the model | "Select the elements of issue NW-9504F9 in Navisworks and colour them." (temporary; the file is not changed) |
| Reports | "Generate the PDF report and the handoff report for coordination." / "Generate CSV and BCF." |
| Without Navisworks | "Analyse the file `C:\...\clash.xml`." |

The 16 internal tools (`nw_status`, `nw_connect`, `nw_document`, `nw_profile`, `nw_snapshot`, `nw_analyze`, `nw_issues`, `nw_issue`, `nw_query`, `nw_model`, `nw_report`, `nw_run`, `nw_apply`, `nw_setup`, `nw_view`, `nw_job`) are chosen by the assistant itself; you do not have to type their names. The detailed list is in [docs/TOOLS.md](docs/TOOLS.md).

## 9. Safety: what is good to know

- The installer leaves the program in **read-only mode** (`VDC_NAVIS_LAB_READ_ONLY=1`): it can read, analyse and colour temporarily, but it **does not create or modify anything in the document**. To allow changes (create sets and tests, group, save): `.\instalar.ps1 -AllowWrites`, or `vdc-navis-lab-cli desktop-config --write --allow-writes`, and restart Claude Desktop.
- Even with writing allowed, every change takes two steps: a plan (which touches nothing) and its execution by `plan_id`, which rechecks the document before doing anything and verifies the result afterwards.
- **Make a copy of the .nwd/.nwf before the first test with writing enabled.** As a precaution, not because any damage was seen.
- Reports are saved only in `%USERPROFILE%\.vdc_navis_lab\exports`.
- The program does not send your models to any server of its own. What Claude reads from Navisworks goes into the conversation with Claude, like any other data you give it.

## 10. If something fails

| Symptom | What to do |
|---|---|
| `python` is not recognised, or opens the Microsoft Store | Install Python from python.org with "Add python.exe to PATH". Close PowerShell and open a new one |
| `Python 3.11 or newer was not found` | Same: you may have an old version (3.9, 3.10) |
| `dotnet` is not recognised | `winget install Microsoft.DotNet.SDK.8`, close PowerShell and open a new one |
| `Navisworks Manage was not found ...` | You installed a version that is not Manage, or it is in another path. The Python side was installed. Type `.\instalar.ps1 -Navisworks 2025` to force the version |
| `Missing in ...refs\2025: Autodesk.Navisworks...` | The Autodesk DLLs are not where expected. Look in `C:\Program Files\Autodesk\Navisworks Manage 2025` and report which `Autodesk.Navisworks.*.dll` files are there |
| Build errors (`error CS...`) | The add-in uses a function your Navisworks version does not have. It is the expected case for 2023/2024/2025: **keep `instalacion.log` and report it** (section 11) |
| `Build failed` because packages cannot be downloaded | No internet, or a proxy blocks NuGet |
| `Navisworks is running` | Close it (the script waits). Also check Task Manager: `Roamer.exe` must disappear |
| `check.ps1` says `NO pipe` | Navisworks did not load the add-in. Look at block 3 (`addin.log`) and block 2 (is the `.dll` there?). If the plugin is there but does not load, it may be the version: section 11 |
| Navisworks asks whether you trust the plugin when opening | Choose to load it. It is the add-in you just installed |
| Claude Desktop does not show the `vdc-navis-lab` tool | Quit it **completely** (`^` arrow, right click, Quit) and open it again. Check Settings, Developer |
| `desktop-config` says the file is not valid JSON | The file `%APPDATA%\Claude\claude_desktop_config.json` has an earlier error and nothing was written. Close Claude Desktop, open it with Notepad, fix the line it indicates and repeat |
| "no Navisworks instance" | Navisworks is closed, has no model, or the add-in did not load |
| Results say "never run" | That test was not run in Navisworks: no clashes does not mean it is clean |
| The analysis looks odd on your own model | The priority weights are calibrated on a single model. Report it with a concrete example |

## 11. How to report a problem (this is what helps most)

Send these three things to whoever gave you the program:

1. **`instalacion.log`**, which is in the program folder. It has everything the installer showed, including errors.
2. **Your Navisworks version** (section 3) and whether the computer has more than one.
3. If it is installed but does not answer, the output of `.\addin\check.ps1` with Navisworks open: select the text with the mouse, press Enter to copy it and paste it into a message. A photo of the screen also works.

You do not need to understand the error. "It failed at step 4 with Navisworks 2025" plus `instalacion.log` is enough.

## 12. Update

If you downloaded the ZIP: download the new ZIP and repeat sections 4 and 5, in another folder or over the same one (with Navisworks closed). If you use git: `git pull origin main` in the program folder and then `.\instalar.ps1`.

## 13. Uninstall

1. Close Navisworks and Claude Desktop.
2. Delete the folder `%APPDATA%\Autodesk\Navisworks Manage <version>\Plugins\VdcNavisLab`.
3. In `%APPDATA%\Claude\claude_desktop_config.json` delete the `"vdc-navis-lab"` entry (`.bak` backup copies are next to it).
4. Delete the program folder.

## Appendix: how it is organised

- `instalar.ps1`: installs everything.
- `addin\`: the Navisworks add-in (`build-and-install.ps1`, `check.ps1`, `probar.ps1`, `todo.ps1`). See [addin/README.md](addin/README.md).
- `src\`: the Python program. `docs\`: technical documentation. `examples\`: example files.
- Apache 2.0 licence. Independent project of VDC Process Lab, not affiliated with Autodesk.
