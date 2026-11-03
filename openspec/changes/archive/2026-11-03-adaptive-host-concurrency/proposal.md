# Proposal: adaptive-host-concurrency (REJECTED after measurement, no code kept)

## Hypothesis
After per-host limits and request-level parallelism (ADR 57) the 2024 MLB season took 2,264 s
(was 3,234 s) and ran at the 8 requests/s limit for minutes 15-35. Minutes 0-12 ran at about
1 request/s and the last 3 minutes at about 3 requests/s. By Little's law the requests in flight
needed to reach a rate R are R x latency, so a fixed limit of 4 looked too small for slow
requests (the audit log showed 17-19 s per request). Proposal: a per-host gate that measures the
request latency and moves its limit between a floor and a ceiling of 16, dropping back to the
floor on errors.

## Outcome
Built (`AdaptiveGate`, 11 tests, mutation-checked), measured live, and **rejected**: it gave no
measurable gain and made MLB's slow answers slower. The code was discarded, the evidence is in
`design.md`, and ADR 58 records the decision so it is not tried again without new evidence.
No specification changed.
