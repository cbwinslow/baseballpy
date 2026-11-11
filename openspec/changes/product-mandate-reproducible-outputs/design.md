# Design: product-mandate-reproducible-outputs

## 1. Evidence (2026-11-11)

- `grep -i "pypi|reproduc|deterministic|consistent|same results|redistribut"` over `AGENTS.md`,
  `CLAUDE.md`, `openspec/project.md`, `README.md`: no match. The contract describes mandates for
  ingestion, specs and agents but not the purpose of the product or the sameness of outputs.
- Session record: the MLB 2019 damage (two compactions at once) was repaired by moving files and
  re-running the ingest; the code fix (`compact-one-writer`) came after the owner asked. The queue
  still marks stages "done" after failed after-steps (`.baseballpy/state/queue.json`: 2018 to 2021).
- Rebuild evidence that this approach works: after the 2019 refill the table held 225,837 rows, exactly
  the records' `records_count` sum, 2,965 games, 0 duplicates on the registered key.

## 2. Decisions

- The product is the library and its workflows. The lake of one machine is an oracle for tests, never the
  deliverable. Data is reproducible, workflows are not replaceable.
- Fix order for a data defect: (1) find the code path that produced it, (2) write a test that fails,
  (3) fix the code, (4) rebuild the data with the workflow and compare with the old output, (5) only then
  delete or replace files. Hand edits of files are a last resort, recorded in the change and followed by
  a rebuild.
- "Same results" is defined as: for pinned inputs (git SHAs, a closed season, a fixed date window) the
  same rows, schema, record counts, chunk and file names and compacted-file bytes on every machine and
  run. Live inputs (Statcast, the MLB API) are not pinned by the provider: they are made repeatable by
  keeping every response (raw) and by deterministic processing of it, so a rebuild from raw is
  identical.
- Both history (bulk, resumable) and live (real-time) workflows are in scope; both write through the same
  typed Parquet layout and views, so DuckDB, PyArrow, Polars, pandas, Parquet, CSV and PostgreSQL users see
  the same tables.

## 3. Prior art / reuse check

Documentation only; no tool applies. Compared with pybaseball (no lake, no guarantees) and dlt (pinned
state per pipeline): the project keeps pinned upstream refs (`core/sources_lock.json`) and manifests
already; this change makes the rule explicit and testable.

## 4. Tests

`tests/test_agent_rails.py::test_the_contract_states_the_product_and_reproducibility_mandate` reads
`AGENTS.md`, `CLAUDE.md` and `openspec/project.md` for the section titles and key rules.

## 5. As built

- `AGENTS.md` sections 0 and 15 and rule 14.2.10; `CLAUDE.md` (mission section, hard rule 5);
  `openspec/project.md`; `README.md`; ADR 100; requirement in `agent-runbooks`.
- Test `tests/test_agent_rails.py::test_the_contract_states_the_product_and_reproducibility_mandate`
  failed before the text and passes after.
- Gates (2026-11-11): pytest 1625 passed, 6 skipped; ruff check clean; ruff format --check 751 files
  already formatted; mypy --strict no issues in 180 files; docs generate --check up to date;
  openspec validate --specs 22 passed.
- The change stays open (not archived) because the follow-up tasks 2.1 to 2.5 are mapped in it; each opens
  its own change when started.
