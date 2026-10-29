# Tasks: chadwick-source-review

Cards with steps and files: `docs/agents/tracks/01-chadwick.md` (card C-0N = the task below).

- [x] 1. Review
  - [x] 1.1 Inventory the upstream repository against the registry (C-01)
  - [x] 1.2 Verify and fix adapter conformance, no hard-coded dataset names (C-02): defect confirmed, the fix is 5.1 and 5.2
  - [x] 1.3 Compare the generated schema with real data (C-03)
  - [x] 1.4 Review the code against the designated tools and decoupling rules (C-04)
- [ ] 5. Fixes found by the review
  - [x] 5.1 Split ingest (extract, normalize, store) from the lookup index (C-09)
  - [x] 5.2 Registry-driven adapter: one job per registered dataset, per-dataset row counts (C-10)
  - [x] 5.3 `resolve_id` through an explicit column map for all nine id types, both directions (C-11)
  - [ ] 5.4 Vectorised lookup index, duplicate-id guard, correct `PlayerRecord` types (C-12)
  - [ ] 5.5 Data-driven nicknames and vectorised name search (C-13, needs the owner's OK)
  - [x] 5.6 Keep the upstream README, correct spec and docs (C-14)
- [ ] 2. Tests
  - [ ] 2.1 Close the spec and test gaps (C-05)
- [ ] 3. Verify
  - [ ] 3.1 Live verification on a scratch home (C-06)
  - [ ] 3.2 Check export through every existing sink (C-07)
- [ ] 4. Close
  - [ ] 4.1 Docs, ADRs, spec merge, archive (C-08)
