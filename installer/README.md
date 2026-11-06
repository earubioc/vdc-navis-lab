# Installers / Instaladores

Two packages, built from this repository.

| Package | What it is | Built with | Installed by |
|---|---|---|---|
| `VdcNavisLab-<year>-<version>.msi` | the Navisworks add-in, one per major version (2025, 2026) | `build-msi.sh <year> <version> <dll>` | the IT department (Intune, GPO, SCCM, double click) |
| `vdc-navis-lab-<version>.mcpb` | the MCP server as a Claude Desktop extension, server type `uv` (116 KB; downloads its dependencies the first time) | `build-mcpb.sh` | double click, or Settings > Extensions in Claude Desktop |
| `vdc-navis-lab-<version>-offline-windows.mcpb` | the same server with every dependency inside (13 MB; for computers without internet), server type `python` | `build-mcpb-python.sh --target windows` | the same; needs Python 3.11, 3.12 or 3.13 installed |

## Build

```bash
# the DLL must be compiled against the Navisworks DLLs of that year (addin/build-and-install.ps1 on Windows, or mcs)
installer/build-msi.sh 2025 1.0.1 path/to/VdcNavisLab-2025.dll
installer/build-msi.sh 2026 1.0.1 path/to/VdcNavisLab-2026.dll
installer/build-mcpb.sh                              # uv type
installer/build-mcpb-python.sh --target windows     # offline type (needs network once, to download wheels)
```

Output goes to `dist/`. The MSI build needs `wixl` and `msitools` (`apt install wixl msitools`).

## One add-in, one place

The MSI installs per machine. If the add-in was installed before for one user (`addin/build-and-install.ps1`, `instalar.ps1`, folder `%APPDATA%\Autodesk\Navisworks Manage <year>\Plugins\VdcNavisLab`), delete that copy first; otherwise Navisworks loads the add-in twice.

The offline bundle holds the dependencies for Python 3.11, 3.12 and 3.13 on 64-bit Windows in one folder (the compiled files of each version have different names, so they coexist). It does not include the interpreter: Claude Desktop starts the `python` it finds on the PATH. With the `uv` type and an empty cache, the first start needs internet; with this one it never does.

The `uv` MCPB only holds the server's source. When the extension is enabled, Claude Desktop installs the dependencies with `uv` (needs internet the first time). The server also needs the add-in installed on the same computer to talk to Navisworks; without it, it works on exported clash files.

## Test

* Linux, no Windows: `PYTHONPATH=src python -m pytest tests/test_installer.py` (bundle contents, MSI payload) and `uv run --no-project --with mcp python installer/handshake.py <unzipped mcpb> 16` (the server starts as the manifest says and answers).
* Clean Windows: copy `installer/` and the packages to Windows Sandbox (`probar-instalacion.wsb`) or a fresh virtual machine and run `probar-instalacion.ps1 -Msi ... -Year 2025 [-MsiNueva ...] [-Mcpb ...]`. It installs, checks the file and its hash, reinstalls, upgrades, uninstalls, and starts the server from the unzipped extension.
