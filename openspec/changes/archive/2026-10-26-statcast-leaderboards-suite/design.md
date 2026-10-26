# Design: Statcast Full Leaderboards & Metrics Suite

## 1. Upstream Endpoints & Parameter Conventions
All Baseball Savant leaderboard endpoints use `https://baseballsavant.mlb.com/leaderboard/{name}?csv=true` and accept standard parameters:
- `year`: Season year (integer, e.g. 2024).
- `type`: Perspective (`batter` or `pitcher` or `Fielder`).
- `min`: Minimum qualification threshold (`q` or integer count).
- `team`: Optional 3-letter team filter.
- `pos`: Position filter (e.g. `3` for 1B, `OF` for outfield).

## 2. Directory Layout & Caching
Cached under `~/.baseballpy/cache/statcast/leaderboards/`:
```text
~/.baseballpy/cache/statcast/
├── manifest.json
├── leaderboards/
│   ├── expected_statistics/year=2024_type=batter.parquet
│   ├── exit_velocity/year=2024_type=batter.parquet
│   ├── sprint_speed/year=2024.parquet
│   ├── bat_tracking/year=2024_type=batter.parquet
│   ├── outs_above_average/year=2024.parquet
│   ├── arm_strength/year=2024.parquet
│   ├── poptime/year=2024.parquet
│   ├── catcher_framing/year=2024.parquet
│   ├── pitch_arsenals/year=2024.parquet
│   ├── pitch_movement/year=2024.parquet
│   └── abs_challenges/year=2024.parquet
```

## 3. Rate Limiting & Concurrency
Enforce host-specific rate limiter (`baseballsavant.mlb.com` capped at 2.5 req/s) via `aiolimiter.AsyncLimiter` and jittered backoff via `tenacity`.
All cache writes route through `atomic_write_parquet` to ensure zero corruption on network termination.
