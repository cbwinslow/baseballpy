# Design: chadwick-complete-access

- **Cache.** `ChadwickRegister.load` keeps one register per process in a small dict keyed by the lake
  home and the modification time of the `register` processed manifest, with the monotonic time it was
  loaded. It is reused until `ttl_for("chadwick")` seconds have passed (so the floating-ref check still
  happens in long sessions) or `refresh=True` / `ChadwickRegister.clear_cache()` is called. A new ingest
  rewrites the manifest and therefore invalidates the entry.
- **PlayerRecord.** All 40 register columns, same names and Python types as the Arrow schema
  (`key_person` and `key_uuid` required, the rest optional). `test_player_record_covers_every_register_column`
  fails if a regeneration adds a column the record lacks.
- **All four datasets.** `ChadwickRegister(table, names_table, links_table, countries_table)`; `load` fills
  all four. `names_for(person)` and `links_for(person)` take a `key_person` or a `PlayerRecord` and return
  the rows as dicts; `country(code)` matches ISO alpha-2/alpha-3, IOC or FIFA code, ignoring case
  (`NA` is Namibia, data and not null). A `key_person` can be re-used by upstream over time: the links and
  names rows belong to the register of the same release (documented).
- **Descriptions** only from cited text (ADR 34): README for link `source`/`value` and `altname_type`;
  Wikipedia pages of the code standards for the four country codes. Not defined upstream and left
  undescribed: `name_suffix`, `name_matrilineal`, `name_nick`, the other eight `altname_*` columns and
  `name_full_en`. Upstream does not document `countries.csv` at all.

## As built (2026-10-29)
- `ChadwickRegister.load` keeps one register per process (`_LOADED`, key = lake home + mtime of the processed register manifest, time-to-live from `ttl_for("chadwick")`); `clear_cache()` added. Real lake: first `get_register()` 1.0 s; 1000 `crosswalk()` calls 1.25 s (was about 190 s: 0.19 s per call).
- Profiling found a project-wide cost: `sources/catalog.register_all()` took 5.6 ms per call although idempotent, and every load calls it. It now returns at once while the registry still holds everything it registered, and runs again if the registry was replaced or cleared (test in `test_lake.py`).
- `PlayerRecord` has all 40 register columns (generated from the schema table, types included); `test_player_record_covers_every_register_column` guards it.
- `ChadwickRegister(table, names_table, links_table, countries_table)`; properties for the three optional tables; `names_for`, `links_for`, `country`. Checked on the real lake: `links_for` returns the tsncards link of person `00006177` (Elgin Battles), `country("JPN")` and `country("us")` resolve, `NA` is Namibia.
- Descriptions: `scripts/build_column_descriptions.py` now writes cited text for `register_links.source/value`, `register_names.altname_type` (Chadwick README) and the four country codes (ISO 3166-1, IOC, FIFA pages, each URL answered 200 on 2026-10-29). Not defined upstream, left undescribed: `name_suffix`, `name_matrilineal`, `name_nick`, eight `altname_*` columns, `name_full_en`.
- Docs corrected: the quickstart claimed `search_name("Pete Alonso")` returns "Peter Alonso"; the real register stores "Pete Alonso", so the example now uses "Michael Trout" (verified against the real register).
- The Chadwick software tools (`cwevent`, ...) are a Retrosheet matter (`chadwickpy` boundary) and are reviewed there.
