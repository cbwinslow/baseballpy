# Proposal: finish-mlb-history

## Why
The per-game MLB data (boxscore, live feed, play-by-play, win probability, linescore) is in the lake for 2022, 2025 and 2026 and part of 2024. 2008 to 2021, 2023 and the rest of 2024 are missing, about 46,000 games. The owner wants all of it downloaded, unattended, with nothing left behind, and a list of what else stands between today and a v1 release.

Three problems stood in the way (all measured on 2026-11-08):
1. A games run also re-ran every season dataset and failed (exit 1) on the ones the provider refuses (HTTP 406, B-30), so a finished season looked failed and spent about 15 minutes on repeated requests.
2. Disk: 16 GB free, about 3 GB per season as small files (35,763 files for 2022). The history would not fit without compacting as it goes.
3. A crash ended the whole shell loop: nothing restarted it.

## What changes
- A games run fetches only the games (and the schedule it needs): `games_only` job parameter (ADR 91).
- `baseballpy run` compacts after each finished stage (`--compact`, on by default), which returns disk space and migrates files written under an older schema (ADR 87).
- `plans/mlb-games-history.toml`: one stage per missing season, newest first.
- The queue runs the plan unattended and repeats it daily, which also retries anything that failed.
- Follow-up work is listed as tasks: verification, audit, the five default gaps, rare untyped columns, batched chunk writes (speed), a live end-to-end test of the streamer, and the v1 release steps.

## Impact
Spec: `mlb-api-ingestion`. ADR 91. Code: `sources/mlb_api/api.py`, `sources/mlb_api/adapter.py`, `ingest/queue.py`, `cli_queue.py`. Data: `plans/mlb-games-history.toml`. Tests: `tests/test_mlb_game_levels.py`, `tests/test_queue.py`.
