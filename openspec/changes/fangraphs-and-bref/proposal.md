# FanGraphs and Baseball-Reference

## Why
The projection models need WAR and FanGraphs-style projections and park factors. Both sites ban fast scrapers and say so (Sports Reference: more than 20 requests a minute is a block of up to a day; FanGraphs: no scraping, API or automatic import, and a bot challenge on the site). The owner asked for sources "just like the others" without getting banned.

## What changes
1. `bref`: Baseball-Reference WAR from the two files it publishes for download (done, ADR 78).
2. FanGraphs: no downloader. The evidence is in `docs/sources/fangraphs.md`; the owner holds FanGraphs data on the homelab (`raw.fangraphs_*`), and a member-export importer is possible. Both are owner decisions.
