# Proposal: the product mandate and reproducible outputs

## Why

The owner stated twice that `baseballpy` is a reusable Python library, to be published on PyPI, that
downloads, ingests and maintains MLB data (historical and live) for other people, and that every user
running the download workflows must get the same results. The contract (`AGENTS.md`, `CLAUDE.md`,
`openspec/project.md`) never says this: no search for PyPI, reproducibility or "same results" matches
any of them. In the 2026-11-11 session, agents spent most of their effort repairing data files by hand
(the 2019 MLB boxscore tables) instead of fixing the code that produced the damage and proving that a
fresh run gives the same output. The data on the owner's machine can be downloaded again; the
workflows cannot be replaced.

## What

1. **Contract text** (`AGENTS.md` new section 0 "Product mission" and new section 15 "Reproducible
   outputs", `CLAUDE.md`, `openspec/project.md`, `README.md`): the product is the code and its
   workflows, not the lake on one machine; the lake is a test oracle; a data defect is fixed in code
   with a test and the data is then produced again by the workflow (hand edits of data files are a last
   resort, written down and followed by a rebuild); outputs must be the same for every user and every
   run (pinned inputs, stable ordering, deterministic file names and bytes, no machine-specific
   values); supported ways to use the data (DuckDB, PyArrow, Polars, pandas, Parquet, CSV, PostgreSQL);
   historical and real-time are both in scope.
2. **A machine check**: `tests/test_agent_rails.py` fails if these statements are removed.
3. **Follow-up code tasks** (mapped, not built here): a rebuild check that runs a workflow into a
   scratch home and compares it with the lake; ingest re-fetches a chunk its compacted file lacks;
   the queue stops calling a stage "done" when its after-step failed; compaction output is
   deterministic; a determinism audit per source (Statcast is not pinned).
4. ADR 100 and a requirement in the `agent-runbooks` spec.

## Out of scope

Building the follow-up tools (each is its own task with its own tests), changing any dataset schema,
and the data repair tasks of `compact-one-writer` (2.2 to 2.4).
