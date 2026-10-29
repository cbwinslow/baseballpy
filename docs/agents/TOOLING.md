# Designated tools: use these before writing code

Every AI agent working on `baseballpy` MUST answer the **reuse check** below before it writes a
helper, a parser, a loop over rows or a new module. A new hand-written utility that duplicates
something a designated tool does is a defect, even if its tests pass. This file is binding
(`AGENTS.md` section 14) and `tests/test_agent_rails.py` fails when a runtime dependency in
`pyproject.toml` is missing from the table.

## The reuse check (write the answers in the task card or commit body)

1. Which row of the table below covers what I am about to write?
2. Did I read the tool's reference excerpt (`docs/references/<tool>.txt`) or its Context7 docs?
3. If I still need custom code: what exactly can the tool not do? (One sentence, with evidence.)
4. Does a registry entry, a generator or a declarative table remove the special case I am about to
   write? (`AGENTS.md` section 13.)

## The table

| Need | Use | Notes / where it lives | Do not |
|---|---|---|---|
| HTTP, retries, rate limits, User-Agent | `httpx` + `tenacity` + `aiolimiter` through `core/http.py::HttpClient` | one client, per-host limits, HTTP/2 | import `httpx`, `requests`, `urllib.request` or `aiohttp` anywhere else; sleep/retry by hand |
| Typed tabular interchange | `pyarrow` (`pa.Table`, `RecordBatchReader`) | strict schemas, `safe=True` casts | pass `dict` rows or pandas frames between layers |
| CSV / JSON-lines / Parquet parsing | `pyarrow.csv`, `pyarrow.json`, `pyarrow.parquet`, or `polars.scan_*` | stream, project and cast in the engine | loop `csv.reader` rows in Python for bulk data |
| Large JSON payloads | `msgspec` (decode into `Struct`/typed dict) | `core/http.py`, `core/audit.py`, `stream.py` | `json.loads` on multi-MB responses in new code |
| Dataframe-agnostic code | `narwhals` | `frames.py`, register lookups | write the same logic twice for polars and pandas |
| Local analytics, views, SQL | `duckdb` (views over Parquet only) | `database.py`, `sinks/duckdb.py` | copy data into DuckDB tables; build SQL by string concatenation (use `core/sql.py`) |
| In-memory transforms, joins, group-by | `polars` (or Arrow compute) | lazy where possible | row loops, `iterrows`, hand-written group-by |
| Destinations beyond files (Postgres, BigQuery, Snowflake, MotherDuck) | `dlt` through `sinks/dlt.py` behind `SinkProtocol` | sources never import `dlt` | add a per-destination writer inside a source |
| Configuration | `pydantic` + `pydantic-settings` (`BASEBALLPY_*` env) | `core/config.py` | read `os.environ` ad hoc; hard-code paths |
| CLI and terminal output | `click` + `rich` | `cli*.py` | `print()` tables, `argparse` |
| Tests | `pytest`, `respx`, `hypothesis`, `pytest-socket` | fixtures in `tests/fixtures/` | touch the real network in unit tests; hand-roll HTTP mocks |
| Retrosheet event parsing | `chadwickpy` only inside `sources/retrosheet/_chadwick_adapter.py` | GPL boundary (ADR 26) | import it anywhere else; re-implement the parser |
| Packaging / env | `uv` only | `uv sync`, `uv run` | `pip install`, `python -m venv` |
| Lint / types | `ruff` (`uvx ruff`), `mypy --strict` (`uv run mypy`) | zero warnings | add `# type: ignore` or `noqa` without a written reason |
| Code delegation | `agy` via `scripts/agy_delegate.py` | `docs/agents/AGY_DELEGATION.md` | use Claude `Agent`/workflow subagents (owner rule) |

## Where the project does not yet follow this table (the review finds and fixes these)

Measured on 2026-10-29 from imports under `src/`: stdlib `csv` is used in 5 modules
(`retrosheet/parser.py`, `retrosheet/box_parser.py`, `statcast/lb_parse.py`, `core/schema_tools.py`,
`cli_db.py`), stdlib `json` in 22 modules while `msgspec` is used in 4, `narwhals` in 2, `polars` in
4. Each source review (`WORK_BREAKDOWN.md` stage S4) decides per module: migrate to the designated
tool, or record in the change's `design.md` what the tool cannot do. The count is evidence for the
review, not a defect list; do not rewrite working code without a task card.

## Adding a tool

A new runtime dependency needs an OpenSpec change, an ADR, a row in this table and a reference
excerpt in `docs/references/` (`scripts/fetch_reference_docs.py`). Remove a tool only the same way.
