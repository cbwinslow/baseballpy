## ADDED Requirements

### Requirement: Site Datasets Are Opt-In And Typed
The Retrosheet datasets parsed from retrosheet.org's own files (the `SITE_DATASETS` table) MUST be registered as opt-in with strict
schemas generated from the real files, MUST be ingested by the same `ingest retrosheet` command through a `site`
unit, and a default Retrosheet ingest MUST NOT plan a job that contacts retrosheet.org; a zip already stored MUST NOT
be requested again, and partial dates MUST stay the upstream text.

#### Scenario: Registered opt-in and not planned by default
- **WHEN** the registry is loaded and a default Retrosheet ingest is planned, then a site dataset is named
- **THEN** the six site datasets are `opt_in` with strict schemas and keys, the default plan has no site job, and naming a site dataset plans one `site` job
- Verified by `tests/test_retrosheet_site_datasets.py::test_the_six_site_datasets_are_registered_opt_in_and_strict` and `tests/test_retrosheet_site_datasets.py::test_a_default_ingest_never_plans_a_site_job_but_a_site_dataset_does`.

#### Scenario: Stored zips become typed tables without a request
- **WHEN** the site zips are already stored and the site datasets are ingested twice with the network blocked
- **THEN** typed tables are written with the registered schema (partial dates kept as text), and the second run finds every dataset current
- Verified by `tests/test_retrosheet_site_datasets.py::test_stored_zips_become_typed_tables_without_any_request` and `tests/test_retrosheet_site_datasets.py::test_ingest_site_writes_typed_parquet_then_skips_a_current_dataset`.
