"""Core protocol interfaces separating Extract, Parse/Schema, and Sink stages."""

from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol, runtime_checkable

import pyarrow as pa


@runtime_checkable
class ExtractorProtocol(Protocol):
    """Protocol for fetching raw data from endpoints with caching and rate limiting."""

    def extract(self, *args: Any, **kwargs: Any) -> bytes | str | dict[str, Any] | list[Any]:
        """Synchronously extract raw payload."""
        ...

    async def extract_async(
        self, *args: Any, **kwargs: Any
    ) -> bytes | str | dict[str, Any] | list[Any]:
        """Asynchronously extract raw payload."""
        ...


@runtime_checkable
class StreamExtractorProtocol(Protocol):
    """Protocol for real-time live event streaming from active games."""

    async def stream_events(
        self, game_pk: int, *args: Any, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield real-time play events and state diffs as they occur."""
        ...


@runtime_checkable
class NormalizerProtocol(Protocol):
    """Protocol for coercing raw records into strongly-typed Arrow representations."""

    @property
    def schema(self) -> pa.Schema:
        """Return the canonical PyArrow schema."""
        ...

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        """Coerce raw payload into a validated, strongly-typed PyArrow Table."""
        ...

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Coerce a stream of raw payloads into a streaming PyArrow RecordBatchReader."""
        ...


@runtime_checkable
class LiveEventConsumerProtocol(Protocol):
    """Protocol for downstream consumers/models operating on live event streams."""

    async def on_event(self, event: dict[str, Any] | pa.RecordBatch) -> None:
        """Consume a single live event or pitch batch (e.g. inference, win prob update)."""
        ...


@runtime_checkable
class SinkProtocol(Protocol):
    """Protocol for ingesting Arrow data into database or file destinations."""

    def write(self, table: pa.Table, destination: str, **kwargs: Any) -> int:
        """Write a PyArrow Table to the destination. Returns number of records written."""
        ...

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        """Stream a RecordBatchReader to the destination. Returns total records written."""
        ...
