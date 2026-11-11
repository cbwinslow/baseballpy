# Tasks: deterministic-compaction

- [x] 1.1 Tests: `tests/test_compact_deterministic.py` (byte-identical files for another download order; rerun
  rewrites nothing; staged compaction gives the same rows). Done when the three pass and a sabotaged compact
  (unsorted keys) makes the first fail.
- [x] 1.2 Records: `lake-access` requirement, ADR 104, reword AGENTS.md section 15 rule 1, close B-411.
  Done when `docs generate --check` and `openspec validate --specs` pass.
- [x] 1.3 Gates, archive and commit.
