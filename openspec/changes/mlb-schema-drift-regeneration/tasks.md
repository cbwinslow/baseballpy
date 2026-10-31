# Tasks: mlb-schema-drift-regeneration

Order: 1.1 -> 1.2 -> 1.3 -> 1.4.

## 1. Generate from the fallback

- [ ] 1.1 `sources/mlb_api/generic.py`: one public `hydrate_request_params()` used by
  `_pool_pages_by_hydrate` and by the generator; `scripts/gen_mlb_schemas.py`: sample a refused
  `v1/stats` pool through the hydrate route (`hydrate_sample()`), and record `"route"`/`"fallback_pages"`
  in the probe entry.
  Done when the runtime tests for the fallback still pass unchanged and the generator maps the direct
  refusal to a hydrate sample.

- [ ] 1.2 Regenerate the ten `stats_stat_splits_*` datasets (`mlb_tables.py`, fixtures,
  `docs/mlb_probe.json` with `--only ... --skip-combos`); `gameType`, `numTeams` and `sport.abbreviation`
  are typed columns.
  Done when the generated file carries `game_type`, `num_teams` and `sport_abbreviation` for every split
  pool and the probe entries say `route: hydrate`.

- [ ] 1.3 `tests/test_mlb_coverage.py`: every flattened key of a committed fixture has a typed column.
  Done when the test passes for all endpoints with a schema.

## 2. Close the change

- [ ] 1.4 Docs (`docs/sources/mlb_api.md` generation note), spec merge, BACKLOG rows, gates, archive.
  Done when `openspec validate --specs`, `docs generate --check`, `pytest`, `ruff`, `mypy` are green and
  the change is under `openspec/changes/archive/<date>-mlb-schema-drift-regeneration/`.
