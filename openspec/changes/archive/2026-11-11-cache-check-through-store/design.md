# Design: cache-check-through-store

## 1. Evidence (2026-11-11)

- `grep part_path(` over `src/`: the MLB generic path and Retrosheet's `_current` use `has_part`/`is_cached`
  (compaction-safe). Statcast pitches `_is_chunk_fresh` (line 265: `rows > 0 and not cache_path.exists()` means
  "not fresh") and `_fetch_chunk` (line 332: `pq.read_table(cache_path, ...)`) use the plain file only.
- `core/stores.py::has_part` -> `holds_chunk` (compacted.py): the compacted file exists and its footer chunk
  map lists the key; `read_part` reads from the part or from the compacted file and retries if a refresh moves
  the chunk.
- A chunk the records call COMPLETED whose compacted file lacks it is already "not stored" for `has_part`
  (a store-level test pins this).

## 2. Reuse check (TOOLING.md)

No new tool or helper: `ProcessedStore.has_part` and `read_part` already exist; the fix deletes a private
file-name check and calls them. Registry/data-driven: no dataset names added.

## 3. Decision

- `_is_chunk_fresh` takes the spec and chunk instead of `cache_path` and asks `store.has_part`.
- A cache hit reads `store.read_part(spec, chunk_id, season)` cast to `spec.schema`.
- Rejected: teaching `_get_cache_path` about compacted files (a second copy of the logic in the store).

## 4. Tests

`tests/test_cache_through_store.py` (Statcast, three 5-day windows, the existing `_by_window` mock):
1. after `compact_dataset`, `ingest_season` again: `cached_chunks == 3`, no new request, same rows;
2. the compacted file is removed: the three windows download again and the rows equal the first run;
3. store level: a chunk whose compacted file lacks it is not cached (`is_cached` False).

## 5. As built

- `sources/statcast/extractor.py`: `_get_cache_path` removed; `_is_chunk_fresh(chunk_id, start_dt, end_dt, refresh,
  minors)` asks `store.has_part`; a cache hit reads `store.read_part` (cast to the spec schema if needed).
- Tests: `tests/test_cache_through_store.py` (3). Before the fix `test_a_compacted_statcast_season_is_served_from_the_lake`
  failed with `cached_chunks == 0` (3 expected); the other two already held and stay as guards.
- Statcast suites (106 tests) pass. Gates: see the commit.

## 6. Gate evidence (2026-11-11)

pytest 1629 passed, 6 skipped; ruff check clean; ruff format 759 files already formatted; mypy --strict no issues
in 180 files; docs generate --check up to date; openspec validate --specs 22 passed.
