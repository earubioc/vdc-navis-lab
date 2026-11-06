# Server <-> add-in protocol

JSON-RPC 2.0, UTF-8, one JSON object per line, **one request per connection**. The server connects, writes one line, reads one line, closes.

Transport: Windows named pipe `\\.\pipe\vdc-navis-lab.<pid>` (ACL: current user only). Development and the simulator use loopback TCP, `tcp://127.0.0.1:PORT`. Maximum line: 64 MB.

## Errors

```json
{"jsonrpc":"2.0","id":3,"error":{"code":-32000,"message":"...","data":{"code":"stale_document","hint":"..."}}}
```

`error.data.code` is one of: `stale_document`, `busy`, `not_found`, `unsupported`, `invalid_params`, `no_document`, `internal`. Messages never contain model content.

## Methods

| Method | Params | Result |
|---|---|---|
| `hello` | `light?` | `product`, `version` (Navisworks), `addin_version` (optional; the add-in's own version, absent in add-ins before 1.1), `api`, `instance_id`, `doc`, `methods` (what this add-in implements) |
| `doc.info` | none | `doc` fields plus `models`, `units` |
| `model.census` | none | per model: element count, top categories |
| `elements.query` | `criteria[]`, `group_by`, `limit` | `count`, `groups[]`, `sample[]` |
| `clash.tests` | none | list of `{name, kind, status, tolerance, count}` |
| `clash.run` | `tests[]` | `{job_id}` |
| `clash.export` | `tests[]`, `limit` | `{job_id}`; the result is a `vdc_navis_lab.clashset/1` document |
| `clash.page` | `test`, `cursor`, `limit`, `closed_describe`, `begin?`, `if_fingerprint?`, `budget_ms?` | one slice of one test: `clashes[]`, `next` (cursor or null), `total`, `open_total`, `closed_total`, `skipped`, `skipped_open`, `closed_skipped`, `memory_growth_mb`, `stop` |
| `clash.release` | none | `{released}`: drops the caches of a paged extraction |
| `clash.apply` | `if_fingerprint`, `dedupe_key`, `groups[]`, `statuses[]`, `viewpoints[]`, `sets[]` | `applied`, `verified`, `missing` |
| `doc.save` | `if_fingerprint`, `path?` | `saved`, `verified`, `path` |
| `clash.image` | `clash_id`, `path` | `saved`, `path` |
| `view.select` | `if_fingerprint`, `guids[]`, `focus?`, `ghost?` | `selected`, `clashes`, `verified`, `framed`, `ghosted`, `missing` |
| `view.color` | `if_fingerprint`, `groups[{color, guids[]}]`, `ghost?` | `groups`, `coloured_items`, `ghosted`, `missing` |
| `sets.list` | none | `sets[{name, path, kind, items or conditions/matches}]` (selection and search sets, folders included) |
| `props.sample` | none | `item`, `from_selection`, `categories[{category, internal, properties[]}]` of the selected or a sample element |
| `setup.apply` | `if_fingerprint`, `sets[]`, `tests[]` | `applied`, `verified`, `missing`, `notes`; `sets[]` is `{name, files[]}` or `{name, where[]}`, `tests[]` is `{name, type, tolerance_m, a_set, b_set}` |
| `view.reset` | `clear_selection?` | `reset`, `selection_cleared` |
| `job.status` / `job.result` / `job.cancel` / `job.list` | `job_id` | job state, result, or list |

`hello.methods` is authoritative: a method that is not listed answers `unsupported`, and the server degrades with a clear message. The v0.2 add-in implements every method in this document, verified end to end against a real document, including `clash.image`. `clash.image` renders a PNG framed on that clash and writes it to `path` directly (the server resolves and validates `path` under the allowed output folders first, the same way `doc.save`'s path is handled); it never modifies the document, so unlike `clash.apply` it carries no `if_fingerprint` and needs no plan. `view.select`, `view.color` and `view.reset` change the view, not the document: the selection and temporary appearance overrides (`OverrideTemporaryColor`, `OverrideTemporaryTransparency`) are never saved and `view.reset` (`ResetAllTemporaryMaterials`) or closing the document puts everything back, so they carry the document fingerprint but need no plan. `view.select` frames with the same oblique camera used for saved viewpoints. `clash.apply`'s `sets[]` is `[{name, guids[]}]`: one static `SelectionSet` per entry (the elements of those clashes), inside the folder "VDC Lab" of `Document.SelectionSets`; a set with the same name is reused, and the result carries `applied.sets_added`/`sets_reused` and `verified.sets`. `clash.apply`'s `viewpoints[]` is `[{guid, name}]`: it does modify the document (one `SavedViewpoint` per entry, under `Document.SavedViewpoints`), so it goes through the same plan as `groups`/`statuses`, counted in `applied.viewpoints_added`/`viewpoints_reused` and `verified.viewpoints`. Each saved viewpoint has an oblique camera computed from the clash centre (the result's `ViewBounds` is empty and put the camera at the origin), the whole model ghosted and both clashing items in red; it is created with `AddCopy` and then refreshed with `ReplaceFromCurrentView`, because `CaptureRuntimeOverrides` returns a default camera (D-048).

Paged extraction (`clash.page`). The server walks the tests one after the other and asks for one bounded slice at a time, so nothing accumulates in Navisworks and no message approaches the 64 MB line limit. Within a test the add-in orders the results open first (new, active, reviewed), then closed (approved, resolved), and the cursor is a position in that order. `limit` is clamped to 25..3000 and each call also stops after `budget_ms` (default 1500, at least one result), so the UI thread is held for about a second and a half at most; the server leaves a pause proportional to the time of each slice (`VDC_NAVIS_LAB_EXTRACT_DUTY`, 0.8 by default) so Navisworks keeps answering. `closed_describe` is the number of closed results the call may describe: `-1` describes all of them (the profile keeps closed results), `N` describes at most N and only counts the rest in `closed_skipped` (the noise filter would drop them anyway; a few are described so that a pair that only has closed results still shows as seen). `begin` marks the first call of an extraction: it clears the caches and takes the memory baseline of the add-in's guard; when Navisworks grows by more than 1 GB since then the call returns what it has with `stop: "memory"`. `if_fingerprint` refuses (`stale_document`) a call after the open document changed. `hello` with `light: true` skips the revision hash (it reads every result of every test) and is what a responsiveness probe should use. An add-in that does not list `clash.page` in `hello.methods` is served with the single export job (`clash.export`), capped at `VDC_NAVIS_LAB_MAX_CLASHES` (40,000 by default for that path).

Long operations return a `job_id` immediately. States: `running`, `completed`, `failed`, `cancelled`. `job.status`'s `progress` is `{kind:"indeterminate"}` or, once a job knows its size, `{kind:"determinate", done, total}`; `clash.export` reports one done per test, so Navisworks stays responsive between tests instead of a single block for the whole export.

## Document identity

`doc.fingerprint` identifies the document (path and model files); `doc.revision` changes whenever tests, results or result statuses change. Writes carry `if_fingerprint` and fail with `stale_document` on mismatch.

## `vdc_navis_lab.clashset/1`

```
{ schema, source, document{title,fingerprint,revision}, models[], truncated, skipped, skipped_open?,
  tests[{name,kind,status,tolerance,count}],
  clashes[{id,test,name,status,kind,distance,point[3],level,
           a{id,name,category,family,model,level,system?,props,bbox[[x,y,z],[x,y,z]],obb?{c,u,h}}, b{...}}] }
         obb (optional, metres): oriented box from the real triangles, only for beams, columns, conduits and pipes
         and only when the triangles fit inside Navisworks' own (looser) box: c centre, u three unit axes (first =
         longest), h half extents. When it cannot be computed the element carries props.obb_status with the reason.
```

Units are metres. `distance` is negative for penetration. `kind` is `hard`, `clearance` or `duplicate`. Status values: `new`, `active`, `reviewed`, `approved`, `resolved`. `skipped` counts results the add-in dropped because one of their elements no longer exists in the model; `skipped_open` is how many of those were still new or active (the rest were already reviewed, approved or resolved and do not affect the analysis). Neither is silent: `nw_analyze`'s coverage reports them. The same shape is what `nw_report(kind="json")` writes and `nw_analyze(path=...)` reads.
