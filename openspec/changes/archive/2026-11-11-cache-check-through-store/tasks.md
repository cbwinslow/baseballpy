# Tasks: cache-check-through-store

Order: 1.1 -> 1.2 -> 1.3.

- [x] 1.1 Tests first: `tests/test_cache_through_store.py` (Statcast season served from a compacted lake with
  no request; compacted file removed means a fresh download with identical rows; a chunk its compacted file
  lacks is not cached). They fail before the change where the code is wrong.
  Done when the Statcast tests fail against the current code.
- [x] 1.2 `sources/statcast/extractor.py`: `_is_chunk_fresh` uses `store.has_part`, a cache hit uses
  `store.read_part`.
  Done when 1.1 passes and `tests/test_statcast*.py` still pass.
- [x] 1.3 Records and gates: `caching-and-invalidation` requirement, ADR 103, gates, close B-409, archive.
  Done when evidence is in `design.md`.
