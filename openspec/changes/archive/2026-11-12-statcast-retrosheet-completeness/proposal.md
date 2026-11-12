# Proposal: statcast-retrosheet-completeness (leave no provider data behind)

## Why
The owner asked (2026-11-11) to make sure everything Statcast and Retrosheet offer is ingested, logged, timed and
threaded through the designed workflows. A check against the live Baseball Savant menu and retrosheet.org found gaps.

## Findings (2026-11-11, from the live menu and files, not from memory)
- **Savant:** the 2026-10-27 probe guessed route names and wrongly recorded four routes as 404. The live menu shows
  twelve leaderboard variants we did not ingest: swing timing and miss distance (batter, pitcher), year to year
  (batter, pitcher), arm angle, pitcher running game, first base receiving, outfield directional OAA, catcher stance,
  catcher throwing, hot stove (batter, pitcher). All answer CSV or an embedded JSON array with unique keys.
- **Savant, not ingestible yet (recorded with evidence):** the World Baseball Classic pitch search answers with the
  same rows as the MLB search for every filter tried; top performers and enhanced game scores answer HTML without an
  embedded table.
- **Retrosheet:** the Negro Leagues bundle (8,215 games) is in neither our events (0 of its games) nor fully in our
  box scores (4,647); its seven CSVs were raw files only.
- **Logging and threading:** leaderboard fetches and site downloads logged one duration only; the site-log parsing
  ran on one thread.

## What
1. Twelve new leaderboard variants in the declarative catalog, schemas generated live, fixtures, docs.
2. The four wrong "unsupported" entries replaced by the real routes; three new ones recorded with evidence.
3. Seven Negro Leagues tables (`negro_*`), opt-in, in the same `site` unit.
4. Download and processing seconds logged separately for leaderboard fetches and site downloads.
5. Site-log members parsed on the configured worker threads, with a test that the rows are identical.
