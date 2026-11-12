# Tasks: typing-gaps-retrosheet-statcast

- [x] 1.1 Tests first: `tests/test_typing_audit.py` (probe seasons from the data, audit finds typed text, empty season
  gives no type evidence). Done when they fail for the right reason.
- [x] 1.2 `scripts/gen_savant_schemas.py`: `probe_years` and `observed_type`; regenerate `lb_tables.py` and
  `docs/savant_probe.json` live. Done when the type diff is reviewed (no column lost).
- [x] 1.3 `scripts/audit_column_types.py` with reasons in `KNOWN_TEXT`. Done when it prints 0 without a reason.
- [x] 1.4 Retrosheet: `daily_splits` dates `date32`, `box_games.tiebreaker` `int16` (schema, parser, tests).
- [x] 1.5 Re-download the Statcast leaderboards and re-run the audit (Statcast clean).
- [x] 1.6 Rebuild Retrosheet `daily_splits` and `box_games` offline from raw and re-run the audit.
- [x] 1.7 Gates (pytest, ruff, format, mypy), `docs generate --check`, `openspec validate --specs`; spec merge, ADR,
  archive; commit.
