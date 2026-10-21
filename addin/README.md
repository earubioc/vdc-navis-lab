# Navisworks add-in

**Status: reads and writes verified on Navisworks Manage 2026 (net48).** Connection, test listing and clash extraction work on a real federated NWD built from Revit exports. `clash.apply` (status, grouping) and `doc.save` (save_as) ran against a real open document and were verified by re-reading it: results come back read-only from the API, so both go through `DocumentClashTests` (`TestsEditResultStatus`, `TestsInsertCopy`, `TestsMove`) instead of setting properties directly. Not yet verified: Navisworks 2025 (its folder on the test machine had no API DLLs).

## What it does

An `EventWatcherPlugin` loads with Navisworks, captures the UI thread, and opens the named pipe `vdc-navis-lab.<pid>`, accessible to the current user only. Requests are handled on a worker thread and any Navisworks API call is marshalled to the UI thread, because the API is single-threaded.

Implemented: `hello`, `doc.info`, `clash.tests`, `clash.export`, `clash.apply`, `doc.save`, `job.status`, `job.result`, `job.cancel`, `job.list`. Everything else answers `unsupported` and `hello.methods` says so. Wire format: [../docs/PROTOCOL.md](../docs/PROTOCOL.md).

Extraction runs one test per UI-thread slice, so Navisworks processes its own message queue between tests instead of freezing for the whole export; not yet confirmed against a real model (needs Navisworks open). Known limits of 0.1: `model.census`, `elements.query` and `clash.run` are not implemented.

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
