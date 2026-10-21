# Navisworks add-in

**Status: compiles against the Navisworks Manage 2026 API (net48); never yet run inside Navisworks.** Calls marked `VERIFY` in `Handlers.cs` type-check, but their runtime behaviour is still unconfirmed.

## What it does

An `EventWatcherPlugin` loads with Navisworks, captures the UI thread, and opens the named pipe `vdc-navis-lab.<pid>`, accessible to the current user only. Requests are handled on a worker thread and any Navisworks API call is marshalled to the UI thread, because the API is single-threaded.

Implemented: `hello`, `doc.info`, `clash.tests`, `clash.export`, `job.status`, `job.result`, `job.cancel`, `job.list`. Everything else answers `unsupported` and `hello.methods` says so. Wire format: [../docs/PROTOCOL.md](../docs/PROTOCOL.md).

Known limits of 0.1: extraction runs on the UI thread in one block (Navisworks is unresponsive meanwhile); writes (`clash.apply`, `doc.save`) are not implemented.

## Build and install (one command)

Requires the .NET SDK and the Navisworks assemblies copied to `addin\refs\2026\` (the folder is git-ignored; never commit them). Close Navisworks, then in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File D:\IA_WORK\MCP_NAVIS\addin\build-and-install.ps1
```

It builds and copies `VdcNavisLab.dll` to `%APPDATA%\Autodesk\Navisworks Manage 2026\Plugins\VdcNavisLab\` (current user, no administrator rights), the same layout other third-party plugins use. The folder name must equal the DLL name. Then open Navisworks and run `addin\check.ps1` to see whether it loaded.

## First test

1. Open a federated model with clash tests.
2. In Python: `vdc-navis-lab` (or an MCP client) and call `nw_status`. The instance should be listed.
3. `nw_analyze` should return a summary. Compare the clash count with Clash Detective.
