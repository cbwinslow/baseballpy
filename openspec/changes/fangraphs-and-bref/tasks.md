# Tasks
- [x] 1.1 `bref` source: endpoints, generated schemas, extractor with a block stop, ingest by season, adapter, docs, tests (ADR 78)
- [x] 1.2 shared client: rates below one request a second, `host_max_attempts`, NULL words in the CSV reader
- [x] 1.3 FanGraphs terms and bot protection recorded as evidence (`docs/sources/fangraphs.md`)
- [x] 2.1 import of the FanGraphs tables already on the homelab for private use (owner decided yes; ADR 79): `fangraphs` source, inbox, export script, schemas from the files
- [ ] 2.2 `bref` daily archive (`war_archive-YYYY-MM-DD.zip`): WAR as it was on each day, opt-in, for backtests
- [x] 3.1 slow honest downloader for leaderboards and projections (ADR 80), generic `--option` switch
- [ ] 3.2 downloaders for guts and park factors (HTML pages), prospects and splits (POST route): each downloadable, or recorded as not possible with evidence
