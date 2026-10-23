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
| `hello` | none | `product`, `version`, `api`, `instance_id`, `doc`, `methods` (what this add-in implements) |
| `doc.info` | none | `doc` fields plus `models`, `units` |
| `model.census` | none | per model: element count, top categories |
| `elements.query` | `criteria[]`, `group_by`, `limit` | `count`, `groups[]`, `sample[]` |
| `clash.tests` | none | list of `{name, kind, status, tolerance, count}` |
| `clash.run` | `tests[]` | `{job_id}` |
| `clash.export` | `tests[]`, `limit` | `{job_id}`; the result is a `vdc_navis_lab.clashset/1` document |
| `clash.apply` | `if_fingerprint`, `dedupe_key`, `groups[]`, `statuses[]`, `viewpoints[]` | `applied`, `verified`, `missing` |
| `doc.save` | `if_fingerprint`, `path?` | `saved`, `verified`, `path` |
| `clash.image` | `clash_id`, `path` | `saved`, `path` |
| `job.status` / `job.result` / `job.cancel` / `job.list` | `job_id` | job state, result, or list |

`hello.methods` is authoritative: a method that is not listed answers `unsupported`, and the server degrades with a clear message. The v0.2 add-in implements every method in this document, verified end to end against a real document, including `clash.image`. `clash.image` renders a PNG framed on that clash and writes it to `path` directly (the server resolves and validates `path` under the allowed output folders first, the same way `doc.save`'s path is handled); it never modifies the document, so unlike `clash.apply` it carries no `if_fingerprint` and needs no plan. `clash.apply`'s `viewpoints[]` is `[{guid, name}]`: it does modify the document (one `SavedViewpoint` per entry, under `Document.SavedViewpoints`), so it goes through the same plan as `groups`/`statuses`, counted in `applied.viewpoints_added`/`viewpoints_reused` and `verified.viewpoints`.

Long operations return a `job_id` immediately. States: `running`, `completed`, `failed`, `cancelled`. `job.status`'s `progress` is `{kind:"indeterminate"}` or, once a job knows its size, `{kind:"determinate", done, total}`; `clash.export` reports one done per test, so Navisworks stays responsive between tests instead of a single block for the whole export.

## Document identity

`doc.fingerprint` identifies the document (path and model files); `doc.revision` changes whenever tests, results or result statuses change. Writes carry `if_fingerprint` and fail with `stale_document` on mismatch.

## `vdc_navis_lab.clashset/1`

```
{ schema, source, document{title,fingerprint,revision}, models[], truncated, skipped,
  tests[{name,kind,status,tolerance,count}],
  clashes[{id,test,name,status,kind,distance,point[3],level,
           a{id,name,category,family,model,level,system?,props,bbox[[x,y,z],[x,y,z]]}, b{...}}] }
```

Units are metres. `distance` is negative for penetration. `kind` is `hard`, `clearance` or `duplicate`. Status values: `new`, `active`, `reviewed`, `approved`, `resolved`. `skipped` counts results the add-in dropped because one of their elements no longer exists in the model; it is never silent (`nw_analyze`'s coverage reports it). The same shape is what `nw_report(kind="json")` writes and `nw_analyze(path=...)` reads.
