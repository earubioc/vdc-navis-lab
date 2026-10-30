# vdc-navis-lab

Clash coordination for Autodesk Navisworks Manage, exposed as an [MCP](https://modelcontextprotocol.io) server so any MCP-capable assistant can read, rank and act on clash results.

Navisworks reports thousands of raw clashes. The hard part of coordination is deciding which ones matter, which discipline has to move, and which fifty of them are the same mistake repeated on every floor. `vdc-navis-lab` does that analysis in a deterministic engine and gives the assistant a small set of tools to work with the result, instead of handing it a pile of raw rows.

> **Status: v0.3, early.** The analysis engine, file ingestion, exports, the MCP server and a Navisworks simulator are implemented and tested (111 tests). The Navisworks add-in is built and verified against a real Navisworks Manage 2026: every method in the protocol works against a real document, including writes (`clash.apply`, `doc.save`), re-running tests (`clash.run`), a model census (`model.census`, `elements.query`) and an image per clash (`clash.image`). Saved viewpoints (camera on the clash, ghosted model, clashing items in red) and the beam-passage rule (from oriented boxes of the real geometry) are confirmed against a real model; issues are split by kind of crossing and modelling errors (an element running through a slab, a finish overlapping structure) are grouped into one model-update request, tried on an export of that model and still to be re-confirmed live. Tested on one real model, one installation; the beam-passage thresholds are a starting point to agree with a structural designer; PDF reports and Navisworks 2025 are still missing. See [What is verified](#what-is-verified).

## What it does

- **Issues, not clashes.** Raw clashes are tagged by discipline, stripped of noise (designed openings, shallow touches, self-assemblies), clustered into issues, and ranked with a score whose every component is explained.
- **Root causes.** Detects one element involved in many issues (a riser, a rack) and one detail repeated across levels, so one decision closes many issues.
- **Who has to move.** Each issue names the discipline that should adjust, based on how movable each side is.
- **Honest coverage.** Reports tests that never ran, discipline pairs with no results, and tests whose results were all filtered. "No clashes" is never reported as "clean" without saying what was not checked.
- **Safe writes.** Changes to the Navisworks document are two-step: a dry run returns a `plan_id`, and only that id can be executed. Execution is bound to the document and revision, refuses stale analyses, and reports what was verified by re-reading the document.
- **Works without Navisworks.** Reads Clash Detective XML, CSV and its own JSON export, so analysis, reports and BCF export run anywhere.
- **Your criteria, in a file.** Disciplines, weights, tolerances and priority bands live in a TOML profile you can version and review.

## Quick start

Use a virtual environment, not your global Python (the `mcp` dependency pulls recent `starlette` and `websockets`, which can conflict with other tools installed globally).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
vdc-navis-lab-cli demo                                      # guided walk-through, no setup, touches nothing
vdc-navis-lab-cli sample examples/tower-demo.json           # a synthetic 5-level tower
vdc-navis-lab-cli analyze examples/tower-demo.json --lang en
```

`vdc-navis-lab` itself is a stdio server meant to be launched by an MCP client; typed into a terminal it prints a note and exits (`--serve` forces it). To let a client talk to a simulated Navisworks, keep `vdc-navis-lab-cli simulate` running in another terminal.

Step-by-step guides for non-programmers: [manual_para_dummies.md](manual_para_dummies.md) (es), [manual_for_dummies.md](manual_for_dummies.md) (en).

### Connect an assistant

Claude Desktop: `vdc-navis-lab-cli desktop-config --write` merges the entry safely (backup first). Any stdio MCP client:

```json
{
  "mcpServers": {
    "vdc-navis-lab": { "command": "vdc-navis-lab", "env": { "VDC_NAVIS_LAB_READ_ONLY": "0" } }
  }
}
```

Claude Code: `claude mcp add vdc-navis-lab -- vdc-navis-lab`

## Tools

Fourteen tools, prefix `nw_`. Heavy data never enters the conversation: results are summaries or file paths. Details in [docs/TOOLS.md](docs/TOOLS.md).

| Area | Tools |
|---|---|
| State | `nw_status`, `nw_connect`, `nw_job` |
| Criteria | `nw_profile` |
| Model | `nw_model`, `nw_query` |
| Analysis | `nw_run`, `nw_analyze`, `nw_issues`, `nw_issue` |
| Output | `nw_report` (markdown, csv, bcf, json, plan), `nw_snapshot` |
| Writes | `nw_apply`, `nw_document` |

## Safety defaults

| Setting | Effect |
|---|---|
| `VDC_NAVIS_LAB_READ_ONLY=1` | Blocks every write to Navisworks. Previews still work. |
| `VDC_NAVIS_LAB_OUTPUT_ROOTS` | Folders (OS path separator) where files may be written. The default is `~/.vdc_navis_lab/exports`. |
| `VDC_NAVIS_LAB_HOME` | Data folder (snapshots, endpoint registry). |
| `VDC_NAVIS_LAB_ENDPOINT` | Skip discovery: `pipe://NAME` or `tcp://127.0.0.1:PORT`. TCP is loopback only. |

The add-in listens on a Windows named pipe restricted to the current user. File reads are limited to known extensions and 256 MB, XML with DTDs is refused, CSV cells that look like formulas are neutralised, and error messages never echo model content.

## What is verified

| Part | State |
|---|---|
| Analysis engine, profile, exports (CSV, Markdown, BCF 2.1 against the official XSD), snapshots | Tested on synthetic data |
| MCP server over stdio, 14 tools, write flow, read-only mode | Tested end to end against the simulator |
| Clash Detective XML ingestion | Tested on a synthetic file in the common layout; real exports vary and need field testing |
| Windows named pipe client | Verified on Windows against a real Navisworks Manage 2026 (Claude Desktop through the connector) |
| Navisworks add-in (C#) | Verified on Navisworks Manage 2026 (net48): connection, test listing, extraction and analysis of a real 654-clash model; `clash.apply` (status, grouping) and `doc.save` (save_as) verified by re-reading the document; `clash.run` re-ran a test; `model.census`/`elements.query` returned 3798 real elements, 749 of them grouped by level; `clash.image` wrote a 1.13 MB PNG matching the native Clash Detective render |
| Saved viewpoints, sleeve and embedded-conduit rules, beam passage from oriented boxes | Confirmed on one real model: on it, critical 35 to 15 and electrical x structure critical 15 to 2; thresholds are defaults, not a code |
| Scoring weights and bands | Reasonable defaults, calibrated only on the sleeve, conduit and beam-passage components of one real model |

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, the analysis pipeline, design decisions
- [docs/PROTOCOL.md](docs/PROTOCOL.md): wire protocol between server and add-in
- [docs/TOOLS.md](docs/TOOLS.md): tool reference
- [docs/ROADMAP.md](docs/ROADMAP.md): what is next
- [addin/README.md](addin/README.md): building and installing the add-in

## License

MIT, see [LICENSE](LICENSE).
