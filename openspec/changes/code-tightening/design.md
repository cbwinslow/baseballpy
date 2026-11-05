# Design
- Rule: a slice may only move code into named helpers; a test that changes is a sign the slice is wrong.
- Order: small core functions first (`parse_seasons`, `run_jobs`), then the CLI and parsers, last the Statcast and MLB adapters (they decide what is downloaded).
- Evidence per slice is pasted into the commit message (gates and the complexity count).
- Evidence 1.3: `requests_for` old (git HEAD) vs new over 364 endpoints x 6 contexts = 2,184 comparisons, 0 differences; `parse_box_text` old vs new over 428 real box-account files, all four tables equal. (The comparison parsed real files, so it wrote duplicate quarantine files; the 50 duplicates were removed, 219 original cells remain.)

