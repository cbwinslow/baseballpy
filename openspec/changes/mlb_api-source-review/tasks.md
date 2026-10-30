# Tasks: mlb_api-source-review

Cards with steps and files: `docs/agents/tracks/05-mlb_api.md` (card M-0N is the Nth task below).
Findings of the review become tasks `5.n` (with cards) before the tests and verification tasks run.

- [x] 1. Review (look and report; no code changes)
  - [x] 1.1 Inventory the provider against the registry (M-01)
  - [x] 1.2 Check registry and adapter conformance (M-02)
  - [x] 1.3 Compare the generated schema with real data (M-03)
  - [x] 1.4 Review the code against the designated tools and decoupling rules (M-04)
- [ ] 5. Fixes (the standard ones first, then one task per finding of the review)
  - [x] 5.1 Record upstream fingerprints for every raw file (M-05)
  - [x] 5.2 Decide currency with is_current() at every cache tier (M-06)
  - [x] 5.3 Keep the provider's documentation files (M-07)
  - [x] 5.4 Review the second way in (user-supplied files); N/A if the source has none (M-08) <!-- N/A: the MLB Stats API has no import path -->
  - [x] 5.5 Make every dataset and column reachable from Python (M-09)
  - [x] 5.6 No hard-coded default season; standings honour refresh (M-15)
  - [x] 5.7 One refused request must not abort the season job: ingest the rest, fail the job at the end with detail (M-16)
  - [x] 5.8 Registered keys unique on real rows: extend the keys of players_season, schedule_hydrated, per-game team stats and league leaders; ref_metrics by metric id (M-17)
  - [x] 5.9 `--datasets` accepts any registered dataset name, not only the five units (M-18)
  - [x] 5.10 Empty text is NULL (CSV round trip); the declarative MLB datasets get parser revision 1 (M-19)
  - [ ] 5.11 Remaining non-unique keys: transactions_season (one id covers several people, person_id has NULLs), repeated provider rows in leaders, coaches and jobs, draft_prospects NULL key part (M-20)
  - [ ] 5.12 team_stats_expected_statistics_hitting: each request returns one row holding the whole player list as JSON (flattening/records path), 579 identical rows of 600 (M-21)
  - [x] 5.13 League-wide pools survive the provider's 406: fetch the same splits through people hydrate in batches (M-22)
  - [x] 5.14 `baseballpy probe`: ten-second canary check of every provider route (M-23)

- [ ] 2. Tests
  - [ ] 2.1 Close the spec and test gaps (M-10)
- [ ] 3. Verify
  - [ ] 3.1 Live verification on a clean scratch home (M-11)
  - [ ] 3.2 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (M-12)
  - [ ] 3.3 Cited column descriptions (M-13)
- [ ] 4. Close
  - [ ] 4.1 Docs, decisions, spec merge, archive (M-14)
