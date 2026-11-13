# Tasks: data-validation-roundtrip

- [x] 1.1 Tests first: `tests/test_roundtrip.py` (equal cells pass; a 32-bit float, a dropped leading zero, a raw value turned NULL and a dropped row each fail; quarantined rows are counted).
- [x] 1.2 `baseballpy/core/roundtrip.py` and the command `baseballpy verify-roundtrip`, driven by the registry and the manifests.
- [x] 1.3 Run it on every Statcast, Retrosheet, Lahman and Chadwick dataset; record the table in design.md.
- [x] 1.4 Leading-zero integers are text in `infer_type_name`; regenerate the schemas and review the diff.
- [x] 1.5 Float64 for Statcast pitches and the four MLB columns; rebuild the stored chunks; round-trip clean. (Statcast pitches and pitches_minors rebuilt and proved equal to raw; MLB 2008-2026 rebuilt as float64 with equal row counts, see design.md.)
- [x] 1.6 Typed info columns of `box_games`; rebuild offline.
- [x] 1.7 `verify-sample` per source; gates; spec merge, ADR, archive. (results per source in design.md; spec merged into openspec/specs/audit-and-benchmarking; ADR 115)
