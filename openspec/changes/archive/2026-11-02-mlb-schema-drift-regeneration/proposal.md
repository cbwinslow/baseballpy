# Proposal: Regenerate the typed schemas through the hydrate fallback

## Why

The 2026-10-31 live proof of the split pools (B-187) found that a hydrate split object carries three
fields the generated schema does not type: `gameType`, `numTeams` and `sport.abbreviation`. In one
sampled page (150 players, 9,421 splits) they appear on 9,421, 526 and 9,421 rows respectively. The
schemas were generated when the direct `/v1/stats` route still answered, and that payload omits them, so
at runtime the normalizer keeps them as JSON in `_extras`: the data is preserved but untyped (no column,
no type, no filter).

The direct route has answered HTTP 406 since 2026-10-29 (B-30/B-32). Regenerating the schemas the old
way now yields no sample at all, so the generator must use the same route the runtime fallback uses
(`/v1/people?hydrate=stats(...)`), not hand-edited columns.

## What

- One public helper in `sources/mlb_api/generic.py` for the hydrate wire form, used by both the runtime
  fallback and the generator (no duplicated expression building).
- `scripts/gen_mlb_schemas.py`: when a `v1/stats` request is refused by the provider, sample the pool
  through the hydrate route instead, and record in the probe entry which route produced the sample.
- Regenerate `stats_stat_splits_*` (ten datasets): `mlb_tables.py`, `docs/mlb_probe.json` and their
  fixtures. `gameType`, `numTeams` and `sport.abbreviation` become typed columns.
- A test that every flattened key of a committed fixture has a typed column, so a silently untyped
  field (the `_extras` path) fails the suite.
- Docs: a note in `docs/sources/mlb_api.md` (generation) and the spec requirement.

## Out of scope

- The single-season family (`stats_stats_single_season_*`): it has no person equivalent and stays blocked
  (B-191).
- Changing what the runtime stores; `_extras` stays the safety net for fields the schema does not know.
- A parser revision bump: the stored chunk digest already includes the schema fingerprint, so a widened
  schema makes every old part stale (`core/stores.py::spec_fingerprint`).
