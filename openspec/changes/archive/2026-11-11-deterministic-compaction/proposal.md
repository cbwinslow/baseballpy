# Proposal: compaction is deterministic

## Why

AGENTS.md section 15 says the same inputs must give the same outputs for every user. Compaction is the
one step that rewrites files after a download, so two users who downloaded the same chunks in a different
order (different thread timing), or who compacted at different times, must not end with different data.
Task B-411 asked for a test that compares two runs byte for byte.

## What

- Tests (`tests/test_compact_deterministic.py`): the same chunks put into two lakes in opposite order give
  byte-identical compacted files; a rerun rewrites nothing; compacting in two stages gives the same rows as
  compacting once.
- Measured result (2026-11-11): all three already hold on the current code (sorted chunk keys, fixed codec
  and row-group size, no timestamp in the file). So this change adds the guards and states the rule:
  **the bytes depend only on the chunks compacted in one run; the grouping into files depends on when
  compaction ran (a later compaction does not merge old compacted files); the rows a user queries do not.**
  `AGENTS.md` section 15 rule 1 is reworded to say exactly that, and `response-log-segments` (one write per
  season) is what makes the file grouping canonical too.
- One requirement and scenarios in `lake-access`, one ADR.

## Out of scope

Making the grouping independent of history (re-merging compacted files): `response-log-segments` removes
the need (a season is written once).
