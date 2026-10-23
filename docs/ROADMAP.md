# Roadmap

## Next (needed to call it usable)

1. **Field-test ingestion** with real Clash Detective XML and CSV exports from different Navisworks versions and languages.
2. **Confirm saved viewpoints against a real model.** Implemented (`nw_apply(ops=[{"op":"viewpoint", "issues":...}])`, one `SavedViewpoint` per issue under `Document.SavedViewpoints`), compiles cleanly, not yet run against real Navisworks.

Every other method in `docs/PROTOCOL.md` is implemented and confirmed against a real Navisworks document (2026-10-21 to 2026-10-23):

- **Reads:** `hello`, `doc.info`, `clash.tests`, `clash.export` (chunked, one test per UI-thread slice), `doc.sample`, `model.census`, `elements.query` (one `Model` per UI-thread slice; a federated NWD opened as one document reports as a single `Model` in `Document.Models`, not one per nested `.nwc` -- an honest finding, not a bug).
- **Writes:** `clash.apply` (status via `TestsEditResultStatus`, grouping via `TestsInsertCopy`/`TestsMove`) and `doc.save` (both `save_as` and `save` over the open file), through `DocumentClashTests` because results and tests come back read-only from the API -- setting properties directly threw `NotSupportedException` on the first real attempt. `clash.run` (`TestsRunTest`, one test per UI-thread slice). `clash.apply` also confirmed at 10x scale (10 issues, 66 clashes in one plan).
- **Calibration and honesty:** `score.sleeve` dampens and caps clean through-crossings of a floor/wall by a small MEP run (critical 52→35, medium 1→18 on the first real model), and `skipped` (results dropped because an element no longer exists in the model) is counted and reported (56 on that same model, matching the 710-vs-654 gap first noticed).
- **Image per clash:** `clash.image` (`DocumentClashTests.TestsImageForResult`, a `Bitmap` saved as PNG), exposed as `nw_report(kind="image", issue=<id>)`, confirmed against a real model (a 1.13 MB PNG matching the native Clash Detective render).

## Capabilities under consideration

- Search sets from a query, to reuse a selection in Navisworks.
- Color the model by priority, with a guaranteed reset.
- Rule-based clash test creation from the discipline matrix.
- PDF report and narrative report for a coordination meeting.
- Cross-project learning of which crossings are usually accepted.
- Revit and IFC element enrichment (system, level, size) for better scoring.

## Not planned

- A second analysis engine inside the add-in.
- Raw API passthrough tools. They defeat the safety model.
