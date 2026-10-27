## ADDED Requirements

### Requirement: Cancellation Is Not Success
`track`/`async_track` MUST record `CANCELLED` for `CancelledError`/`KeyboardInterrupt` and `FAILURE` for other exceptions, then re-raise.

### Requirement: Cache Hit Accuracy
Every source MUST set `cache_hit` true when no network request was made.

### Requirement: Lazy Logger
The default audit logger MUST be created on first use so `BASEBALLPY_HOME` set after import is honored.
