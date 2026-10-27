# Design: Catalog Completeness Audit

- **Sources of provider lists:** MLB `/v1/statTypes`, `/v1/statGroups`, `/v1/sports`, `/v1/standingsTypes`, `/v1/rosterTypes`, `/v1/gameTypes`, `/v1/leagueLeaderTypes`; Savant leaderboard index page links; GitHub trees (Retrosheet, Chadwick, Lahman) vs the pattern registries.
- **Mechanics:** reuse `scripts/gen_*_schemas.py` probe functions as library code (`baseballpy.audit` module) so the audit and the generators cannot drift; the audit never writes generated modules.
- **Verdicts** are data (`AuditFinding(kind, source, item, evidence)`), rendered by the CLI and serialised for CI.
- **Unsupported hygiene:** `tried` lists parameters and URLs; re-verification retries those plus the documented client conventions; findings of kind `REVIVED` link the evidence.
- **Cost control:** the audit runs list-level probes and one request per unsupported item; the full combo sweep stays in the generators.
- **Lesson encoded:** a verdict of `unsupported` is a claim with an expiry date.
