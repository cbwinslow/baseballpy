# Change Proposal: Statcast Full Leaderboards & Metrics Suite

## Why
Baseball Savant provides not only pitch-by-pitch tracking via `statcast_search/csv`, but also 11 official analytical leaderboard endpoints:
1. `expected_statistics` (xBA, xSLG, xwOBA, xOBP)
2. `statcast` (Exit Velocity & Barrels)
3. `sprint_speed` (Sprint Speed & HP to 1B)
4. `running_splits` (Baserunning & 90-ft splits)
5. `outs_above_average` (OAA & Defensive Runs)
6. `bat_tracking` (Bat Speed & Swing Length)
7. `arm_strength` (Throwing velocity across positions)
8. `poptime` (Catcher Pop Time & Exchange Time)
9. `catcher_framing` (Strike rate & Runs Extra Strikes)
10. `pitch_arsenals` (Pitch mix & characteristics)
11. `pitch_movement` (Pitch horizontal and vertical movement)
12. `abs-challenges` (Automated ball-strike challenge results)

To satisfy the Full Data Preservation mandate (ADR 15), `baseballpy` must provide a comprehensive, strongly-typed extractor and normalizer for all Savant leaderboards, with token-bucket rate limiting (2.5 req/s), atomic parquet caching with manifest checkpointing, and clean top-level functions (`bb.statcast.get_leaderboard(...)`).

## What Changes
1. **Exhaustive Schema Documentation:** Document all leaderboard endpoints, parameters, tables, and column dictionaries in `docs/sources/statcast.md`.
2. **Leaderboard Extractor & Normalizer:** Implement `StatcastLeaderboardExtractor` and `StatcastLeaderboardNormalizer` in `src/baseballpy/sources/statcast/leaderboards.py`.
3. **Typed Schemas:** Define explicit physical PyArrow schemas for each leaderboard in `src/baseballpy/sources/statcast/leaderboards.py`.
4. **Public Facade Integration:** Expose `get_leaderboard(name, year, **kwargs)` and individual helpers (`expected_statistics`, `exit_velocity`, `sprint_speed`, `bat_tracking`, `outs_above_average`, etc.) under `baseballpy.sources.statcast`.
5. **Testing & Verification:** Comprehensive unit tests in `tests/test_statcast.py` with mock fixtures verifying extraction, normalization, and typing.
