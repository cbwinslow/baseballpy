# Tasks

- [x] 1.1 `baseballpy speed`: requests per second against the cap, answer time, in-flight use, and the named limit, from the audit log
- [x] 1.2 speed watch in `baseballpy run` (`--speed-every`, default 10 minutes) printed into the queue log
- [x] 1.3 measure where the time goes: host probe, in-flight A/B, per-chunk write profile (results in the proposal)
- [x] 2.1 profile the per-game path with real payloads and a lake-sized manifest and record the costs in design.md (found: the name-clash check and one manifest rewrite per chunk)
- [x] 2.2 deferred manifest saves in bulk runs and an index for the name-clash check, in place of one full-manifest copy and rewrite per chunk (ADR 93)
- [ ] 2.2b batched chunk writes: many games in one Parquet file per dataset with the same resume guarantees (own OpenSpec change `batched-chunk-writes`, ADR); worth about 110 ms of the remaining 520 ms per game
- [ ] 2.3 cheaper normalization of the per-game payloads (414 ms per game without any storage). Normalizing in 8 worker processes gave only 100 ms (630 to 530 ms per game) for about 2.4 GB more committed memory, so it was not kept; look for less Python per record instead
- [ ] 2.4 owner decision: worker processes that share the host's rate limit (the host lock allows one downloader per host today)
- [ ] 2.5 after 2.2 and 2.3, rerun `baseballpy speed` during a season and record the requests per second before and after
