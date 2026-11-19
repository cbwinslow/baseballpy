# Change Proposal: Chadwick Player Register & Master Crosswalk

## Why
Baseball data across Statcast, MLB Stats API, Retrosheet, Baseball-Reference, FanGraphs, and Lahman use conflicting player identifier schemes (`mlbam` vs `retro` vs `bbref` vs `fangraphs`).
A master player resolution system is required so that:
1. Users and models can look up players by any ID, slug, or name.
2. Ingestion pipelines can automatically enrich and crosswalk player IDs across disparate databases.
3. Downloads are cached locally as Parquet with Git commit SHA / ETag change checking, avoiding unnecessary network downloads.

## What Changes
1. Implement `baseballpy.sources.chadwick`:
   - `ChadwickExtractor`: Downloads `people.csv` from the official Chadwick Bureau GitHub mirror (`https://raw.githubusercontent.com/chadwickbureau/register/master/data/people.csv`). Checks GitHub commit SHA or remote ETag before downloading.
   - `ChadwickNormalizer`: Normalizes and validates the schema into a strongly-typed PyArrow table (`key_mlbam` as `int32`, `key_retro` as `string`, etc.).
   - `ChadwickRegister`: Ergonomic player registry class with indexing for instant O(1) lookups by MLBAM, Retrosheet, BBRef, FanGraphs, and fuzzy/exact name matching.
2. Top-level API exports:
   - `baseballpy.chadwick.register()`
   - `baseballpy.resolve_player(...)`
3. Comprehensive test suite with offline fixtures in `tests/test_chadwick.py`.
