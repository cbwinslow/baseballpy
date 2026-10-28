# Design: Retrosheet CSV bundles (evidence only; not implemented)

## Reachability, 2026-10-28
`www.retrosheet.org` resolves (216.57.231.121) but TCP connections to ports 80 and 443 time out after 10 s, from two independent networks: the owner's PC and the homelab server (`curl -sv -m 10`; `csvdownloads.html`, `csvoverview.html`, `csvcontents.html` and `/` all returned HTTP code 000 after 30 s). So the generator that must probe the files cannot run anywhere available today.

A web search found a December 2025 forum thread where one user could not reach the site for weeks and a VPN fixed it while others reached it normally, which points at network-specific blocking rather than a site outage (Sources: the Tapatalk thread listed under the search "retrosheet.org website down unreachable connection timed out"; no status page exists). No fix is attempted here: Retrosheet code is never pointed at another host.

## What the pages say (search snippets, not fetched pages)
- One zip holds seven master CSV files covering games 1898-2025 (all games Retrosheet has any information for, including Negro League, all-star and postseason games); a simplified set keeps only the `stattype = value` rows; parsed play-by-play (`plays`) is a separate download, as one file (16,538,512 lines) or by season; team-specific bundles hold the seven basic CSVs for one team; the fall 2025 package is about 710 MB (pages: `csvoverview.html`, `csvdownloads.html`, `csvcontents.html`, `downloads/plays.html`, `fall2025release.html`).
- Column names, types and licence wording were not read, so no schema may be written (types come from data, never guesses).

## Plan once reachable
1. `scripts/gen_schemas.py retrosheet` style generator probes the seven masters and `plays`, widens types over the full files, verifies keys and writes `docs/*_probe.json`.
2. Register the datasets with `ingest="opt_in"` (the `plays` file is about 16.5 M rows) through the existing downloader and `HttpClient`, with the bundle's sha256 in the raw manifest.
3. Add the licence and attribution wording to `docs/DATA_LICENSES.md`.
Implementation waits for the owner's approval and for the host to be reachable.

## How others consume the bundles (searched 2026-10-28, standard mode)
Queries: "Retrosheet CSV downloads bundle retrosheet R package calestini retrosheet csv files plays gameinfo teamstats" and "jerryword retrosheet-csv github"; the READMEs of both repositories were read from `raw.githubusercontent.com`.
- **R `retrosheet` (CRAN, Colin Douglas, GPL >= 2)**: `getRetrosheet()` / `get_retrosheet()` parse the single-season event, game-log, roster and schedule files into tibbles. It does not read the official CSV bundles.
- **`calestini/retrosheet` (Python, MIT, version 0.1.0, work in progress)**: parses the event files into its own CSVs; its README says the files are not yet fully parsed and the statistics not validated, and points to Chadwick for a complete solution. Not a consumer of the official bundles.
- **`jerryword/retrosheet-csv` (no licence declared, last push 2020-09)**: Chadwick `cwgame`, `cwevent`, `cwcomment`, `cwsub` and `cwdaily` output (Chadwick 0.8.1) from the event files, plus `FILENAME_TX` and `LINE_NUMBER_CT` columns for traceability. Its own derived CSVs, not the official bundles.
- **Chadwick tools**: read the event files; the `chadwickbureau/retrosheet` mirror that this project already uses ships those and no bundle.
- All four repeat the Retrosheet notice (data "obtained free of charge from and is copyrighted by Retrosheet"); that wording is the attribution baseline for `docs/DATA_LICENSES.md`.
- Finding: no public project was found that consumes the official CSV bundles (`csvoverview.html`, seven master CSVs, 1898-2025), so there is no community schema to compare against; the bundles' column names and types must come from the files themselves (task 1, blocked on reachability) and a generator, as the plan above says. The existing event-file path (Chadwick-parsed `events`, `gamelogs`, box accounts) covers the games those files hold; whether the bundles add games the event files lack (the overview page mentions Negro League, all-star and postseason games from 1898) is to be measured once the bundles can be read, not assumed.
