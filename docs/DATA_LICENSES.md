# Data Licenses and Attribution

`baseballpy` itself is licensed **GPL-3.0-or-later** (see [LICENSE](../LICENSE) and [NOTICE](../NOTICE)).
It ships **no data**; it downloads data from third parties on request. Each source's own terms apply to
the data you download. Read the linked originals before publishing or redistributing anything.
(This page links to and summarizes terms; it is not legal advice and does not replace the originals.)

| Source | Where it comes from | Terms | Original text |
|---|---|---|---|
| Statcast / Baseball Savant, MLB Stats API (MLBAM) | `baseballsavant.mlb.com`, `statsapi.mlb.com` | MLB Advanced Media's published copyright notice limits use of its materials to individual, non-commercial, non-bulk use unless MLBAM authorizes otherwise. Bulk downloading is subject to that notice, so keep request rates polite (baseballpy rate-limits by default) and do not redistribute or commercialize the data without authorization. | <http://gdx.mlb.com/components/copyright.txt> |
| Retrosheet (events, game logs, rosters, reference tables) | GitHub mirror `chadwickbureau/retrosheet` | Free of charge for use with attribution. Required notice: "The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at www.retrosheet.org." Follow Retrosheet's data-use notice when you publish. | <https://www.retrosheet.org> |
| Lahman Baseball Database | Owner's mirror `cbwinslow/lahman-database-csv` (an unmodified re-post of SABR's release) or a user-supplied archive | Copyright © 1996–2025 SABR (donated by Sean Lahman). SABR publishes the license terms with each release (see `readme2025.txt` in the release and <https://sabr.org/lahman-database/>); licensing questions go to SABR (see the mirror README). | <https://sabr.org/lahman-database/> |
| Chadwick Bureau Register | `chadwickbureau/register` | Open Data Commons Attribution License (ODC-By) 1.0 — attribute the Chadwick Baseball Bureau. | <http://opendatacommons.org/licenses/by/1.0/> |

## Attribution text you should include when publishing derived work
- Retrosheet: the notice quoted above.
- Chadwick Register: "Player identifiers from the Chadwick Bureau Register (ODC-By 1.0), https://github.com/chadwickbureau/register".
- Lahman: credit SABR and Sean Lahman and link to the official site.
- MLB data: follow the MLBAM notice above.

## Lahman data provenance rule
Lahman data is fetched **only** from the owner's mirror (configurable) or imported from an archive you supply with
`LahmanSource.import_archive`. The `chadwickbureau/baseballdatabank` repository is **not** used because its data
stops around 2023.
