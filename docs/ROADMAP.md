# Roadmap

## Next (needed to call it usable)

1. **Chunked extraction.** Process a few tests per UI slice so Navisworks stays responsive during long exports.
2. **Field-test ingestion** with real Clash Detective XML and CSV exports from different Navisworks versions and languages.
3. **Calibrate the profile** on real projects. The first real model (654 clashes) produced 52 critical and 60 high of 113 issues, and each of the ten top issues reports penetration equal to 100% of the smaller element's dimension (pipes and conduits crossing structure), so the bands do not yet separate crossings that a sleeve resolves from true conflicts.
4. **Report skipped results.** The add-in skips results whose elements are missing from the model (710 listed, 654 exported in the first real model) and should say so in the analysis coverage.

## Add-in methods not yet implemented

`model.census`, `elements.query`, `clash.run`. The server already speaks them and the simulator implements them.

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
