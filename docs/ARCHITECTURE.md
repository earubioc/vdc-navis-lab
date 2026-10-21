# Architecture

```
 MCP client (any LLM)
        | stdio
 navis_mcp.server      14 tools, thin wrappers, error mapping
        |
 navis_mcp.service     App: state, plans, jobs, snapshots
     |         |
 engine/      bridge/            exports, views, ingest, paths
 (pure)       client -> transport (pipe | tcp) -> add-in or simulator
```

## Layers

**Engine** (`engine/`) is pure Python with no I/O. Input is a `ClashSet` (clashes, tests, element metadata) and a `Profile`; output is an `AnalysisResult`. Everything is deterministic, so the same input and profile always give the same ranking.

Pipeline: tag, filter noise, cluster, measure crowding, score, find root causes, derive decisions, rank.

- **Tagging.** A model's discipline comes from its file name first and its categories second. The user can override per model, and an override re-tags the analysis in memory.
- **Noise.** A clash is noise when it is a designed opening (needs bounding-box containment, not just a name), shallow, a self-assembly, or already closed. Filtered clashes are counted by reason; a test whose results are all filtered is reported in coverage.
- **Clustering.** Union-find over element pairs, then single-linkage in a spatial hash per discipline pair, with a median bisect when a cluster exceeds the maximum span.
- **Scoring.** Six components (penetration, criticality, immovability, size, crowding, clearance), weights renormalised over the components that apply. Gates raise the priority floor for structural and fire pairs regardless of the score.
- **Causes.** `shared_element` (one element in many issues) and `repeated_detail` (same crossing across levels). Shared elements weigh more, because closing one removes several issues.
- **Decisions.** Issues grouped by cause so a single change is a single line in the work plan.

**Bridge** (`bridge/`) is how the server talks to Navisworks. One JSON-RPC request per connection over a Windows named pipe (loopback TCP for the simulator). Discovery looks for pipes named `navis-mcp.<pid>`; several instances can be open and writes refuse to guess between them.

**Service** (`service.py`) holds the session: the current analysis and which instance and revision it came from, saved plans, pending jobs. It is the only place that decides whether an analysis is stale.

**Server** (`server.py`) registers tools and converts failures into structured errors (`{"error": code, "detail": ..., "hint": ...}`).

## Writes

1. `nw_apply(ops=[...])` validates the operations against the current analysis, builds a plan, and returns a `plan_id`. Nothing changes.
2. `nw_apply(plan_id=..., dry_run=false)` executes only a stored plan, bound to the instance, document fingerprint and revision it was made for. Plans expire after 30 minutes and run once. The add-in receives the plan id as an idempotency key, so a retry cannot apply twice.
3. After the change, the add-in re-reads the document and the server reports the verified counts, not the requested ones.

An analysis becomes stale when the document revision changes for any reason other than our own verified write.

## Snapshots

A snapshot stores the issues of an analysis by the set of element pairs they contain. Comparing two snapshots uses Jaccard similarity of those sets and reports `new`, `persisting` and `absent`. An issue that disappears is `absent`, never `resolved`: it may have been fixed, filtered, closed, or simply not retested.

## Design decisions

- **Analysis outside Navisworks.** The Navisworks API is single-threaded and runs in-process, so heavy work there freezes the user's session. The add-in only extracts and applies; scoring happens in the server.
- **A profile file instead of code.** Criteria are data, validated on load, with a checksum shown in every report.
- **Few tools, rich results.** Fourteen tools with actions and filters, instead of dozens of narrow ones, keep the assistant's tool list small enough to choose from reliably.
- **Offline first.** Everything except live extraction and writes works from a file.
