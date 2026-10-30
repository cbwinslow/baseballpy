# Design: mlb-stats-route-406-and-deep-pools

## 1.1 Research (2026-10-30, standard web search)
Searched for how other clients handle HTTP 406 on `statsapi.mlb.com/api/v1/stats`. No issue, forum post or client documentation reports this status for that route; results were generic definitions of 406 (the server cannot produce a response matching the request's `Accept` headers), a community OpenAPI client that lists `GET /api/v1/stats` (parameter reference only) and unrelated clients. Reading: a 406 means the request is rejected on content negotiation or by a front-end rule, not for missing data. Our probes already varied the User-Agent (pybaseball's, a browser's) and the query (`playerPool`, `limit`, `sitCodes`); the `Accept` header is the one variable not yet recorded as tried (idea for the next retest: send `Accept: application/json` and `Accept: */*`, one request each).

## 1.2 Retest log (one request per hour at most; control `v1/teams`)
- 2026-10-29: 406 on league-wide `v1/stats` from this PC and the homelab; `v1/teams` and `v1/people/{id}/stats` answered 200.
- 2026-10-30: `v1/stats?stats=season&group=hitting&season=2025&sportIds=1&playerPool=ALL&limit=5` answered 406 again; control `v1/teams?sportId=1&season=2025` answered 200. Still open (B-32).

## 2.1 Generator guard (2026-10-30)
`scripts/gen_mlb_schemas.py`: `get_json` logs every provider error (403, 406, 429, 500, 502, 503, 504) with its status and remembers it in `PROVIDER_ERRORS`; `probe_param_combos` does not mark a stat type `unsupported` when a provider error occurred during its probe protocol; `write_combos` refuses to replace `stat_combos.py` with an empty league-wide player or team table. Tests: `tests/test_gen_mlb_keys.py::test_a_provider_error_is_logged_and_remembered_never_read_as_no_data`, `::test_an_empty_league_wide_table_is_never_written` (both fail without the change).
