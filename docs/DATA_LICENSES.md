# Data Licenses and Attribution

`baseballpy` itself is licensed **GPL-3.0-or-later** (see [LICENSE](../LICENSE) and [NOTICE](../NOTICE)).
It ships **no data**; it downloads data from third parties on request. Each source's own terms apply to
the data you download. Read the linked originals before publishing or redistributing anything.
(This page links to and summarizes terms; it is not legal advice and does not replace the originals.)

| Source | Where it comes from | Terms | Original text |
|---|---|---|---|
| Statcast / Baseball Savant, MLB Stats API (MLBAM) | `baseballsavant.mlb.com`, `statsapi.mlb.com` | MLB Advanced Media's published copyright notice limits use of its materials to individual, non-commercial, non-bulk use unless MLBAM authorizes otherwise. Bulk downloading is subject to that notice, so keep request rates polite (baseballpy rate-limits by default) and do not redistribute or commercialize the data without authorization. | <http://gdx.mlb.com/components/copyright.txt> |
| Retrosheet (events, game logs, rosters, reference tables) | GitHub mirror `chadwickbureau/retrosheet` | Free of charge for use with attribution. Required notice: "The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at www.retrosheet.org." Follow Retrosheet's data-use notice when you publish. | <https://www.retrosheet.org> |
| Lahman Baseball Database | Owner's mirror `cbwinslow/lahman-database-csv` (an unmodified re-post of SABR's release) or a user-supplied archive | Copyright © 1996–2025 SABR (donated by Sean Lahman). Licensed under Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0): attribute SABR and Sean Lahman, and share adaptations (including exported copies of the data) under the same licence. The release's own notice is in `readme2025.txt`, kept with the `LICENSE` text in `raw/lahman/documents/`; licensing questions go to SABR (see the mirror README). This is not legal advice. | <https://creativecommons.org/licenses/by-sa/3.0/> and <https://sabr.org/lahman-database/> |
| Chadwick Bureau Register | `chadwickbureau/register` | Open Data Commons Attribution License (ODC-By) 1.0 — attribute the Chadwick Baseball Bureau. | <http://opendatacommons.org/licenses/by/1.0/> |
| Kalshi (MLB markets) | `api.elections.kalshi.com` public market-data API | Terms for redistributing market data are not stated on the pages read: baseballpy shares the code, not the data. | <https://docs.kalshi.com> |
| Polymarket (MLB markets) | `gamma-api.polymarket.com`, `clob.polymarket.com` public APIs | Terms for redistributing market data are not stated on the pages read: baseballpy shares the code, not the data. | <https://docs.polymarket.com> |
| Baseball-Reference WAR | The two WAR files Baseball-Reference publishes for download (`/data/war_daily_bat.txt`, `/data/war_daily_pitch.txt`) | Sports Reference asks that pages are not scraped (at most 20 requests a minute, a longer block above that), that no website or tool is built on scraped data and that its data does not train generative AI without permission. baseballpy fetches only the two published files (2 requests), at 6 a minute, never retries after a refusal, and shares the code, not the data. Facts are not copyrightable, but credit Baseball-Reference when you publish WAR values. | <https://www.sports-reference.com/data_use.html>, <https://www.sports-reference.com/bot-traffic.html> |
| FanGraphs | `baseballpy ingest fangraphs -o download=yes` downloads leaderboards and projections from FanGraphs' own website JSON, slowly (one request every 2 seconds), with an honest user agent, never retrying a refusal; or types files you supply from `inbox/fangraphs/` | FanGraphs says it supports no scraping, API use or automatic import and protects the site with a bot challenge; its data is for private, non-commercial use or fair use. Use the downloader at your own risk, keep the data private and never share or publish `processed/fangraphs`, `raw/fangraphs` or `inbox/`; baseballpy ships no data. See `docs/sources/fangraphs.md`. | <https://blogs.fangraphs.com/faq-exporting-data/> |

## Attribution text you should include when publishing derived work
- Retrosheet: the notice quoted above.
- Chadwick Register: "Player identifiers from the Chadwick Bureau Register (ODC-By 1.0), https://github.com/chadwickbureau/register".
- Lahman: "The Lahman Baseball Database, copyright 1996-2025 SABR (donated by Sean Lahman), https://sabr.org/lahman-database/, licensed CC BY-SA 3.0"; share adaptations of it under the same licence.
- MLB data: follow the MLBAM notice above.
- Baseball-Reference WAR: "WAR from Baseball-Reference.com, https://www.baseball-reference.com/data/".

## Lahman data provenance rule
Lahman data is fetched **only** from the owner's mirror (configurable) or imported from an archive you supply with
`LahmanSource.import_archive`. The `chadwickbureau/baseballdatabank` repository is **not** used because its data
stops around 2023.
