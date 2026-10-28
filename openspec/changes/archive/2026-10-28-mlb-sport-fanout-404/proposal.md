# Change Proposal: Tolerate the provider's 404 for sports and teams without data (fan-out)

## Context & Motivation
Found by the first live run of `baseballpy ingest mlb_api -s 2023 -d season` (2026-10-27): `GET /v1/teams?sportId=31&season=2023` answers 404 `{"message":"Object not found"}` for seven listed sports (31, 32, 52, 61, 509, 510, 576), in 2023 and 2024 alike, and the job failed. The provider lists these sports in `/v1/sports` but has no teams for them. AGENTS section 11.4: a per-request 404 is tolerated only for endpoints that opt in, and is recorded and counted.

The same live run then failed on `GET /v1/teams/231/alumni` (team fan-out): teams the provider lists can also lack a resource.

## Proposed Changes
Non-paginated endpoints declared with a `{sport_id}` or `{team_id}` fan-out (`FAN_OUT_MARKERS`) opt in to `tolerate_missing` automatically (a declarative rule in `MlbEndpoint.__post_init__`, not a per-endpoint list), so every fanned endpoint behaves the same; the existing generic path records the 404 as an empty part and counts it in `EndpointReport.missing`.

## Out of Scope
Changing which sports are fanned out (the provider's own `/v1/sports` list stays the source).

## Impact
`endpoints.py` only; no schema change.
