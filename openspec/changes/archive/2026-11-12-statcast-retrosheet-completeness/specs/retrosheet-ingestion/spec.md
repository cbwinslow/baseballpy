## ADDED Requirements

### Requirement: The Negro Leagues Bundle Is Tables And Site Downloads Are Timed Apart
The seven CSVs of the Negro Leagues bundle MUST be opt-in typed datasets of the `site` unit, parsed on the configured
worker threads with rows identical to a sequential parse, and every site download MUST log its download seconds apart
from the rest.

#### Scenario: Seven tables, threads and timings
- **WHEN** the Negro Leagues datasets are registered, members are parsed with one and with four workers, and a site file is downloaded
- **THEN** seven opt-in datasets exist, both parses give equal tables, and the audit event has download and processing seconds
- Verified by `tests/test_retrosheet_site_logs.py::test_the_negro_leagues_bundle_is_seven_opt_in_tables`, `tests/test_retrosheet_site_logs.py::test_parallel_parsing_gives_the_same_rows_in_the_same_order` and `tests/test_retrosheet_site.py::test_every_download_is_audit_logged_and_timed`.
