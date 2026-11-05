# Season calendar

## Why
`all_seasons()` of the Statcast and MLB adapters ended at the clock's year, so from 1 January it planned a season that had not started (the MLB calendar lists next year's season months ahead). Statcast pitches skipped it, but leaderboards, game feeds and the MLB endpoints were not checked. The owner asked for a way to know which seasons are available.

## What changes
- `core/season_calendar.py`: one request to `/v1/seasons/all`, cached twelve hours; a season counts once its first day has arrived.
- Both adapters end `all_seasons()` at the newest started season and skip any job of a not-started season with the reason.
- Tests with a pretend clock of 15 January and 19 February.
