# Design: retrosheet-site-files

## 1. Evidence

Policy evidence is in `proposal.md`. Files and their pages were read with WebFetch on 2026-11-11 (a backend fetch,
not from the owner's address; about 20 page reads in all).

## 2. Prior art and reuse check

- The Chadwick GitHub mirror and Chadwick's own download scripts fetch the same zips; baseball.computer starts
  from the same Retrosheet files. Reused: `HttpClient` (rate limit, host lock, audit), `RawStore`, the audit logger.
- Not reused: nothing hand-rolled for HTTP (AGENTS.md section 14.3); robots.txt parsing is the standard library's
  `urllib.robotparser` on text fetched through `HttpClient`.

## 3. Decisions

- One request every four seconds, one connection, no retries on throttle signals (stop and report).
- Honest User-Agent: `baseballpy/<version> (polite bulk download)`; no contact data.
- Redundant subsets are skipped; one is fetched later to prove it is a subset.

## 4. Tests

`tests/test_retrosheet_site.py` with respx: no network, no sleeping (the limiter is configured fast in tests).

## 5. As built

Code: `sources/retrosheet/site.py` (file table in groups, `site_client`, `fetch_site_files`), `scripts/fetch_retrosheet_site.py`,
and in the shared layers `HttpClient.download_sync` / `DownloadResult` (a streamed, rate-limited, audited download that
never holds a file in memory and refuses a file above a limit) and `RawStore.adopt` (move a streamed file into the raw
folder with its sha256). Tests: `tests/test_retrosheet_site.py` (6) and `tests/test_http_download.py` (4), failing first.
A disk guard stops the run before a download when less than 4 GB is free.

### Real runs (2026-11-11, owner on a VPN; every file one request, one every 4 seconds, no refusal)

| Stage | Files | Size | Time | Result |
|---|---|---|---|---|
| core | 13 | 244.7 MB | 188 s | all valid zips |
| bundles + discrepancies | 11 | 9.9 MB | 53 s | all valid zips |
| officialtotals | 0 of 184 | stopped by me | - | the first file, `1882AA.zip`, had reached 443 MB and was still growing: the ledgers are hundreds of MB each (the page warns of "very large files"), so 184 files could be tens of GB and fill the disk. I stopped the job and deleted its partial file. Opt-in only, after a size decision. |

My first attempt at the 3 CSV bundles ran under a 10-minute command timeout that killed `csvdownloads.zip` at 660 MB
(the site sends about 1 MB/s); I deleted my own partial file. That bundle and `basiccsvs.zip` are dominated by
`plays.csv` (parsed play-by-play, event data) and are now the opt-in group `event_csvs`. `negroleagues.zip` was kept: it
holds seven CSVs for the Negro Leagues, including a 90 MB `plays.csv`.

### What is inside (read from the zips without unpacking)

| File | Contents |
|---|---|
| `tranDB.zip` | `tran.txt`: the transactions database (quoted CSV, 16 fields: dates, transaction id, player, type code, from and to team and league, draft type, round, pick, info); `readme.txt` lists about 80 type codes (trades, draft, free agent, injured list, suspension, military service, ...). **Not in the mirror.** |
| `playerlogs.zip` | 54,992 per-player CSVs (`<id>_b.csv`, `_f.csv`, `_p.csv`): batting, fielding and pitching lines per game with a `stattype` column and an `eject` column; 1.4 GB uncompressed. Same columns as the CSV bundle's `batting`, `fielding`, `pitching`. **Not in the mirror.** |
| `mgrlogs.zip` | 859 per-manager CSVs (team stats of each game: line score, lineup, batting, pitching, fielding, plus `eject`). **Not in the mirror.** |
| `umplogs.zip` | 1,762 per-umpire CSVs (game info plus the ejections the umpire made). **Not in the mirror.** |
| `negroleagues.zip` | `allplayers`, `gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, `plays` for the Negro Leagues. |
| `biodata.zip`, `biofile.zip`, `ballparks.zip`, `teams.zip`, `ejections.zip`, `rosters.zip`, `schedule.zip` | Same files and lines as the mirror (see the comparison). |
| `1890sdis.zip` .. `1980sdis.zip` | discrepancy files per decade (the mirror has them per season). |
| `GameFiles.pdf` | description of the account-file format. |

### Comparison with what we hold from the pinned GitHub mirror (read from the files, not from memory)

- The live mirror's `master` is still the pinned commit `ee82e50b...` (checked through the GitHub API today; pushed
  2026-08-13), 8,635 entries.
- `ejections`, `biofile`, `relatives`, `coaches`, `ballparks`, `teams`, the 2024-2026 schedules and the 4,148 roster files
  have **the same lines and line counts as the site** (the files differ in bytes only by line endings).
- `biofile0.csv` differs in 352 rows: the site is newer (it fills first and last game dates of Negro Leagues players
  that the mirror lacks, for example `abrej103` debut 19340530 on the site against 19350511 in the mirror). The site's
  data therefore runs a little ahead of the mirror.
