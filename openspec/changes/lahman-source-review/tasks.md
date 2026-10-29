# Tasks: lahman-source-review

Cards with steps and files: `docs/agents/tracks/02-lahman.md` (card L-0N is the Nth task below).
Findings of the review become tasks `5.n` (with cards) before the tests and verification tasks run.

- [ ] 1. Review (look and report; no code changes)
  - [ ] 1.1 Inventory the provider against the registry (L-01)
  - [ ] 1.2 Check registry and adapter conformance (L-02)
  - [ ] 1.3 Compare the generated schema with real data (L-03)
  - [ ] 1.4 Review the code against the designated tools and decoupling rules (L-04)
- [ ] 5. Fixes (the standard ones first, then one task per finding of the review)
  - [ ] 5.1 Record upstream fingerprints for every raw file (L-05)
  - [ ] 5.2 Decide currency with is_current() at every cache tier (L-06)
  - [ ] 5.3 Keep the provider's documentation files (L-07)
  - [ ] 5.4 Review the second way in (user-supplied files); N/A if the source has none (L-08)
  - [ ] 5.5 Make every dataset and column reachable from Python (L-09)
- [ ] 2. Tests
  - [ ] 2.1 Close the spec and test gaps (L-10)
- [ ] 3. Verify
  - [ ] 3.1 Live verification on a clean scratch home (L-11)
  - [ ] 3.2 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (L-12)
  - [ ] 3.3 Cited column descriptions (L-13)
- [ ] 4. Close
  - [ ] 4.1 Docs, decisions, spec merge, archive (L-14)
