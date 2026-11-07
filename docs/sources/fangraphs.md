# FanGraphs (not downloaded)

## Verdict: no supported way to download, so baseballpy does not
- **What FanGraphs says** (read 2026-11-06): its contact page says that outside of the one-click data export for FanGraphs Members it does not support exporting data in any other way, and lists web scraping, API endpoints and importing data automatically as unsupported. Its 2026 "State of FanGraphs" post says it does not scrape data itself, keeps agreements with its data providers, and that at least 60 percent of its traffic is from non-human sources (crawlers, AI bots, scrapers). Its FAQ says the data is for private, non-commercial use or fair use. Its robots.txt disallows only a few legacy pages and sets no crawl delay.
- **What the site does:** it answers automated clients with a bot challenge ("Just a moment..."; pybaseball users report HTTP 403 on the leaderboards).
- **Decision:** baseballpy does not scrape FanGraphs and never tries to get around a bot challenge. No dataset is registered for downloading. This page is the probe evidence the project rules ask for when something cannot be ingested.

## What can be used instead
- **Baseball-Reference WAR** is built (`docs/sources/bref.md`), from files its owner publishes for download.
- **Statcast** leaderboards (xwOBA, expected stats, sprint speed, outs above average and more) and the **MLB Stats API** stat pools are already in the lake.
- **FanGraphs data the owner already holds** (the homelab database, schema `raw`: `fangraphs_batting` 108,947 rows, `fangraphs_pitching` 52,989, `fangraphs_fielding` 183,284, `fangraphs_projection` 547,980, `fangraphs_prospects` 19,153, splits, park factors, guts constants) could be imported once into typed Parquet for private use. That is an owner decision (`openspec/changes/fangraphs-and-bref`).
- **A member export importer** (the owner clicks FanGraphs' own Export Data button and drops the CSV in a folder; baseballpy types it) would follow FanGraphs' rules and could be shared as code. Not built.
