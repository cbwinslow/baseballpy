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
