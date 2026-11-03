# Proposal: verify-small-answers (B-235)

## Problem
In the second full 2024 season run the MLB Stats API answered the single
`/v1/standings?standingsTypes=byOrganization` request with a valid but partial document: 106 of
201 team records (19 of 30 organizations, 308,486 bytes against 573,230). Five fetches made
afterwards were complete. The client stores whatever valid answer it gets, so the gap would have
stayed in the data. No documentation or library found by a web search validates this (the MLB
API has no official docs; pybaseball and baseballr do not check), and `cache check --upstream`
only compares git fingerprints.

## Solution
A low-volume request whose first answer is small is fetched again: if the second answer is the
same bytes it is stored (two requests); if the bodies differ a third is fetched and the largest
body is kept (a partial answer is a subset, so the largest is the most complete), with a
`provider_inconsistent` warning naming the sizes. "Low-volume" and "small" are settings, not
names: `verify_max_requests` (default 5 requests in the endpoint's call, 0 disables) and
`verify_max_bytes` (default 1,000,000). Fan-outs (hundreds of requests), big answers, paginated
pools and non-200 answers are not verified, so the extra cost stays below 1 percent of a season.

## Scope
`src/baseballpy/core/config.py` (two settings), `src/baseballpy/sources/mlb_api/generic.py`,
`tests/test_verify_small_answers.py`, spec `mlb-api-ingestion`, `docs/sources/mlb_api.md`, ADR 60.
