# Changelog

## 0.5.0 (beta)

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
