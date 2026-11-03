# Roadmap

## Next (after 1.0)

1. **A second model and Navisworks 2025 and 2024.** Everything so far was measured on one federated model of one project; the add-in is built against the 2026 assemblies.
2. **Calibrate with a structural designer.** The beam-passage thresholds (middle third, diameter of a third of the dimension, 25 and 70 degrees, which failures are high or critical) are a starting point in `[score.beam_pass]`; they are not a code. Columns still have no rule of their own.
3. **A criteria document.** A short yes/no sheet for a structural designer, turned into profile rules, so the coordination and structural criteria both live in a file the server reads.
4. **Prebuilt add-in and one-command installer.**

Every other method in `docs/PROTOCOL.md` is implemented and confirmed against a real Navisworks document (2026-10-21 to 2026-10-23):

- **Reads:** `hello`, `doc.info`, `clash.tests`, `clash.export` (chunked, one test per UI-thread slice), `doc.sample`, `model.census`, `elements.query` (one `Model` per UI-thread slice; a federated NWD opened as one document reports as a single `Model` in `Document.Models`, not one per nested `.nwc` -- an honest finding, not a bug).
- **Writes:** `clash.apply` (status via `TestsEditResultStatus`, grouping via `TestsInsertCopy`/`TestsMove`) and `doc.save` (both `save_as` and `save` over the open file), through `DocumentClashTests` because results and tests come back read-only from the API -- setting properties directly threw `NotSupportedException` on the first real attempt. `clash.run` (`TestsRunTest`, one test per UI-thread slice). `clash.apply` also confirmed at 10x scale (10 issues, 66 clashes in one plan).
- **Calibration and honesty:** `score.sleeve` dampens and caps clean through-crossings of a floor/wall by a small MEP run (critical 52→35, medium 1→18 on the first real model), and `skipped` (results dropped because an element no longer exists in the model) is counted and reported (56 on that same model, matching the 710-vs-654 gap first noticed).
- **Saved viewpoints (v0.2.6):** camera from the clash centre, ghosted model, clashing items in red; confirmed visually on a real model. The first two versions were blank or showed the building without the clash (`ViewBounds` was empty).
- **Realistic priorities (v0.2.7 to v0.3.2):** thin conduits embedded in a floor or wall drop to low (`small_cap`); a conduit no longer vanishes into a "Nivel 5" category when it comes from a nested Revit link; the analysis checks the model for modelled sleeves and says when there are none; skipped results report how many were still open; beams, columns, conduits and pipes carry an oriented box so a passage through a beam is judged by angle, position along the span and the depth, and diameter (`engine/passage.py`). Measured on the first real model: critical 35 to 15, high 60 to 79, medium 18 to 17, low 0 to 2; electrical x structure went from 15 critical to 2.
- **Image per clash:** `clash.image` (`DocumentClashTests.TestsImageForResult`, a `Bitmap` saved as PNG), exposed as `nw_report(kind="image", issue=<id>)`, confirmed against a real model (a 1.13 MB PNG matching the native Clash Detective render).

- **PDF report (v0.4):** `nw_report(kind="pdf")`, a small PDF writer with no dependencies (A4, Helvetica, tables, priority bar); tried on the real model export (8 pages, 183 issues).
- **View tools (v0.4):** `nw_view` selects an issue and frames it, colours the model by priority and resets, through `view.select`, `view.color` and `view.reset` in the add-in; compiled against the real Navisworks 2026 assemblies, pending the first live confirmation.

- **Author hand-off and selection sets (v0.5):** `nw_report(kind="handoff")` and `nw_apply` op `set`; the hand-off was generated from the real model's export and the sets were run in Navisworks in v1.0.
- **Setup, audit, group by level and rules (v1.0):** `nw_setup` (`sets.list`, `props.sample`, `setup.apply`), `nw_model(audit=true)`, `nw_apply` `by` and `rules`; all run against the real application except the rule previews. A federated NWD reports each source file in the census.

## Capabilities under consideration

- Ignore rules and tolerances per pair in the generated tests; a full audit that compares units and coordinates against the project origin.
- Narrative report for a coordination meeting.
- Cross-project learning of which crossings are usually accepted.
- Revit and IFC element enrichment (system, level, size) for better scoring.

## Not planned

- A second analysis engine inside the add-in.
- Raw API passthrough tools. They defeat the safety model.
