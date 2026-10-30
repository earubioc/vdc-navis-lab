# Roadmap

## Next (needed to call it usable)

1. **Field-test ingestion** with real Clash Detective XML and CSV exports from different Navisworks versions and languages.
2. **Calibrate with a structural designer.** The beam-passage thresholds (middle third, diameter of a third of the dimension, 25 and 70 degrees, which failures are high or critical) are a starting point in `[score.beam_pass]`; they are not a code. A vertical run that stops inside the beam is told apart from one that crosses it (kind `end`); columns still have no rule of their own.
3. **A second model and Navisworks 2025.** Everything so far was measured on one federated model of one project.
4. **Trade-specific profile overrides.** MEC files are classified as HVAC by default; some teams need their own mapping.

Every other method in `docs/PROTOCOL.md` is implemented and confirmed against a real Navisworks document (2026-10-21 to 2026-10-23):

- **Reads:** `hello`, `doc.info`, `clash.tests`, `clash.export` (chunked, one test per UI-thread slice), `doc.sample`, `model.census`, `elements.query` (one `Model` per UI-thread slice; a federated NWD opened as one document reports as a single `Model` in `Document.Models`, not one per nested `.nwc` -- an honest finding, not a bug).
- **Writes:** `clash.apply` (status via `TestsEditResultStatus`, grouping via `TestsInsertCopy`/`TestsMove`) and `doc.save` (both `save_as` and `save` over the open file), through `DocumentClashTests` because results and tests come back read-only from the API -- setting properties directly threw `NotSupportedException` on the first real attempt. `clash.run` (`TestsRunTest`, one test per UI-thread slice). `clash.apply` also confirmed at 10x scale (10 issues, 66 clashes in one plan).
- **Calibration and honesty:** `score.sleeve` dampens and caps clean through-crossings of a floor/wall by a small MEP run (critical 52→35, medium 1→18 on the first real model), and `skipped` (results dropped because an element no longer exists in the model) is counted and reported (56 on that same model, matching the 710-vs-654 gap first noticed).
- **Saved viewpoints (v0.2.6):** camera from the clash centre, ghosted model, clashing items in red; confirmed visually on a real model. The first two versions were blank or showed the building without the clash (`ViewBounds` was empty).
- **Realistic priorities (v0.2.7 to v0.3.2):** thin conduits embedded in a floor or wall drop to low (`small_cap`); a conduit no longer vanishes into a "Nivel 5" category when it comes from a nested Revit link; the analysis checks the model for modelled sleeves and says when there are none; skipped results report how many were still open; beams, columns, conduits and pipes carry an oriented box so a passage through a beam is judged by angle, position along the span and the depth, and diameter (`engine/passage.py`). Measured on the first real model: critical 35 to 15, high 60 to 79, medium 18 to 17, low 0 to 2; electrical x structure went from 15 critical to 2.
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
