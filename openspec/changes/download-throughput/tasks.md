# Tasks

- [x] 1.1 `baseballpy speed`: requests per second against the cap, answer time, in-flight use, and the named limit, from the audit log
- [x] 1.2 speed watch in `baseballpy run` (`--speed-every`, default 10 minutes) printed into the queue log
- [x] 1.3 measure where the time goes: host probe, in-flight A/B, per-chunk write profile (results in the proposal)
- [ ] 2.1 profile the normalization of a live feed and a boxscore payload (cProfile on real payloads) and record the top costs in design.md
- [ ] 2.2 batched chunk writes: many games in one Parquet file per dataset with the same resume guarantees (own OpenSpec change `batched-chunk-writes`, ADR)
- [ ] 2.3 cheaper normalization of the per-game payloads, driven by 2.1
- [ ] 2.4 owner decision: worker processes that share the host's rate limit (the host lock allows one downloader per host today)
- [ ] 2.5 after 2.2 and 2.3, rerun `baseballpy speed` during a season and record the requests per second before and after
