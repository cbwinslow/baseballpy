# Tasks: retrosheet-source-review

Cards with steps and files: `docs/agents/tracks/03-retrosheet.md` (card R-0N is the Nth task below).
Findings of the review become tasks `5.n` (with cards) before the tests and verification tasks run.

- [ ] 1. Review (look and report; no code changes)
  - [ ] 1.1 Inventory the provider against the registry (R-01)
  - [ ] 1.2 Check registry and adapter conformance (R-02)
  - [ ] 1.3 Compare the generated schema with real data (R-03)
  - [ ] 1.4 Review the code against the designated tools and decoupling rules (R-04)
- [x] 5. Fixes (the standard ones first, then one task per finding of the review)
  - [x] 5.1 Record upstream fingerprints for every raw file (R-05)
  - [x] 5.2 Decide currency with is_current() at every cache tier (R-06)
  - [x] 5.3 Keep the provider's documentation files (R-07)
  - [x] 5.4 Review the second way in (user-supplied files); N/A if the source has none (R-08) <!-- N/A: Retrosheet has no import path; every file comes from the pinned tree or a local checkout of it -->
  - [x] 5.5 Make every dataset and column reachable from Python (R-09)
  - [x] 5.6 Store every event field chadwickpy emits and key events on (GAME_ID, EVENT_ID) (R-15)
  - [x] 5.7 One declarative dataset-to-producer map: every registry name works with --datasets, one download per ingest (R-16)
  - [x] 5.8 No silent loss in game logs and rosters: quarantine short rows, keep extra fields in _extras (R-17)
  - [x] 5.9 Box parser: keep repeated info keys, safe dates, BoxParseError for bad numbers (R-18)
  - [x] 5.10 Shared stores: an empty rebuild removes the stale Parquet; stale .part files cleaned in processed/; quarantine follows the source's lake (R-19)
  - [x] 5.11 Export streams one season at a time (R-20)
  - [x] 5.12 Really stream box scores and box accounts; count rows without re-reading Parquet (R-21)
  - [x] 5.13 Data-quality checks across datasets, shown by catalog status (R-22)
  - [x] 5.14 boxscores_batting has no unique key: a player who re-enters in the same slot gets two rows (R-23)
  - [x] 5.15 Audit-log and time every Retrosheet operation (tree listing, file download, documents, unit build, quality check, season and reference ingest) (R-24)
  - [x] 5.16 rosters key is not unique: the all-star rosters repeat club lines; add a roster column (R-25)
  - [x] 5.17 substitutions key is not unique: a player who changes position in one stoppage gets two rows; add SUB_FLD_CD to the key (R-26)
  - [x] 5.18 box_starters key is not unique: a two-way player is listed twice in a lineup; add position to the key (R-27)
- [ ] 2. Tests
  - [ ] 2.1 Close the spec and test gaps (R-10)
- [ ] 3. Verify
  - [ ] 3.1 Live verification on a clean scratch home (R-11)
  - [ ] 3.2 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (R-12)
  - [ ] 3.3 Cited column descriptions (R-13)
  - [x] 3.4 Processed chunks are not rebuilt when the parser or schema changes (R-28)
- [ ] 4. Close
  - [ ] 4.1 Docs, decisions, spec merge, archive (R-14)
