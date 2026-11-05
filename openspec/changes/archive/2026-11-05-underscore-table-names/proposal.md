# Underscore table names

## Why
Lahman tables had two names: the folder `lahman/AwardsShareManagers` and the view `lahman_awardssharemanagers`. SQL ignores letter case, so the CamelCase was lost in views and the run-together view names were hard to read. The owner chose underscores everywhere and pointed to the PostgreSQL `raw` schema as the style model.

## What changes
- Lahman tables are named `awards_share_managers` etc.: folder, registry key and view (`lahman_awards_share_managers`). Lahman's own spelling stays only for file names, download addresses and the git tree (`upstream_name`).
- One test (`tests/test_table_names.py`) enforces the rule for every dataset of every source.
- `docs/ADDING_DATA.md` states the rule and how to add a dataset or a source.
