# Tasks: Restructure the Data Lake

Prerequisite: `harden-ingestion-core` tasks 1-5 complete (HttpClient, manifest lock, atomic names).

- [ ] 1. LakeConfig (L-1, L-2) <!-- id: 1 -->
  - [ ] 1.1 Add `LakeConfig` to `core/config.py`; remove directory creation from property getters
  - [ ] 1.2 Keep `CacheConfig` as deprecated alias with `DeprecationWarning`; update all internal imports to `LakeConfig`
  - [ ] 1.3 Tests: env overrides, no mkdir on read, legacy `BASEBALLPY_CACHE_DIR` warning
- [ ] 2. Dataset registry (L-5, L-7) <!-- id: 2 -->
  - [ ] 2.1 Create `core/datasets.py` with `DatasetSpec` and empty `DATASETS`; sources register themselves (see `complete-source-coverage`)
  - [ ] 2.2 Test: every spec has schema, keys, view name, endpoint_doc anchor that exists in `docs/sources/*.md`
- [ ] 3. Raw/processed stores (L-2) <!-- id: 3 -->
  - [ ] 3.1 Implement `RawStore` and `ProcessedStore` (atomic, sha256, footer validation)
  - [ ] 3.2 `reprocess(spec, season)` re-parses from `raw/` offline
  - [ ] 3.3 Port Statcast, MLB API, leaderboards, Retrosheet, Lahman, Chadwick extractors to write both tiers (coordinate with coverage change tasks)
  - [ ] 3.4 Split Retrosheet `events` and `events_postseason` into separate datasets (L-4)
- [ ] 4. BaseballDatabase rewrite (L-3, L-4, L-5, L-6, L-7) <!-- id: 4 -->
  - [ ] 4.1 Registry-driven view creation with `quote_ident` and escaped paths
  - [ ] 4.2 Handle `season` hive column collision; add test
  - [ ] 4.3 Read-only behavior + `DatabaseReadOnlyError`
  - [ ] 4.4 Add `v_player_crosswalk`, `v_season_catalog`
  - [ ] 4.5 Tests: no leaderboard rows in pitches, no duplicate events, all registered datasets get views
- [ ] 5. Migration (L-9) <!-- id: 5 -->
  - [ ] 5.1 Implement `core/migrate.py` per design mapping table; `VERSION` file
  - [ ] 5.2 Synthetic v1-tree integration test incl. idempotency and `--dry-run`
  - [ ] 5.3 First-use detection hint (log once)
- [ ] 6. Pinned refs (L-8) <!-- id: 6 -->
  - [ ] 6.1 `core/sources_lock.py` + URL builders using refs; record `source_ref` in manifests
  - [ ] 6.2 `refs update` implementation (HttpClient, `GITHUB_TOKEN` support)
  - [ ] 6.3 Tests with respx
- [ ] 7. Cleanup <!-- id: 7 -->
  - [ ] 7.1 `git rm` `test.duckdb`, `test2.duckdb` if tracked; delete from disk
  - [ ] 7.2 Verify `.gitignore` covers `*.duckdb`, `*.part`, `__pycache__`
- [ ] 8. Verification <!-- id: 8 -->
  - [ ] 8.1 `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy --strict src`
  - [ ] 8.2 Manual: `baseballpy migrate-layout --dry-run` on real home dir, review output; run for real; `baseballpy db sync`; compare per-view row counts to pre-migration
  - [ ] 8.3 Manual: download one Statcast week + one Retrosheet season fresh into an empty `BASEBALLPY_HOME`, confirm tree matches the Target Layout exactly (`find` listing saved to `docs/examples/layout.txt`)
- [ ] 9. Docs <!-- id: 9 -->
  - [ ] 9.1 ADR 23; update `openspec/specs/caching-and-invalidation/spec.md` from deltas
  - [ ] 9.2 Layout section in README, QUICKSTART, every `docs/sources/*.md` (paths)
