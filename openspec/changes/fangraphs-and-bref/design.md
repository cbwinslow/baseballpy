# Design: FanGraphs and Baseball-Reference

## Evidence (2026-11-06)
- Sports Reference bot-traffic page: more than 20 requests a minute (10 for FBref and Stathead) puts a session "in jail for up to a day"; no mention of robots.txt or a crawl delay. Data-use page: do not aggressively spider, do not create websites or tools based on scraped data, do not train generative AI on it without permission; facts cannot be copyrighted. The `/data/` page lists the downloadable files (`war_archive-YYYY-MM-DD.zip` daily; the page text is 190,000 characters long) and the About page links `war_daily_bat.txt` and `war_daily_pitch.txt`.
- Measured: `war_daily_bat.txt` 35.6 MB, 126,547 rows, 49 columns, years 1871 to 2026, 12,023 `NULL` WAR; `war_daily_pitch.txt` 15.4 MB, 57,884 rows, 43 columns; keys `(player_ID, year_ID, stint_ID)` unique in both; UTF-8.
- FanGraphs robots.txt: only legacy pages disallowed, no crawl delay. Contact page: only the one-click export for members is supported; scraping, API endpoints and automatic imports are listed as unsupported. 2026 state-of-the-site post: it does not scrape, keeps agreements with data providers, and at least 60 percent of its traffic is non-human. The site answers automated clients with a bot challenge. No terms page was read in full (the terms URL tried returned 404), so the stance above comes from FanGraphs' own statements.
- Homelab (read only): `raw.fangraphs_batting` 108,947 rows by 477 columns, `fangraphs_pitching` 52,989 by 546, `fangraphs_fielding` 183,284, `fangraphs_projection` 547,980 by 120 (team, counting and rate stats, WAR, quantiles), `fangraphs_prospects` 19,153 by 137, `fangraphs_split_batting` 167,929, `fangraphs_split_pitching` 135,000, `fangraphs_park_factors` 3,135, `fangraphs_park_factors_handedness` 750, `fangraphs_guts` 156; also `raw.bref_batting`, `bref_pitching`, `bref_war_batting` and `bref_war_pitching`. Every column there is text.

## Decisions
1. Baseball-Reference: only the published files (decided, ADR 78).
2. FanGraphs: no downloader (decided, ADR 78). What to do with the homelab copy is open (task 2.1).
