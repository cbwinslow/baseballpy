# Change Proposal: Parameterized MLB Stat Types

## Context & Motivation
The first catalog audit (`catalog-audit-first-run-fixes`, finding F-6) reports 26 stat types listed by `/v1/statTypes` for which no generated combination returned data. They are valid provider offerings that need extra request parameters the generic stat sweep does not send. AGENTS.md section 3 and the standing owner rule forbid leaving provider data behind.

Stat types with no data today: `advanced`, `byDayOfWeekPlayoffs`, `byMonthPlayoffs`, `careerStatSplits`, `firstYearStats`, `gameTypeStats`, `homeAndAwayPlayoffs`, `lastYearStats`, `metricAverages`, `metricLog`, `projectedRos`, `projected_Zips`, `projected_Zips2YR`, `projected_Zips3YR`, `projected_ZipsRos`, `standard`, `statSplits`, `statSplitsAdvanced`, `tracking`, `vsPlayer`, `vsPlayer5Y`, `vsPlayerTotal`, `vsTeam`, `vsTeam5Y`, `vsTeamTotal`, `winLossPlayoffs`.

## Hypotheses to test (each needs evidence before any `unsupported` verdict)
- Split types need `sitCodes=` (from `/v1/situationCodes`, 602 codes): `statSplits`, `statSplitsAdvanced`, `careerStatSplits`.
- Matchup types need an opponent: `vsPlayer*` (`opposingPlayerId=`), `vsTeam*` (`opposingTeamId=`).
- Tracking/metric types need `metrics=` (from `/v1/metrics`, 22 names): `tracking`, `metricAverages`, `metricLog`.
- Playoff and first/last-year types need a season or game type that has data (`*Playoffs`, `firstYearStats`, `lastYearStats`, `gameTypeStats`).
- `standard`, `advanced`, `projected_Zips*`, `projectedRos` may be aliases or season-gated.

## Proposed Changes
1. A parameter-discovery pass in `scripts/gen_mlb_schemas.py` that, per unproductive stat type, tries the bare request, then one documented parameter at a time (sitCodes, metrics, opposing ids, season/gameType), records `tried`, and registers every combination that returns data with its parameters as part of the endpoint definition (a `params` fan-out dimension for sit codes / metrics).
2. Registry support for list-valued fan-out parameters (`sit_codes`, `metrics`) in `requests_for`, keyed so each (stat type, group, parameter value) is its own chunk.
3. Stat types that stay empty after the protocol are recorded `unsupported` with `verified_on` and `tried`; the audit then reports them as accounted for instead of NO_DATA.

## Out of Scope
Per-player matchup fan-out over all player pairs (only documented aggregate forms: `vsPlayerTotal`, `vsTeamTotal` if they work with a single id).

## Impact
Additive MLB datasets; larger generator run. Recorded as an ADR when decisions are made.
