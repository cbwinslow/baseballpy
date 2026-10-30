# Tasks: statcast-source-review

Cards with steps and files: `docs/agents/tracks/04-statcast.md` (card S-0N is the Nth task below).
Findings of the review become tasks `5.n` (with cards) before the tests and verification tasks run.

- [ ] 1. Review (look and report; no code changes)
  - [x] 1.1 Inventory the provider against the registry (S-01)
  - [x] 1.2 Check registry and adapter conformance (S-02)
  - [ ] 1.3 Compare the generated schema with real data (S-03)
  - [x] 1.4 Review the code against the designated tools and decoupling rules (S-04)
- [ ] 5. Fixes (the standard ones first, then one task per finding of the review)
  - [x] 5.1 Record upstream fingerprints for every raw file (S-05)
  - [x] 5.2 Decide currency with is_current() at every cache tier (S-06)
  - [ ] 5.3 Keep the provider's documentation files (S-07)
  - [ ] 5.4 Review the second way in (user-supplied files); N/A if the source has none (S-08)
  - [ ] 5.5 Make every dataset and column reachable from Python (S-09)
  - [x] 5.6 Audit-log and time the game-feed fetch and season ingest (S-15)
- [ ] 2. Tests
  - [ ] 2.1 Close the spec and test gaps (S-10)
- [ ] 3. Verify
  - [ ] 3.1 Live verification on a clean scratch home (S-11)
  - [ ] 3.2 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (S-12)
  - [ ] 3.3 Cited column descriptions (S-13)
- [ ] 4. Close
  - [ ] 4.1 Docs, decisions, spec merge, archive (S-14)
