## ADDED Requirements

### Requirement: The Site Fetcher Is Polite And Obeys robots.txt
The Retrosheet site fetcher MUST read `robots.txt` before any file request and MUST NOT request a path it
disallows; MUST use one connection and at most one request every four seconds with a User-Agent that names the
library and carries no personal data; MUST stop the whole run at the first 403, 429, 503 or connection error and
report it; MUST skip files already stored and store each file with its sha256; and MUST audit-log and time every
download.

#### Scenario: Disallowed paths, throttling and reruns
- **WHEN** the fetcher is given a path that robots.txt disallows, then files where the first answers 429, then files that all answer 200 twice
- **THEN** the disallowed path is never requested, the 429 stops the run with the remaining files unrequested, and the second run of the good files makes no file request
- Verified by `tests/test_retrosheet_site.py::test_robots_disallowed_paths_are_never_requested`, `tests/test_retrosheet_site.py::test_a_throttle_answer_stops_the_whole_run` and `tests/test_retrosheet_site.py::test_files_are_stored_once_and_skipped_on_a_rerun`.

#### Scenario: Paced and honestly identified
- **WHEN** the site client is built
- **THEN** its host rate is at most one request per four seconds, its concurrency is one, and its User-Agent starts with `baseballpy/`
- Verified by `tests/test_retrosheet_site.py::test_the_client_is_paced_and_honestly_identified`.
