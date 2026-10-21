# Roadmap

## Next (needed to call it usable)

1. **Compile and run the add-in against a real Navisworks.** Verify the API calls marked `VERIFY`, the named pipe from Python on Windows, and unit handling.
2. **Chunked extraction.** Process a few tests per UI slice so Navisworks stays responsive during long exports.
3. **Field-test ingestion** with real Clash Detective XML and CSV exports from different Navisworks versions and languages.
4. **Calibrate the profile** on real projects. The demo tower ranks many issues as high; the weights and gates need real data.

## Add-in methods not yet implemented

`model.census`, `elements.query`, `clash.run`, `clash.apply`, `doc.save`. The server already speaks them and the simulator implements them.

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
