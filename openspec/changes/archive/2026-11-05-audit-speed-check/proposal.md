# Audit speed check

## Why
The owner asked whether the logs prove the speeds and whether the tests agree with the real runs. Reading `audit.jsonl` from the 2026-11-05 Retrosheet backfill showed it cannot: the audit events wrap whole operations (a season download holds many requests), their durations include time spent waiting for the rate limiter (ADR 58), and 60 events completed in one second against a 15-requests-per-second cap on `raw.githubusercontent.com`. So neither the request rate nor the number of requests in flight can be read from the log today.

## What changes
- `HttpClient` writes one `http_request` audit event per real network attempt, with the moment the request was really sent (after the limiter and the in-flight gate) and the moment it ended.
- `baseballpy audit speed` (a new command of the existing `audit` group) reads those events and checks them against the same caps the client enforces (`RateLimitConfig`): requests per second, requests in flight, retries and failures per host, plus rows per second per source. It exits with 1 when a cap was broken or a request failed.
