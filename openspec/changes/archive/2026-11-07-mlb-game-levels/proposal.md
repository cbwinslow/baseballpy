# MLB game levels

## Why
The per-game MLB download (`ingest mlb_api -d games`) took every final game of every level the schedule lists: about 16,000 games per season (major leagues, minors, winter and college leagues) against about 2,960 in the major leagues. At 1.9 requests per second that is 5 to 6 days for all seasons, and the 2026 run stopped with a `MemoryError` after 7.9 hours at about 11,000 games. The owner chose the major leagues first.

## What changes
`--option sports=...` picks the levels whose games get the per-game datasets: `1` (major leagues, the default), a list such as `1,11,12`, or `all`. `schedule_hydrated.sport_id` already says the level of each game, so nothing new is downloaded to decide. The minors stay available with `sports=all`; nothing is removed from the catalog.
