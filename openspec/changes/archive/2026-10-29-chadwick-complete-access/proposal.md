# Proposal: chadwick-complete-access

## Why
Owner asked (2026-10-29), after `chadwick-source-review` closed: is Chadwick completely done, can code
reach all of its data, is everything documented, are the specs closed? An audit found five gaps:
1. `crosswalk()`, `get_register()` and `resolve_player()` reload the register on every call (0.19 s each
   once warm, about 1 s cold): a loop over many players is unusable.
2. `PlayerRecord` carries 19 of the register's 40 columns: death dates, the pro/college/MLB spans of
   playing, managing and umpiring, `key_sr_*` and `name_matrilineal` cannot be read from a record.
3. Only the register and `names.csv` (as search aliases) are reachable from Python. The `links.csv` and
   `countries.csv` datasets are stored and have SQL views but no Python access.
4. 19 columns have no description. Some can be cited (README: link sources and name kinds; the ISO, IOC
   and FIFA code standards for countries); the rest are not defined upstream and stay undescribed.
5. The doc page and the quickstart do not show how to reach all four datasets.

## What changes
A per-process cache of the loaded register (renewed after the Chadwick time-to-live or on `refresh`),
a `PlayerRecord` with every register column (a test keeps it in step with the schema), register methods
`names_for`, `links_for`, `country` and table properties for all four datasets, cited descriptions
through `scripts/build_column_descriptions.py`, and docs. The delta of `data-workflow-standard`
(`caching-and-invalidation`) is merged because that behavior is already built.

## Out of scope
The Chadwick Bureau software tools (`cwevent` and friends) are a Retrosheet concern: they are reached
only through `chadwickpy` in `sources/retrosheet/_chadwick_adapter.py` and are reviewed in the
Retrosheet source review. CSV/PostgreSQL export (Track 6a).
