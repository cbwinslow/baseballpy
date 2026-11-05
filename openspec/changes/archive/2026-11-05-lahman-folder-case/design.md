# Design

- Rejected: lower-casing inside `ManifestTracker`/`LakeConfig` for every source (a global rule for one source's problem); importing `sources.lahman` from `core.migrate` (breaks the import boundary).
- Root cause of the miss: Windows case-insensitivity; the lesson is recorded in ADR 65.

## Evidence
- CI run 41988688786: `test_migrate_layout_dry_run_and_real_run`, `test_lahman_chunk_fetched_at_other_ref_is_refetched` and `test_statcast_adapter_protocol_and_seasons` failed on both Linux jobs, all Windows jobs and the other jobs passed.
- A Windows folder can be made case-sensitive (`fsutil file setCaseSensitiveInfo <dir> enable`); the full suite ran there with `--basetemp`: 1291 passed, 5 skipped. Not verified: that it reproduces every Linux difference (it did not fail before the fix because the fix was made first).
