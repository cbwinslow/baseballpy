# Work breakdown: how the project is partitioned for AI agents

Read with `docs/agents/PROJECT_MAP.md` (what exists), `docs/agents/BACKLOG.md` (the ordered queue)
and `docs/agents/TOOLING.md` (the tools every task must use). This file is the method: it says how
the whole project is cut into pieces small enough to hand to one agent in one sitting.

## 1. How the project works (one paragraph per layer)

1. **Sources** (`sources/<source>/`) know one provider each: where its files and endpoints are, how to
   fetch them politely, and how to turn the payload into Arrow tables with strict schemas. They meet
   the rest of the code only through `ingest.IngestAdapter` (`source`, `all_seasons`, `plan`, `run`).
2. **Registry** (`core/datasets.py`, `sources/catalog.py::register_all()`): every dataset is one
   `DatasetSpec` (schema, partition, keys, view, doc anchor, ingest mode). Views, docs, status, audit
   and tests iterate the registry; nothing else names a dataset.
3. **Ingest** (`ingest/`): `plan_jobs` turns a selection into jobs, `run_jobs` runs them with bounded
   concurrency and writes one audit event each. The CLI and `backfill` sit on top and never import a
   concrete source.
4. **Lake** (`core/stores.py`, `core/atomic.py`, `core/layout.py`): `raw/` keeps upstream bytes with a
   sha256 manifest, `processed/` keeps zstd Parquet, `quarantine/` keeps cells that failed coercion,
   `databases/baseball.duckdb` holds views only.
5. **Sinks** (`sinks/`, `SinkProtocol`): Arrow in, destination out (Parquet, DuckDB, Polars, dlt
   warehouses). A CSV sink does not exist yet (gap, see BACKLOG B-43).
6. **Docs and specs**: OpenSpec specs are behavior, ADRs are reasons, `docs/sources/<source>.md` are
   per-provider references with generated column dictionaries. Tests cite scenarios.

## 2. The partition (recursive)

```text
Program: a typed, complete, documented baseball lake from five providers
├── Track 0  Rails            (agent rules, tooling table, task-card format, enforcement tests)
├── Track 1  Chadwick         (ID crosswalk; smallest; everything else joins on it)   <- start here
├── Track 2  Lahman           (27 tables, user-supplied or cbwinslow mirror only)
├── Track 3  Retrosheet       (event files via chadwickpy, game logs, box accounts)
├── Track 4  Statcast         (pitches, minors, leaderboards, game feed)
├── Track 5  MLB Stats API    (364 endpoints, live stream; largest)
└── Track 6  Cross-cutting    (export sinks incl. CSV, dlt role B-43, backfill, release, docs site)
    each source track = the same seven stages S1..S7 (section 3)
        each stage = task cards (section 4)
            a card that fails the atomic test (section 4) is split into smaller cards
```

Source order follows `EXECUTION_ORDER.md` (smallest to largest) and the dependency in `AGENTS.md`
section 3A: all player resolution goes through Chadwick, so Chadwick is finished and trusted first.
One source is open at a time; its change is `<source>-source-review`; a source track ends when its
change is archived. The owner picks the next source.

## 3. The seven stages every source goes through (identical for all sources)

| Stage | Question it answers | Output |
|---|---|---|
| S1 Inventory | What does the provider offer, and what do we register? | inventory table (every URL, file, endpoint, parameter, column group) vs registry, gaps listed; `unsupported` verdicts re-verified |
| S2 Conformance | Is the source registry- and adapter-driven, with no hard-coded dataset names? | adapter plans every registered dataset; CLI `--datasets` accepts exactly the registry; special cases removed or justified |
| S3 Schema and types | Do the typed columns match real data? | generated schema compared with a live sample; sentinels, nulls and era quirks recorded; `_extras` and drift behavior checked |
| S4 Code review | Does the code use the designated tools and stay decoupled? | per module: migrate to the tool in `TOOLING.md` or record what it cannot do; error handling, atomic writes, rate limits checked against `AGENTS.md` |
| S5 Tests and traceability | Does every requirement have a scenario and a mocked test? | missing scenarios and tests added; fixtures recorded; property tests where parsing is lossy |
| S6 Live verification | Does it work against the real provider? | small live run into a scratch `BASEBALLPY_HOME` (homelab if large), counts from `audit.jsonl`, spot-checked facts |
| S7 Docs, export, close | Can a user find, read and export the data? | `docs/sources/<source>.md` current, column descriptions, export through each sink checked, ADRs, spec delta merged, change archived |

## 4. The task card (the unit handed to an agent)

A card is **atomic** when all of these hold; otherwise split it:

- one concern, one module or one document (at most about 150 changed lines of code, or one doc page);
- every file it may touch is listed, and a different card never needs the same file at the same time;
- its *Done when* is a command whose output proves it (a named test, a CLI call, a diff check);
- it needs no decision the owner has not already made (otherwise it is an OWNER card);
- an agent that has read only the card, `AGENTS.md` and the listed files can finish it.

Cards live in `docs/agents/tracks/<NN>-<source>.md` and mirror the tasks of the source's OpenSpec change
one to one (the task number is the card number). Format (enforced by `tests/test_agent_rails.py`):

```markdown
### C-03 Short imperative title
- **Change task:** `chadwick-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude | agy (Claude reviews the full diff) | OWNER
- **Files:** exact paths it may touch (and "must not touch" if relevant)
- **Tools (reuse check):** the TOOLING.md rows that apply and what each is used for
- **Inputs:** facts it must not guess, with their source (spec, probe JSON, reference excerpt)
- **Steps:** numbered, small
- **Done when:** command(s) and expected result
- **Record:** which tasks.md box, design.md section, ADR or spec delta to update
```

Executor rule: Claude takes anything needing live probes, judgement about upstream behavior, schema or
`unsupported` decisions, OpenSpec/ADR writing and the final review. `agy` takes well-specified code,
tests, fixtures and mechanical edits (`AGY_DELEGATION.md`). OWNER cards wait for the owner and never
block other cards.

## 5. Working a card (the short loop; the full loop is `GOAL_SEEK_PROMPT.md`)

1. Read the card, `AGENTS.md` section 14, `TOOLING.md`, and only the files listed.
2. Write the reuse-check answers into the commit body draft.
3. Do the steps; tests first or alongside; the real network is never used in unit tests.
4. Run the gates (`pytest`, `ruff check`, `ruff format --check`, `mypy --strict src`, `docs generate --check`,
   `openspec validate --specs`, `project_map.py --check`).
5. Tick the task, write evidence in the change's `design.md`, update `BACKLOG.md`, commit once,
   conventional message, never push.

## 6. Cross-cutting tracks (not yet cut into cards)

- **Track 6a Export sinks:** a registry-driven `--format parquet|csv|duckdb|polars|postgres --out PATH`
  over `SinkProtocol` (BACKLOG B-43 redesign; needs the owner brainstorm first).
- **Track 6b MLB 406 and deep pools:** BACKLOG B-30..B-36 (external block).
- **Track 6c Backfill and release:** B-09, B-10, B-38 (owner decisions), `docs/RELEASING.md`.
- **Track 6d Doc drift:** `EXECUTION_ORDER.md` is partly stale, `openspec/project.md` names modules that
  do not exist (`baseballpy.extract`, `.parse`, `.sink`), BACKLOG had a duplicated row; fixed under
  `project-replan-and-agent-rails` tasks 3.x.

Each becomes cards when its turn comes; do not cut cards for work whose design is undecided.
