# Design: Core Architecture & Protocol Interfaces

## Architectural Topology

```text
┌─────────────────┐      HTTP / File Bytes      ┌──────────────────┐
│    Extractor    │ ──────────────────────────> │    Normalizer    │
│  (httpx / cache)│                             │  (PyArrow schema)│
└─────────────────┘                             └──────────────────┘
                                                          │
                                            pyarrow.Table / RecordBatchReader
                                                          ▼
                                                ┌──────────────────┐
                                                │       Sink       │
                                                │ (DuckDB/dlt/etc) │
                                                └──────────────────┘
```

## Protocol Definitions

```python
from typing import Protocol, runtime_checkable, Iterator, AsyncIterator
import pyarrow as pa


@runtime_checkable
class ExtractorProtocol(Protocol):
    """Protocol for fetching raw data from endpoints with caching and rate limiting."""

    def extract(self, *args, **kwargs) -> bytes | str | dict: ...
    async def extract_async(self, *args, **kwargs) -> bytes | str | dict: ...


@runtime_checkable
class NormalizerProtocol(Protocol):
    """Protocol for coercing raw records into strongly-typed Arrow representations."""

    def schema(self) -> pa.Schema: ...
    def normalize(self, raw_data: bytes | str | dict | list) -> pa.Table: ...
    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict]
    ) -> pa.RecordBatchReader: ...


@runtime_checkable
class SinkProtocol(Protocol):
    """Protocol for ingesting Arrow data into database or file destinations."""

    def write(self, table: pa.Table, destination: str, **kwargs) -> int: ...
    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs) -> int: ...
```

## Licensing & Monorepo Rationale
- `baseballpy` is licensed under Apache-2.0.
- Retrosheet integration is abstracted so that `retrosheetpy` (GPL-3.0) can be used as a decoupled package or optional extra (`baseballpy[retrosheet]`) without forcing GPL infectious licensing on applications only using Statcast, MLB API, or Lahman.
