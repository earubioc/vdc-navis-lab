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
| `clash.apply` | `if_fingerprint`, `dedupe_key`, `groups[]`, `statuses[]` | `applied`, `verified`, `missing` |
| `doc.save` | `if_fingerprint`, `path?` | `saved`, `verified`, `path` |
| `job.status` / `job.result` / `job.cancel` / `job.list` | `job_id` | job state, result, or list |

`hello.methods` is authoritative: a method that is not listed answers `unsupported`, and the server degrades with a clear message. The v0.1 add-in implements `hello`, `doc.info`, `clash.tests`, `clash.export`, `clash.apply`, `doc.save`, `doc.sample` and the `job.*` family; `model.census`, `elements.query` and `clash.run` remain unimplemented.

Long operations return a `job_id` immediately. States: `running`, `completed`, `failed`, `cancelled`.

## Document identity

`doc.fingerprint` identifies the document (path and model files); `doc.revision` changes whenever tests, results or result statuses change. Writes carry `if_fingerprint` and fail with `stale_document` on mismatch.

## `vdc_navis_lab.clashset/1`

```
{ schema, source, document{title,fingerprint,revision}, models[], truncated,
  tests[{name,kind,status,tolerance,count}],
  clashes[{id,test,name,status,kind,distance,point[3],level,
           a{id,name,category,family,model,level,system?,props,bbox[[x,y,z],[x,y,z]]}, b{...}}] }
```

Units are metres. `distance` is negative for penetration. `kind` is `hard`, `clearance` or `duplicate`. Status values: `new`, `active`, `reviewed`, `approved`, `resolved`. The same shape is what `nw_report(kind="json")` writes and `nw_analyze(path=...)` reads.
