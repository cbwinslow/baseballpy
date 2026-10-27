## ADDED Requirements

### Requirement: Resumable Backfill
A backfill MUST run from a plan that orders reference snapshots, then seasons ascending per source, MUST resume after interruption from the dataset manifests without re-downloading completed pieces, MUST check free disk against the estimate before starting, and MUST write a per-piece summary (rows, bytes, duration, status).
