# Design
- Rule: a slice may only move code into named helpers; a test that changes is a sign the slice is wrong.
- Order: small core functions first (`parse_seasons`, `run_jobs`), then the CLI and parsers, last the Statcast and MLB adapters (they decide what is downloaded).
- Evidence per slice is pasted into the commit message (gates and the complexity count).
