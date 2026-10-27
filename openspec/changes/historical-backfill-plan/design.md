# Design: Historical Backfill

- **Order:** reference snapshots first (Chadwick register, Lahman, MLB reference lists, jobs/venues), then per season ascending: Retrosheet, MLB season endpoints (sports from `ref_sports`), Statcast pitches, minor-league pitches, leaderboards; per-game endpoints (`include_games`) and `/gf` feeds last because they dominate time and disk.
- **Estimates (to be refined with the measured numbers above):** MLB season endpoints without games are minutes per season; games add roughly 6 per-game requests per game (about 2,430 games x 20 resources); Statcast is ~700,000 pitches per MLB season (about 25 minutes at the observed rate) plus ~230,000 minor-league pitches; Retrosheet about 2 minutes per season.
- **Idempotence:** every piece is already chunked and manifest-resumable; the plan file only orders and bounds them.
- **Safety:** raw tier keeps every response, so a schema regeneration can re-process without network; the plan reports rows, bytes and duration per piece for later comparison.
- **Owner decision points:** whether to include per-game MLB endpoints for every season, the `/gf` feed (about 7 GB per season), and `ingest_history` pools, since these dominate storage.
