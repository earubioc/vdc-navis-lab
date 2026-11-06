# Changelog

## 1.0.1

- `desktop-config --client lmstudio`: prints or merges the entry into LM Studio's `mcp.json` (backup first, other servers untouched). `llm-eval`: tool-calling evaluation of any OpenAI-compatible endpoint (LM Studio) against the simulator, seven scenarios by N repetitions, with figures per scenario and saved transcripts (see `docs/LM_STUDIO.md`).
- `vdc-navis-lab-cli bench`: scale measurement that prints figures only. Default: a synthetic infrastructure federation (`build_infra`, 240 tests by 3000 results, clustered along an alignment, with closed results, noise, clearance tests and shared elements) generated and analysed in memory; `--file` for an exported clash file; `--live` for the whole path against the open Navisworks, including how Navisworks answers while it extracts and the peak memory of both processes.
- `vdc-navis-lab-cli verify [--writes] [--simulate]`: self-check that exercises status, census, analysis, views, reports, exports, images and, with `--writes`, a group, a status and a viewpoint. It prints only PASS/FAIL and figures (no names), so its output can be shared about a confidential model. Peak Navisworks memory is reported on Windows.
- Add-in: changing a clash result's status no longer references the `Assignee` type at compile time; the call picks the overload the running Navisworks has (two or three arguments). It was the only error when building against Navisworks Manage 2025. 2025 is not listed as verified until a live run confirms it.
- Navisworks 2025: the add-in now creates a WinForms UI context when Navisworks leaves none installed on its main thread (2025 does; 2026 does not), which is what made every call fail with "UI thread context not captured". Verified live in Manage 2025: connection, model audit, `nw_setup` (5 sets and 5 tests created) and running the tests.
- `nw_analyze` on a 1.5 GB federation: the sleeve name scan (about 135 s) now runs once in the background; while it runs the call answers `state: running, stage: sleeve_scan`, and the retry collects the same export instead of starting another one (each retry used to repeat export and scan).
- `nw_analyze` counted modeled sleeves with one full pass over the model per name pattern (ten passes); on a large federation that took minutes and outlasted the client's wait. It is now one pass (`contains_any` in `elements.query`). An unknown criterion operator is rejected instead of matching nothing.
- Large projects: the live export is capped at 40,000 clashes (`VDC_NAVIS_LAB_MAX_CLASHES`, `0` removes the cap) and the add-in stops the export when its memory growth passes 1 GB; either way the analysis is marked truncated in the coverage instead of failing late. Found by stress test: ten clearance tests of 1 m on a five-model federation (well over 100,000 results) made Navisworks Manage 2025 run out of memory and close. 37,783 clashes from four tests were extracted and analysed in under a minute on the same machine. Streaming the export to disk in pages is the 1.1 work for infrastructure models.
- The model census is read once per document and runs in a background thread: on a 1.6 GB federated NWD it takes about two minutes, longer than a tool call may wait and longer than the 30 s bridge timeout, so before this it could never complete there. The first call answers `running`; the next one returns the stored result.
- The add-in logs failed and slow calls and the UI context it found at load (`%LOCALAPPDATA%\vdc-navis-lab\addin.log`); `probar.ps1` prints what the connector saw when no model is found.
- Installer and manuals: `instalar.ps1`, version-aware add-in scripts and step-by-step guides in Spanish and English.

## 1.0.0

- `nw_setup`: builds the coordination scaffolding in Navisworks through the same two-step plan as `nw_apply`. `discipline_sets` saves one dynamic search set per discipline (on the source-file property, with Navisworks internal names so it does not depend on the interface language); `tests` creates one clash test per pair of the matrix (the profile's `expected_pairs` or a list), pointing at those sets; `search_set` saves a dynamic search set from criteria (`model`, `category`, `family`, `level`, `name`, `system`, or any property). Existing sets and tests are reused, never overwritten. `action="list"` shows the sets and tests in the document and `action="properties"` lists the property names of an element.
- `nw_model(audit=true)`: model audit. Empty or duplicated models, models without discipline, file name against content, models far from the rest or in other units (co-location), and disciplines the expected pairs need but no model provides.
- The model census now looks inside a federated NWD and reports each source file with its box, instead of one model with the name of the NWD.
- `nw_apply` op `group` accepts `by="level"`, `"pair"` or `"pair_level"`; op `rules` runs the profile's `[[rules]]` (or rules given inline) as ordinary group, status, viewpoint and set operations, with the same preview.
- Selection sets (op `set`), `nw_view` and group by level confirmed in a real Navisworks Manage 2026 document.
- 131 tests. The scoring weights and the beam-passage thresholds are defaults calibrated on one real model.

## 0.5.0

- `nw_report(kind="handoff")`: a CSV for the authors, one row per element that has to change, grouped by the model that has to be edited, with level, family and type, the authoring Id when the export carries one, the issue's coordinates and the action.
- `nw_apply` op `set`: saves selection sets (folder "VDC Lab") with the elements of each issue, or one merged set when `name` is given. Existing sets with the same name are reused. New in this version, not yet run in Navisworks.
- Licence changed from MIT to Apache License 2.0 (with a NOTICE file); the public name is VDC Navis Lab.
- 118 tests.

## 0.4.0

- `nw_report(kind="pdf")`: a readable coordination report (decisions to make, who moves what, hotspots, top issues), written without dependencies.
- `nw_view`: select an issue and frame it, colour the model by priority, reset the appearance. View-only, no plan needed.

## 0.3.5

- Modelling errors (an element running through a slab, a floor finish overlapping structure) become one model-update decision per model instead of dozens of coordination issues.

## 0.3.4

- Issues are split by kind of crossing (slab embedding, beam, column); a vertical run that ends inside a beam is not a passage through it.

## 0.3.2 and earlier

- Beam passage from oriented boxes, sleeves and embedded conduits, real element identity from the Revit tree, saved viewpoints, images per clash, running tests, model census, two-step writes with verified results, BCF 2.1, simulator.
