# Tasks: retrosheet-site-datasets

- [x] 1.1 Tests first: `tests/test_retrosheet_site_datasets.py`.
- [x] 1.2 `SITE_DATASETS`, `read_site_datasets`, `files_for` in `sources/retrosheet/site.py`; generator
  `scripts/gen_retrosheet_site_schemas.py` and generated `site_tables.py`; schema, parser and catalog wiring.
- [x] 1.3 `ingest_site` and the `site` unit in the adapter (default runs plan no site job).
- [x] 1.4 Run it on the real lake, check the views and the type audit.
- [x] 1.5 Docs, spec merge, ADR, gates, archive, commit.
