# Change Proposal: Fix the Findings of the First Catalog Audit

## Context & Motivation
`catalog-completeness-audit` (library + `baseballpy catalog audit`, implemented first because it was cheap and unblocked) was run against the live providers on 2026-10-27 and immediately found coverage gaps that no test had caught. Two of them are *wrong `unsupported` verdicts* recorded during `complete-source-coverage`, caused by probing with an extra parameter that breaks the route.

| ID | Finding | Evidence |
|----|---------|----------|
| F-1 | `active_spin` leaderboard marked unsupported | `GET /leaderboard/active-spin?year=2024&csv=true` returns 708 CSV rows (562 for 2020, 0 for 2019); the earlier probe added `min=q`, which turns the answer into HTML. |
| F-2 | `catch_probability` marked unsupported | `GET /leaderboard/catch_probability?year=2024&min=0&csv=true` returns 301 rows; the earlier probe added `type=Fielder`, which empties the result. (The earlier anonymous rows also came from that parameter.) |
| F-3 | Roster types `allTime`, `coach`, `gameday` missing | `/v1/rosterTypes` lists them; `/v1/teams/147/roster?rosterType=...&season=2024` returns 1,854 / 11 / 42 rows. |
| F-4 | Standings type `currentHalf` missing | `/v1/standingsTypes` lists it; `/v1/standings?standingsTypes=currentHalf` returns 30 team records. |
| F-5 | `GameType` enum has 5 of the 11 game types `/v1/gameTypes` lists (missing C, D, F, I, L, W) | audit MISSING findings. |
| F-6 | 30 stat types listed by `/v1/statTypes` returned no data in any generated combination (e.g. `statSplits`, `vsPlayer`, `vsTeam`, `tracking`, `metricLog`, `projected_Zips*`) | audit NO_DATA findings; they need extra parameters (`sitCodes`, `opposingPlayerId`, `opposingTeamId`, `metrics`, ...). |

## Proposed Changes
1. F-1/F-2: register `leaderboard_active_spin` and `leaderboard_catch_probability` with the parameters that work; remove them from `unsupported`.
2. F-3/F-4: add the roster and standings types to the registry (`ROSTER_TYPES`, `STANDINGS_TYPES`) and regenerate their schemas and fixtures.
3. F-5: complete the `GameType` enum; the enum test becomes an equality check with `/v1/gameTypes`.
4. F-6: not fixed here; a follow-up change `mlb-parameterized-stat-types` is proposed (parameter discovery per stat type). The audit keeps reporting them as NO_DATA until then.
5. `audit` wiring: `unsupported` entries record `verified_on`/`tried` (done), the audit reports REVIVED automatically.

## Out of Scope
F-6 implementation; the weekly CI job (needs the CI workflows from `repo-hygiene-and-docs-sync`).

## Impact
Four more MLB datasets and two more Savant variants; the enum gains members. Recorded as ADR 37.
