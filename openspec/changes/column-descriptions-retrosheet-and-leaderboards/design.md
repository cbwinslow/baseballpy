# Design: Retrosheet and Leaderboard Column Descriptions

Reuses the mechanism of ADR 34 unchanged: `docs/columns/<source>.json` with a `_sources` map, `scripts/build_column_descriptions.py` as the deterministic builder, `docs coverage` ratchet.

- Retrosheet: AGENTS.md section 4 forbids bulk extraction from retrosheet.org; reading a handful of format documents is not bulk, but the host refused connections on 2026-10-27. Alternatives to try before giving up: the documents shipped in the `chadwickbureau/retrosheet` mirror (raw.githubusercontent.com), then retry the host later. Never invent field names (see `retrosheet-box-accounts`).
- Leaderboards: cite the provider's own column definitions only; anything else stays `TODO`.

## Evidence log (2026-10-27)
- `chadwickbureau/retrosheet` branches `master` and `official` hold only data files (`gamelog/`, `seasons/`, `reference/`) and a README; no format documents.
- Community code (`colindouglas/retrosheet` `R/retrosheetFields.R`, `calestini/retrosheet`) lists field names without descriptions, so it cannot be cited as a description source.
- Retrosheet documents the needed pages at `retrosheet.org/gamelogs/glfields.txt`, `downloads/csvcontents.html`, `eventfile.htm`, `boxfile.txt`; the host refused connections. Chadwick's own `cwgame`/`cwevent` documents describe fields that often match the game logs but use different names.
- Still to search: sportsdataverse / `baseballr` (GitHub) for how they document or fetch Retrosheet files, and `docs`-style copies on other hosts.
- FOUND (web search, 2026-10-27): `https://raw.githubusercontent.com/maxtoki/baseball_R/master/data/glfields.txt` is a copy of Retrosheet's game-log field guide (companion repository of a published book; Retrosheet's notice applies). The schema keeps field order, so field `n` is column `n`; ranges are expanded only by structure the document states. Descriptions cite this copy, not retrosheet.org.
- Web search also showed the schedule format is described as "parallel to the Game Logs, with fewer fields" (retrosheet.org/schedule), biofile/ejections/coaches pages exist under retrosheet.org/downloads/csv*.html and `Discrepancy File Format.pdf`, all on the unreachable host; no third-party copy found yet. Candidates not yet checked: `jerryword/retrosheet-csv`, `chadwickbureau/retrosplits` README.
- CHECKED, no field documentation: `jerryword/retrosheet-csv` (parsed Chadwick output, README only) and `chadwickbureau/retrosplits` README (describes its own daybyday/splits files, not Retrosheet's schedule, roster, reference, discrepancy or box formats). Remaining sources for those formats exist only on retrosheet.org (`schedule/index.html`, `downloads/csv*.html`, `biofile.htm`, `eject.htm`, `Discrepancy File Format.pdf`, `boxfile.txt`), which refused connections on 2026-10-27; retry later or supply copies.
- Savant leaderboards: the only provider glossary found is `csv-docs` (pitch columns). `mlb.com/glossary` defines metrics in prose but not by column name, so a mapping would be authored judgement; not done.

