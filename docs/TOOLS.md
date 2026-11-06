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

**`nw_model(audit)`** Federation census: each source file (also inside a federated NWD) with element count, top categories, and the discipline it looks like by name and by content, flagging disagreement. `audit=true` adds the model audit: empty or duplicated models, models without discipline, models far from the rest or in other units (thresholds in the profile's `[audit]`), and the disciplines the expected pairs need but no model provides.

**`nw_query(where, group_by, limit)`** Count and sample elements. `where=[{"field":"category","op":"eq|contains|in","value":...}]`. Fields: `category`, `model`, `level`, `family`, `name`, `system`, or any property name.

## Analysis

**`nw_run(tests, max_wait_s)`** Run clash tests (all or named). Replaces stored results, so the current analysis becomes stale.

**`nw_analyze(path, tests, top, max_wait_s, job_id, lang)`** Extract (live, or from `path`: `.xml`, `.csv`, `.json`), filter, cluster, score, find causes, check coverage. Returns a summary. If live extraction outlasts `max_wait_s`, a `job_id` is returned; call again with it.

**`nw_issues(priority, discipline, responsible, level, cause, sort, limit, offset, lang)`** Filter and page through issues. `sort`: `rank`, `score`, `clashes`, `level`.

**`nw_issue(id, lang)`** One issue: score components, reasons, both elements, causes, clash ids.

## Output

**`nw_report(kind, path, overwrite, limit, lang, issue)`** `summary`, `matrix`, `hotspots`, `plan` come back inline. `markdown` is inline unless `path` is given. `csv`, `bcf` (BCF 2.1), `pdf` (decisions to make, who moves what, where it concentrates, top issues; no dependencies, `limit` caps the rows) `handoff` (a CSV for the authors: one row per element to change, grouped by the model to edit, with level, family and type, authoring Id when the export has one, coordinates and action) and `json` write a file under an allowed output folder. `image` (needs `issue=<id>` and a live Navisworks document, not a file analysis) writes a PNG framed on that issue's representative clash.

**`nw_snapshot(action, name, against)`** `save`, `list`, `compare` (compare is a Pro capability: without it the call answers `pro_required`). Compares by element-pair sets; disappeared issues are `absent`, not `resolved`.

## View

**`nw_view(action, issues, ghost, clear_selection)`** Temporary and view-only: nothing is saved in the document and no plan is needed. `select` takes an issue id, a list, `top:N` or a filter, selects the elements of those issues and frames the first one (`ghost=true` fades the rest of the model). `color` paints the chosen issues (default all) by priority: red critical, orange high, yellow medium, green low; the most severe colour wins on shared elements. `reset` restores the appearance (`clear_selection=true` also clears the selection). Needs an analysis of the open document, not of a file.

## Writes

**`nw_apply(ops, plan_id, dry_run)`** Op `group` accepts `by`: `issue` (default), `level`, `pair` or `pair_level`, for one group per level or pair and test instead of one per issue. Op `rules` runs the `[[rules]]` of the profile (or `rules=[...]` inline, optionally `names=[...]` to pick some) as ordinary ops: each rule is `{name, when:{priority, pair, discipline, responsible, level, cause}, status | group | viewpoint | set}`. Step 1: `ops=[{"op":"group","issues":"top:20"}, {"op":"status","issues":{"priority":"low"},"status":"reviewed"}]` returns a preview and `plan_id`. Step 2: `plan_id=..., dry_run=false` executes it and reports verified counts. `{"op":"viewpoint","issues":"top:5"}` saves viewpoints; `{"op":"set","issues":{"priority":"critical"},"name":"Críticos"}` saves one selection set (folder `VDC Lab`) with all their elements, or one set per issue when `name` is omitted. Closing critical issues produces a warning in the preview.

**`nw_document(action, path, confirm, overwrite)`** `save` or `save_as`. Without `confirm` it previews; `confirm=true` works only right after a preview of the same action.

## Setup

**`nw_setup(action, ops, plan_id, dry_run)`** Builds the coordination scaffolding. `action="plan"` (default), step 1: `ops=[{"op":"discipline_sets"}, {"op":"tests","pairs":"matrix"}, {"op":"search_set","name":"Ductos","where":[{"field":"category","op":"contains","value":"Duct"}]}]` returns a preview and `plan_id`; step 2: `plan_id=...` executes it and verifies by rereading. `discipline_sets` saves one dynamic search set per discipline (models classified like `nw_model`) in the folder "VDC Lab". `tests` creates one clash test per pair (`pairs="matrix"` uses the profile's `expected_pairs`, or a list such as `["STR-ELE"]`; `tolerance_mm`, default 1; `type` `hard` or `clearance`; `prefix`, default `VDC `) between the discipline sets, which it creates if missing; pairs with a discipline that has no model are skipped and reported. The tests are not run: call `nw_run`. `search_set` takes `where=[{field, op, value}]` with `field` in `model`, `category`, `family`, `level`, `name`, `system`, or `category` plus `property` for any property (`internal=true` to give Navisworks internal names); `op` is `eq`, `contains` or `wildcard`. A criterion that finds nothing is reported, not saved. Existing sets and tests with the same name are reused. `action="list"` shows the sets and tests of the document; `action="properties"` lists the property names and values of the selected element (or of a sample element), to write criteria.

