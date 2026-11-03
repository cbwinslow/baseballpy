# Tasks: verify-small-answers

- [x] 1.1 Settings `verify_max_requests` and `verify_max_bytes`; `_verified_get` in the MLB extractor, used by single requests of low-volume calls.
- [x] 1.2 Tests: a partial first answer is replaced by the full one, identical answers cost two requests, big or many or disabled cost one, non-200 is not verified, all-different keeps the largest and warns.
- [x] 1.3 Live: the standings request verified against MLB, and the extra requests of a full season counted.
- [x] 1.4 Spec merged, source doc, ADR 60, gates, archive.
