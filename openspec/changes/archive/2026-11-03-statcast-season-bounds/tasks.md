# Tasks: statcast-season-bounds

- [x] 1.1 Delete the stray pre-2008 Statcast data from the owner's lake (87 season folders, 122 manifest entries; owner approved).
- [x] 1.2 `seasons.py` with the bounds rule; every Statcast entry point applies it before any request.
- [x] 1.3 Adapter maps skips to `SKIPPED` jobs; a future/unstarted season is skipped, not an error.
- [x] 1.4 Tests, `docs/sources/statcast.md`, ADR 56, spec delta merged, gates, live check, archive.
