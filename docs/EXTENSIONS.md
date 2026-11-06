# Extensions: the plugin interface

The core is open (Apache 2.0). Commercial capabilities live in a separate package that the server discovers at start. This page is the contract between the two.

## Discovery

A package that provides capabilities declares an entry point in the group `vdc_navis_lab.plugins`:

```toml
[project.entry-points."vdc_navis_lab.plugins"]
pro = "vdc_navis_lab_pro:register"
```

`register(mcp, app)` receives the FastMCP server (`None` outside the server) and the `App`. It provides implementations with `app.capabilities.provide(name, fn, plugin=..., available=...)` and returns a `PluginInfo`. `VDC_NAVIS_LAB_NO_PLUGINS=1` loads nothing.

## Capabilities (frozen inside a minor version)

| Name | Called as |
|---|---|
| `writes.execute`, `setup.execute` | `(app, plan_id)` |
| `document.save` | `(app, ep, doc, target, key)` |
| `report.csv`, `report.bcf`, `report.pdf`, `report.handoff`, `report.json` | `(result, profile, limit)` returning bytes |
| `report.image` | `(app, ep, issue, target)` |
| `snapshot.compare` | `(before, after)` |
| `profiles.packs` | `()` |

Adding a name is compatible; changing a signature or removing a name needs a new minor and a new Pro. `tests/test_public_api.py` fails when a signature changes.

## What the core guarantees

- No provider, an unavailable provider (for example an expired license), a failing provider or a plugin for another core line: the capability answers `pro_required` with a hint, the rest of the server keeps working, and `nw_status.extensions` says why.
- The gate lives in the server. The Navisworks add-in speaks an open protocol (`docs/PROTOCOL.md`) and cannot be gated.
- A plugin version N.M requires the core N.M.x (`Requires-Dist: vdc-navis-lab>=N.M,<N.(M+1)`); the loader reads it from the package metadata and refuses a mismatch with `state: incompatible`.

## Usage log

`VDC_NAVIS_LAB_USAGE_LOG=1` appends `{ts, capability, outcome}` lines to `usage.log` in the data folder. It never records names of models, projects, files or elements. Off by default.
