## ADDED Requirements

### Requirement: The Download Speed Is Measured And The Limit Is Named
`baseballpy speed` MUST read the audit log and report, for each host, the requests per second over the window, the rate-limit cap and the share used, the median and 90th percentile answer time, the in-flight use (rate times answer time) against the in-flight allowance, and the number of 429 and 5xx answers. It MUST name the limit: too little traffic to judge, the host pushing back (2% or more of answers), at the rate limit (80% or more of the cap), idle capacity so the wait is local (in-flight use under half the allowance), or a slow host. It MUST skip damaged lines and requests outside the window, and MUST NOT change any setting.

#### Scenario: Rate, cap and verdicts
- **WHEN** the audit log holds 300 requests of one second each over 100 seconds, then 30% pushed-back answers among 100 requests, then a full in-flight allowance below the cap
- **THEN** the report shows about 3 requests per second against a cap of 10 with the wait named local, then names the host pushing back, then names a slow host; a cut line and an old request are ignored
- Verified by `tests/test_speed.py::test_speed_is_requests_per_second_against_the_cap`, `tests/test_speed.py::test_the_four_verdicts`, `tests/test_speed.py::test_a_full_in_flight_allowance_below_the_cap_means_the_host_is_slow`, `tests/test_speed.py::test_pushback_and_old_or_damaged_lines` and `tests/test_speed.py::test_a_missing_log_or_no_traffic_says_so`.

#### Scenario: The command
- **WHEN** `baseballpy speed --json` runs
- **THEN** it prints the report as one JSON object
- Verified by `tests/test_speed.py::test_the_speed_command`.

### Requirement: The Queue Reports Its Speed At Intervals
`baseballpy run` MUST print the measured speed of every active host at the interval given by `--speed-every` (default 10 minutes; 0 turns it off) while it runs, and stop the report when the queue stops.

#### Scenario: The watch
- **WHEN** the queue is started with a speed interval
- **THEN** a watch thread prints the speed line each interval until the queue is stopped
- Verified by `tests/test_queue.py::test_the_speed_watch_prints_each_interval_and_stops_with_the_queue`.
