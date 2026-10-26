# Design: Core Runtime Enhancements

## 1. Directory Layout & Partitioned Cache
```text
~/.baseballpy/ (overridable via BASEBALLPY_CACHE_DIR / BASEBALLPY_HOME)
├── cache/
│   ├── statcast/
│   ├── mlb_api/
│   ├── chadwick/
│   ├── lahman/
│   └── retrosheet/
├── logs/
│   └── audit.jsonl
└── quarantine/
```

## 2. Audit Telemetry Schema
```python
import msgspec


class AuditEvent(msgspec.Struct):
    timestamp_utc: str
    operation: str
    source: str
    status: str  # SUCCESS, FAILURE, RETRY
    records_count: int = 0
    duration_seconds: float = 0.0
    throughput_rps: float = 0.0
    cache_hit: bool = False
    endpoint: str = ""
    destination: str = ""
    error: str | None = None
```

## 3. Benchmark Context Manager & Decorator
Provides a clean context manager:
```python
with audit_logger.track(operation="statcast_search", source="statcast") as tracker:
    data = fetch_data()
    tracker.set_records(len(data))
    tracker.set_cache_hit(False)
```
Automatically handles timing, records count, throughput calculation, error capture, and appending to `audit.jsonl`.
