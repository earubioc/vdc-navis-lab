# Tool reference

Try them by hand: `vdc-navis-lab-cli tools` lists them, `vdc-navis-lab-cli call nw_profile '{"action":"show"}'` calls one, `vdc-navis-lab-cli demo` runs a whole flow.

All tools return JSON. Failures come back as `{"error": code, "detail": ..., "hint": ...}`. Tools that accept `lang` use `es` or `en` (default from the profile).

## State

**`nw_status()`** Reachable Navisworks instances, the selected one, the active profile, the clash tests of the open document (with the ones that never ran), whether an analysis exists and whether it is stale. Never fails when Navisworks is closed.

**`nw_connect(action, target)`** `list`, `select` (pin an `instance_id`; required before writes when several are open), `release`.

**`nw_job(action, job_id)`** `status`, `list`, `cancel`.

## Criteria

**`nw_profile(action, path, mapping)`** `show`, `validate`, `load` (a `.toml`), `reset`, `assign` (`{"model.nwc": "STR"}`). Loading or assigning re-ranks the current analysis without re-extracting.

## Model

**`nw_model()`** Federation census: models, element counts, top categories, and the discipline each model looks like by name and by content, flagging disagreement.

**`nw_query(where, group_by, limit)`** Count and sample elements. `where=[{"field":"category","op":"eq|contains|in","value":...}]`. Fields: `category`, `model`, `level`, `family`, `name`, `system`, or any property name.

## Analysis

**`nw_run(tests, max_wait_s)`** Run clash tests (all or named). Replaces stored results, so the current analysis becomes stale.

**`nw_analyze(path, tests, top, max_wait_s, job_id, lang)`** Extract (live, or from `path`: `.xml`, `.csv`, `.json`), filter, cluster, score, find causes, check coverage. Returns a summary. If live extraction outlasts `max_wait_s`, a `job_id` is returned; call again with it.

**`nw_issues(priority, discipline, responsible, level, cause, sort, limit, offset, lang)`** Filter and page through issues. `sort`: `rank`, `score`, `clashes`, `level`.

**`nw_issue(id, lang)`** One issue: score components, reasons, both elements, causes, clash ids.

## Output

**`nw_report(kind, path, overwrite, limit, lang)`** `summary`, `matrix`, `hotspots`, `plan` come back inline. `markdown` is inline unless `path` is given. `csv`, `bcf` (BCF 2.1) and `json` write a file under an allowed output folder.

**`nw_snapshot(action, name, against)`** `save`, `list`, `compare`. Compares by element-pair sets; disappeared issues are `absent`, not `resolved`.

## Writes

**`nw_apply(ops, plan_id, dry_run)`** Step 1: `ops=[{"op":"group","issues":"top:20"}, {"op":"status","issues":{"priority":"low"},"status":"reviewed"}]` returns a preview and `plan_id`. Step 2: `plan_id=..., dry_run=false` executes it and reports verified counts. Closing critical issues produces a warning in the preview.

**`nw_document(action, path, confirm, overwrite)`** `save` or `save_as`. Without `confirm` it previews; `confirm=true` works only right after a preview of the same action.

## Planned

See [ROADMAP.md](ROADMAP.md): viewpoints and images per issue, search sets, coloring the model by priority, PDF reports, rule-based test setup.
