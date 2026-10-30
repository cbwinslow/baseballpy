# Proposal: reference documentation for the tools and the comparison projects

## Why
The owner asked (2026-10-29) for the documentation of every dependency (dlt, pyarrow, polars, duckdb, narwhals, msgspec, httpx, pydantic, tenacity, aiolimiter, rich, click, respx, hypothesis, pytest) and of the projects baseballpy is measured against (pybaseball, baseballr, baseball.computer, MLB-StatsAPI) to be gathered, with complete copies kept, so endpoint and type decisions are checked against real documentation instead of memory.

## What
`scripts/fetch_reference_docs.py` saves Context7 excerpts (REST API, about 500 KB cap per response, several topic queries for the key libraries) into `docs/references/*.txt`; `scripts/clone_reference_docs.sh` keeps complete shallow clones of the projects' own repositories on the homelab (outside the repository because of size); `docs/references/README.md` indexes both with commits and sizes.

## Out of scope
Rewriting `docs/sources/*` (the endpoint and column dictionaries stay generated from live probes; the references are for cross-checking them).
