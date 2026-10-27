# Tasks: Retrosheet Box Accounts

- [ ] 1. Specification <!-- id: 1 -->
  - [ ] 1.1 Obtain `boxfile.txt` (owner download or an allowed fetch path), store a copy under `docs/sources/retrosheet-boxfile.txt` with the Retrosheet notice; reconcile the layouts in `design.md`
  - [ ] 1.2 ADR 33 and spec merge
- [ ] 2. Implementation <!-- id: 2 -->
  - [x] 2.1 `box_parser.py` (Latin-1 fallback, strict field counts; unknown kinds kept in `box_records`, interim)
  - [x] 2.2 Strict schemas + keys, registry entries, `RetrosheetSource.box_accounts` + `ingest_season` integration (typed: games, starters, batting; lossless: records)
- [ ] 3. Tests <!-- id: 3 -->
  - [x] 3.1 Fixtures cut from real `.EBA/.EBN/.EBE/.EBR/.EBF` files (one per record kind and era)
  - [x] 3.2 Strict-layout and unknown-kind tests (Hypothesis deferred with the remaining typed kinds)
- [ ] 4. Docs and verification <!-- id: 4 -->
  - [x] 4.1 Generated dictionaries; `docs/sources/retrosheet.md` section for box accounts
  - [x] 4.2 Live (interim): 1964 ingested; all 1626 `gamelogs` games are present in `box_games` (1634 = + All-Star game + 7 World Series games). 1915 and 2023 not checked

## Status (2026-10-27)
Interim implementation is in; open: 1.1 (official spec), 1.2 (ADR 33 written for the interim; the final spec merge happens when the change closes), typed datasets for the kinds still in `box_records`, live check of further seasons.
