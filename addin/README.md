# Navisworks add-in

**Status: reads and writes verified on Navisworks Manage 2026 (net48).** Connection, test listing and clash extraction work on a real federated NWD built from Revit exports. `clash.apply` (status, grouping) and `doc.save` (save_as) ran against a real open document and were verified by re-reading it: results come back read-only from the API, so both go through `DocumentClashTests` (`TestsEditResultStatus`, `TestsInsertCopy`, `TestsMove`) instead of setting properties directly. Not yet verified: Navisworks 2025 (its folder on the test machine had no API DLLs).

## What it does

An `EventWatcherPlugin` loads with Navisworks, captures the UI thread, and opens the named pipe `vdc-navis-lab.<pid>`, accessible to the current user only. Requests are handled on a worker thread and any Navisworks API call is marshalled to the UI thread, because the API is single-threaded.

Implemented: every method in [../docs/PROTOCOL.md](../docs/PROTOCOL.md) (`hello`, `doc.info`, `clash.tests`, `clash.export`, `clash.apply`, `doc.save`, `clash.run`, `model.census`, `elements.query`, `clash.image`, `doc.sample`, the `job.*` family). Anything else answers `unsupported` and `hello.methods` says so.

Extraction and `clash.run` run one test per UI-thread slice, confirmed against the real model (D-036, D-038): Navisworks processes its own message queue between tests instead of freezing for the whole operation. `model.census` and `elements.query` run one `Model` per slice the same way, confirmed against the real model (D-039): a census element is the leaf's parent (one per assembly, not one per material solid), deduped by `InstanceHashCode`. `clash.image` uses `DocumentClashTests.TestsImageForResult` (a `Bitmap`, saved as PNG) and does not modify the document, so it carries no `if_fingerprint`; confirmed against the real model (D-042/D-043). `clash.apply`'s `viewpoints[]` saves a `SavedViewpoint` per entry under `Document.SavedViewpoints` (D-045): it does modify the document, so it goes through the same plan as `groups`/`statuses`, not a one-shot call like `clash.image`; confirmed against a real model. A bare camera (`TestsViewpointForResult`) was not useful on its own (D-046), and framing by `result.ViewBounds` put the camera at the world origin because that box is empty (D-048): the viewpoint camera is computed from the clash centre (oblique, distance from the clash extent), the whole model is ghosted with `OverrideTemporaryTransparency`, both clashing items are red via `OverrideTemporaryColor`, and the item is created with `DocumentSavedViewpoints.AddCopy(CaptureRuntimeOverrides())` and then refreshed with `ReplaceFromCurrentView`, because `CaptureRuntimeOverrides()` returns a default camera. Confirmed visually on a real model. Beams, columns, conduits and pipes also get an oriented box (`Orientation.cs`, D-051/D-052): triangles come from the COM API (`InwOaFragment3.GenerateSimplePrimitives`, local-to-world matrix per fragment), the long axis from PCA and the section from a minimum-area rectangle; it is accepted only if the triangles fit inside the box Navisworks reports for the same item. A nested Revit link adds a path node (`file.rvt : 15 : location ...`) that the extractor skips so category and level stay aligned (D-049). Results dropped because an element no longer exists are counted as `skipped`, with `skipped_open` for those still new or active (D-050).

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
