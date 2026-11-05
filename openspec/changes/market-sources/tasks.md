# Tasks
- [ ] 1.1 owner decisions M1 to M4 (design.md) recorded (M1 done: all MLB markets)
- [ ] 1.2 (Kalshi probed, Polymarket open) web research and probes of both APIs written into design.md (fields, paging, limits, history depth)
- [ ] 1.3 measure the homelab MLB subset (rows, bytes as Parquet) and pick the transfer route
- [ ] 2.1 Kalshi: catalog DONE (ADR 70); candles, trades and live snapshots still open
- [ ] 2.2 Polymarket: catalog (events, markets, outcomes), price history, live snapshots: registry, schemas from probes, adapter, tests
- [ ] 3.1 one-time import of the homelab MLB subset into the lake (typed, checked against the APIs on a sample)
- [ ] 3.2 close the gap from the last imported day to today with the new downloaders
- [ ] 4.1 docs per source, specs with Verified-by tests, ADRs, gates, archive
