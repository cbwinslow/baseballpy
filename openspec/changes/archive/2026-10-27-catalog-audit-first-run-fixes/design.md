# Design: Fixes for the First Catalog Audit

## Lesson recorded
Both wrong verdicts (F-1, F-2) came from the first probe adding a parameter the route does not accept. The audit now probes `unsupported` items with the *default* parameters only (`request_params` with no extra qualifier for routes that have no `min`), and AGENTS.md section 11 item 3 already requires recording `tried`. A probe protocol: try the bare route first, then add one parameter at a time.

## Decisions
1. `active_spin`: bare route + `year`; no `min_param` (the qualifier breaks it); first season 2020 (the generator measures it).
2. `catch_probability`: `min` qualifier only, no `type`; keys `(player_id)`; the anonymous rows (null `player_id`) seen in the earlier probe came from the `type=Fielder` parameter, without it every season has real ids (2018: 295 rows, 2024: 301, none null).
3. Roster types `allTime`/`coach`/`gameday` use the existing `team_roster_<type>` template (`season` parameter). `gameday` is date-specific upstream (a game-day roster); without `date` the API returns the current game-day roster, which is what the dataset stores and documents; a dated variant is left to the parameterized-stat/roster follow-up.
4. `currentHalf` follows the standings template; for seasons without halves it is the same population as `regularSeason` (documented).
5. `GameType` members use provider ids and descriptions (S spring, R regular, F wild card, D division series, L league championship, W world series, C championship, P playoffs, A all-star, I intrasquad, E exhibition).
