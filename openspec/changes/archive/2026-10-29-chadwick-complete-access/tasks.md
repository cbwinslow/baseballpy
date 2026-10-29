# Tasks: chadwick-complete-access

- [x] 1. Code
  - [x] 1.1 Per-process register cache (ttl, refresh, clear_cache); `crosswalk` and `resolve_player` use it
  - [x] 1.2 `PlayerRecord` with every register column and a schema-sync test
  - [x] 1.3 Access to all four datasets: table properties, `names_for`, `links_for`, `country`
- [x] 2. Docs
  - [x] 2.1 Cited column descriptions for links, `altname_type` and the country codes; list what upstream leaves undefined
  - [x] 2.2 `docs/sources/chadwick.md`, README and quickstart show how to reach all four datasets
- [x] 3. Close
  - [x] 3.1 Gates, merge this spec delta and the `caching-and-invalidation` delta of `data-workflow-standard`, archive this change
