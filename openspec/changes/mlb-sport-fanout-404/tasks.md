# Tasks
- [x] 1. Fan-out tolerance derived in `MlbEndpoint.__post_init__` (sport and team placeholders, non-paginated); tests for the rule and for a counted 404
- [x] 2. Live (scratch home, 2026-10-27): `ingest mlb_api -s 2023 -d season` failed first on sport 404s, then on `teams/231/alumni`; after the fix it completed with 658,502 rows in 2091 s (the resumed run reused the parts already stored)
- [ ] 3. Not verified: a live Ctrl-C mid-run; whether the six FAILURE audit events of the scratch run are the two original failures plus retries (check logs/audit.jsonl)
