# Change: Lahman Database Ingestion and Modern Chadwick Register Shards

## Why
1. **Chadwick Register Upstream Sharding:**
   - The upstream Chadwick Bureau repository (`chadwickbureau/register`) deprecated and removed the monolithic `data/people.csv` (now returning HTTP 404).
   - The register is now partitioned across 16 hexadecimal shards (`data/people-0.csv` through `data/people-f.csv`), plus auxiliary files: `names.csv` (nicknames, birth names, and alternate spellings), `links.csv` (external identifiers and URLs), and `countries.csv`.
   - `baseballpy` needs an extractor that fetches all 16 shards in parallel, validates commit hash / ETags to detect upstream weekly updates automatically, compiles the shards into a single unified master `pa.Table` / Parquet cache (`~/.baseballpy/cache/chadwick/people.parquet`), and provides an enhanced `ChadwickPlayerCrosswalk` resolver with nickname resolution, fuzzy matching, and typed enums (`PlayerIdType`).

2. **Lahman Baseball Database Modernization (1871–2025):**
   - The legacy `chadwickbureau/baseballdatabank` repository is dead/archived and stops at 2021.
   - The official SABR / Sean Lahman website distributes data via a Box.com download page (`sabr.app.box.com`), which uses ephemeral session tokens and breaks automated network extraction.
   - We will support a resilient dual-mode strategy:
     - **Mode A (Automated Ingestion):** Download directly from the up-to-date, public GitHub mirror `cbwinslow/lahman-database-csv` (containing the complete 1871–2025 SABR release with all 27 tables) with atomic `.part` writing, token-bucket rate limiting, and Parquet caching.
     - **Mode B (Manual Archive Import):** Provide an intuitive helper function `lahman.import_archive(path)` that takes a local zip or extracted folder downloaded by the user from SABR Box, verifies the CSV files, moves/copies them into the local cache directory `~/.baseballpy/cache/lahman/raw/`, and immediately compiles them into strongly-typed Parquet files in `~/.baseballpy/cache/lahman/processed/`.
   - Provide high-level table accessor functions: `batting()`, `pitching()`, `people()`, `teams()`, `fielding()`, `allstar()`, `hall_of_fame()`, `salaries()`, etc., reading zero-copy from the local Parquet cache with optional zero-copy handoffs to DuckDB and Polars.
   - Introduce type-safe Enums: `PlayerIdType` and `LahmanTable`.

## Scope
- Implement `baseballpy.sources.chadwick` multi-shard extractor, commit SHA tracking, nickname resolver, and enums.
- Implement `baseballpy.sources.lahman` extractor, normalizer, table accessors, local import helper, and enums.
- Author exhaustive specifications in `docs/sources/lahman.md` and update `docs/sources/chadwick.md`.
- Record Architecture Decision Record 19 in `docs/DECISIONS.md`.
- Author tests in `tests/test_chadwick.py` and `tests/test_lahman.py`.
- Verify 100% strict mypy and zero ruff errors.
