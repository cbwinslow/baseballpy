# Tasks
- [x] 1. Fan-out tolerance derived in `MlbEndpoint.__post_init__` (sport and team placeholders, non-paginated); tests for the rule and for a counted 404
- [x] 2. Live (scratch home, 2026-10-27): `ingest mlb_api -s 2023 -d season` failed first on sport 404s, then on `teams/231/alumni`; after the fix it completed with 658,502 rows in 2091 s (the resumed run reused the parts already stored)
- [x] 3a. The six FAILURE audit events of the scratch run are exactly the three failed runs (teams 404 twice, alumni 404 once; each logged as operation + ingest_job)
- [x] 3b. Live Ctrl-C mid-run: verified for the shared ingest runner on 2026-10-28 (real console Ctrl-C on a running `ingest`: interrupted promptly, `CANCELLED` audit event, exit 130, resume completed; see `archive/2026-10-28-unified-pipeline-and-cli` task G); the MLB season job was not interrupted separately
