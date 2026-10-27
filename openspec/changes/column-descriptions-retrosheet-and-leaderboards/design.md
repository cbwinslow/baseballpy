# Design: Retrosheet and Leaderboard Column Descriptions

Reuses the mechanism of ADR 34 unchanged: `docs/columns/<source>.json` with a `_sources` map, `scripts/build_column_descriptions.py` as the deterministic builder, `docs coverage` ratchet.

- Retrosheet: AGENTS.md section 4 forbids bulk extraction from retrosheet.org; reading a handful of format documents is not bulk, but the host refused connections on 2026-10-27. Alternatives to try before giving up: the documents shipped in the `chadwickbureau/retrosheet` mirror (raw.githubusercontent.com), then retry the host later. Never invent field names (see `retrosheet-box-accounts`).
- Leaderboards: cite the provider's own column definitions only; anything else stays `TODO`.
