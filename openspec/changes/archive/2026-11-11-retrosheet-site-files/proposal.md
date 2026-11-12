# Proposal: download Retrosheet's own bulk files, politely

## Why

The owner (2026-11-11) allowed fetching files from retrosheet.org (on a VPN, after an earlier ban for hitting the
site many times) and asked for every file except the event files, so that we can decide which to codify. The
GitHub mirror we use (`chadwickbureau/retrosheet`) carries the event, box, game-log and roster data but not
everything the site publishes (for example transactions, the CSV bundles, official daily totals, player logs).

## Policy evidence (read 2026-11-11, before any request to the site)

- `https://www.retrosheet.org/robots.txt`: `User-agent: *` with `Disallow: /boxesetc/`, `/gamelogs/` (and the
  double-slash forms). No `Allow`, no `Crawl-delay`. **We never request those paths** (the game logs are in the mirror).
- `https://www.retrosheet.org/notice.txt`: recipients are "free to make any desired use of the information",
  including selling it; any transfer or product built on it must say "The information used here was obtained free of
  charge from and is copyrighted by Retrosheet." It says nothing about bots, scraping or rate limits.
- Every download page read (`downloads/othercsvs.html`, `csvplayers`, `csvmanagers`, `csvumpires`, `csvteams`,
  `csvparks`, `schedule/`, `transactions/`, `eject.htm`, `biofile.htm`, `officialtotals/`, `NegroLeagues/`) has no
  rule on automated or bulk access. Per-person, per-team and per-park logs exist only through a search box: those
  would take thousands of requests and are not fetched; the bulk zips (`playerlogs`, `mgrlogs`, `umplogs`) are.
- Our own `HttpClient` identifies itself as `python-requests/2.32.3` by default (`core/http.py`); the site fetch
  uses an honest name instead (finding recorded for ADR review).

## What

A declarative table of the site's bulk files and a polite fetcher (`sources/retrosheet/site.py`, a thin script
`scripts/fetch_retrosheet_site.py`): robots.txt is read first and obeyed; one connection, one request every four
seconds; a descriptive `baseballpy/<version>` User-Agent (no personal data); any 403, 429, 503 or connection error
stops the whole run at once and is reported; files already stored are skipped; every download is audit-logged and
timed; files go to `raw/retrosheet/site_files/` with sha256 in the manifest. Groups:

- **core**: `biodata.zip`, `playerlogs.zip`, `mgrlogs.zip`, `umplogs.zip`, `biofile.zip`, `rosters.zip`,
  `ballparks.zip`, `teams.zip`, `ejections.zip`, `schedule/schedule.zip` (all schedules in one file),
  `transactions/tranDB.zip`, `transactions/readme.txt`, `GameFiles.pdf` (the format description).
- **bundles**: `downloads/csvdownloads.zip`, `downloads/basiccsvs.zip`, `downloads/negroleagues.zip` (sizes probed first).
- **discrepancies**: `1890sdis.zip` to `1980sdis.zip` (ten decades).
- **officialtotals**: 184 ledger zips, fetched last and slowest.
- **Not fetched, with reasons:** everything under `/events/` (event and box-score files, excluded by the owner and in
  the mirror), `/gamelogs/` and `/boxesetc/` (robots.txt), `allngldata.zip` (contains event files), the per-season,
  per-league and per-game-type CSV sets and the 150 per-year schedule zips (subsets of files above; one is fetched
  later to prove it), per-person/team/park search results, research PDFs.

## Out of scope

Deciding which files become datasets (the next step, with the files in hand); any change to the existing
Retrosheet datasets.
