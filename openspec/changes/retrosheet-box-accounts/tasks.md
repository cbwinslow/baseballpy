# Tasks: Retrosheet Box Accounts

- [ ] 1. Specification <!-- id: 1 -->
  - [ ] 1.1 Obtain `boxfile.txt` (owner download or an allowed fetch path), store a copy under `docs/sources/retrosheet-boxfile.txt` with the Retrosheet notice; reconcile the layouts in `design.md`
  - [ ] 1.2 ADR 33 and spec merge
- [ ] 2. Implementation <!-- id: 2 -->
  - [ ] 2.1 `box_parser.py` (streaming, Latin-1/CRLF safe, strict field counts, `box_unparsed` for unknown kinds)
  - [ ] 2.2 Strict schemas + keys, registry entries, pool integration in `RetrosheetSource.ingest_season`
- [ ] 3. Tests <!-- id: 3 -->
  - [ ] 3.1 Fixtures cut from real `.EBA/.EBN/.EBE/.EBR/.EBF` files (one per record kind and era)
  - [ ] 3.2 Hypothesis on field counts and quoting; drift test for an unknown kind
- [ ] 4. Docs and verification <!-- id: 4 -->
  - [ ] 4.1 Generated dictionaries; `docs/sources/retrosheet.md` section for box accounts
  - [ ] 4.2 Live: ingest 1915 (5 box files) and 2023; check game counts against `gamelogs` for the same seasons
