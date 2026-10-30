# Change Proposal: Catalog Completeness Audit (Probe CI)

## Context & Motivation
Three coverage gaps this program found late were all *completeness* defects that no test caught: stat groups probed from a hand-picked list, minor leagues defaulted out, and minor-league Statcast pitches declared `unsupported` after probing the wrong parameters (ADR 30, ADR 31). Coverage claims need an automated check against the providers' own lists, and every `unsupported` verdict needs periodic re-verification.

| ID | Gap |
|----|-----|
| Q-1 | No command compares provider-listed items (stat types/groups, sports, standings/roster types, leaderboard routes, git-tree files) with the registry. |
| Q-2 | `unsupported`/`empty` verdicts are never re-probed; stat combinations are sampled for one season and a few players. |
| Q-3 | The probes run only when someone remembers to run the generators. |

## Proposed Changes
1. `baseballpy catalog audit [--source S] [--json]`: re-runs the cheap probes, diffs provider lists against the registry and prints `MISSING` (provider lists it, registry lacks it), `STALE` (registry has it, provider no longer lists it), `REVIVED` (an `unsupported`/`empty` item now returns data) and `DRIFT` (new columns beyond `_extras` expectations). Non-zero exit on any MISSING/REVIVED.
2. Wider sampling for combos: several eras (1990s, 2010s, current) and a larger, role-diverse person sample; the generator records which sample found each combination.
3. A scheduled workflow (`live.yml`, created by `repo-hygiene-and-docs-sync` task 5.1) runs the audit weekly and opens an issue with the report.
4. Each `unsupported` registry entry stores `verified_on` and `tried` (parameters/URLs attempted) so a re-check starts from the evidence.

## Out of Scope
Auto-fixing findings; the CI workflow files themselves (hygiene change).

## Impact
Read-only network probes; additive CLI command. Recorded as ADR 35.
