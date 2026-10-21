# Roadmap

## Next (needed to call it usable)

1. **Field-test ingestion** with real Clash Detective XML and CSV exports from different Navisworks versions and languages.

Calibrated and confirmed against the real model (2026-10-21): the first real model (654 clashes) produced 52 critical and 60 high of 113 issues, and each of the ten top issues reported penetration equal to 100% of the smaller element's dimension (pipes and conduits crossing floors/walls); `score.sleeve` dampens and caps clean through-crossings of a floor/wall by a small MEP run, keeping a beam or column at full severity. With it the same model gives 35 critical, 60 high, 18 medium. Extraction also runs one test per UI-thread slice instead of the whole export in one block, confirmed responsive between tests; `skipped` (results dropped because an element no longer exists in the model) is counted and reported, confirmed at 56 on the first real model (710 listed, 654 exported) -- `nw_analyze`'s coverage warns about it and `complete` turns false, instead of staying silent. `clash.run` (`DocumentClashTests.TestsRunTest`, one test per UI-thread slice) is implemented and confirmed the same way, running `MEC-HYS` on the real model.

## Add-in methods not yet implemented

`model.census`, `elements.query`. The server already speaks them and the simulator implements them.

`clash.apply` and `doc.save` are implemented and verified against a real Navisworks document (status, grouping, save_as), re-reading it to confirm the change. Results and tests come back read-only from the API: both methods go through `DocumentClashTests` (`TestsEditResultStatus`, `TestsInsertCopy`, `TestsMove`) instead of setting properties directly, which threw `NotSupportedException` on the first real attempt.

## Capabilities under consideration

- Viewpoint per issue, camera framed on the clash point, with an image.
- Search sets from a query, to reuse a selection in Navisworks.
- Color the model by priority, with a guaranteed reset.
- Rule-based clash test creation from the discipline matrix.
- PDF report and narrative report for a coordination meeting.
- Cross-project learning of which crossings are usually accepted.
- Revit and IFC element enrichment (system, level, size) for better scoring.

## Not planned

- A second analysis engine inside the add-in.
- Raw API passthrough tools. They defeat the safety model.
