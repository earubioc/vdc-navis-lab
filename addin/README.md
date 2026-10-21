# Navisworks add-in (draft)

**Status: draft. Never compiled, never run inside Navisworks.** It was written against the public API from documentation and memory; every call marked `VERIFY` in `Handlers.cs` has to be checked against the installed assemblies. Do not rely on it until it has been built and tested.

## What it does

An `EventWatcherPlugin` loads with Navisworks, captures the UI thread, and opens the named pipe `vdc-navis-lab.<pid>`, accessible to the current user only. Requests are handled on a worker thread and any Navisworks API call is marshalled to the UI thread, because the API is single-threaded.

Implemented: `hello`, `doc.info`, `clash.tests`, `clash.export`, `job.status`, `job.result`, `job.cancel`, `job.list`. Everything else answers `unsupported` and `hello.methods` says so. Wire format: [../docs/PROTOCOL.md](../docs/PROTOCOL.md).

Known limits of 0.1: extraction runs on the UI thread in one block (Navisworks is unresponsive meanwhile); writes (`clash.apply`, `doc.save`) are not implemented.

## Build

Requires the .NET SDK and a Navisworks Manage installation (the project references its assemblies; the target framework must match your version, `net48` for current releases).

```powershell
dotnet build addin/VdcNavisLab.Addin -c Release -p:NavisworksDir="C:\Program Files\Autodesk\Navisworks Manage 2025"
```

## Install

Copy `addin/bundle/VdcNavisLab.bundle` to `%ProgramData%\Autodesk\ApplicationPlugins\`, put `VdcNavisLab.Addin.dll` in its `Contents` folder, and restart Navisworks. Then, from a terminal, `vdc-navis-lab-cli` or an MCP client can find the instance through its pipe.

## First test

1. Open a federated model with clash tests.
2. In Python: `vdc-navis-lab` (or an MCP client) and call `nw_status`. The instance should be listed.
3. `nw_analyze` should return a summary. Compare the clash count with Clash Detective.
