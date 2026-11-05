# Design

- It is a feature of the existing audit tool (`core/audit.py` events, `baseballpy audit` commands), not a new tool.
- The analysis is a pure function over decoded events (`core/speed.py`), so tests feed it synthetic events and the CLI only prints.
- Caps are read from `RateLimitConfig` (host rate, per-host in-flight limit): the same numbers the client enforces and `tests/test_request_parallelism.py::test_default_host_rates_are_the_documented_ones` pins, so tests, config and log answer to one source.
- Rate check: starts in any one-second window must not exceed the cap plus one (window edges), and the mean over any ten seconds must not exceed 105% of the cap. In-flight check: the largest overlap of (sent, ended) intervals must not exceed the host's limit.
- Rejected: reading `retrosheet_download_file` style operation events (they are not requests); counting log lines per second (completion time includes limiter waiting); a second log file (the audit log already has the filters, `--since` and `read_events`).

## Evidence
- The leaky bucket (`AsyncLimiter(rate, 1)`) starts empty and holds `rate` requests, so a window of W seconds can hold `rate*(W+1)` starts; the first draft of the real-run test asserted a plain mean under 110% of the cap and failed (71 req/s mean over a 1.27 s run of 90 requests at a cap of 40), which showed the bound has to include the burst.
- Before this change, the Retrosheet log showed 60 events finishing in one second against a 15/s cap: those events wrap operations, so the old log could not prove either the rate or the in-flight number (see the owner's question of 2026-11-05).
- `baseballpy audit speed` on the 2026-11-05 log (runs before this change): rows per second per source work; the host section says the caps cannot be checked because those runs wrote no `http_request` events.
- Not verified: a full backfill run with the new events (the running Statcast download started before this change; the MLB API run will be the first).
