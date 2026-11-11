# Proposal: define the final product, per source, in the constitution

## Why

The owner asked (2026-11-11) for a picture of the final product for all data sources, for everything known so far
to be in OpenSpec, and for the docs to be updated as the work goes on. What is known is spread over the change
`response-log-segments`, ADRs 95 to 106, the source pages and the session record; `openspec/project.md` (the
living constitution) still shows the old architecture picture and says FanGraphs and Baseball-Reference are
"planned, not implemented". There is no single place that says: for each source, what is downloaded, how it is
stored, how a user reads it, what proves it, and what is still to do.

## What

- `openspec/project.md` gets a section **The Final Product** (the per-source table, the target layout and the
  definition of done for the whole product) and loses its stale statements. No counts of datasets or rows (they
  change); the table says where to look (`baseballpy catalog list`).
- `openspec/changes/EXECUTION_ORDER.md` gets a **Road to v1** section: the ordered steps from today to the final
  layout, which are owner decisions, and what stays stopped until then (the download queue).
- ADR 107 records the decision made on 2026-11-11: keep all raw; rebuild processed data from raw into the final
  layout with the finished code; delete the old processed files only after the rebuild matches; the queue stays
  stopped until then.
- A test keeps the table in step with the registry (every source appears; every first command is real), and a
  requirement in `agent-runbooks` names it.

## Out of scope

Building any of the remaining steps (each has its own change or task); the deferred sources' contract tests (B-433).
