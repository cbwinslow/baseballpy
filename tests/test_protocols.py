"""Tests for core protocol definitions and typing."""

from collections.abc import AsyncIterator
from typing import Any

import pyarrow as pa

from baseballpy.core.protocols import (
    ExtractorProtocol,
    LiveEventConsumerProtocol,
    NormalizerProtocol,
    SinkProtocol,
    StreamExtractorProtocol,
)


class DummyExtractor:
    def extract(self, *args: Any, **kwargs: Any) -> bytes:
        return b"test_data"

    async def extract_async(self, *args: Any, **kwargs: Any) -> bytes:
        return b"test_data"


class DummyStreamExtractor:
    async def stream_events(
        self, game_pk: int, *args: Any, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"game_pk": game_pk, "event": "pitch"}


class DummyModelConsumer:
    async def on_event(self, event: dict[str, Any] | pa.RecordBatch) -> None:
        pass


class DummyNormalizer:
    @property
    def schema(self) -> pa.Schema:
        return pa.schema([("id", pa.int32()), ("val", pa.string())])

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        return pa.table({"id": [1], "val": ["test"]})

    def normalize_stream(self, raw_data_iter: Any) -> pa.RecordBatchReader:
        tbl = pa.table({"id": [1], "val": ["test"]})
        return tbl.to_reader()


class DummySink:
    def write(self, table: pa.Table, destination: str, **kwargs: Any) -> int:
        return len(table)

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        total = 0
        for batch in reader:
            total += len(batch)
        return total


def test_protocol_runtime_checkable() -> None:
    extractor = DummyExtractor()
    stream_extractor = DummyStreamExtractor()
    consumer = DummyModelConsumer()
    normalizer = DummyNormalizer()
    sink = DummySink()

    assert isinstance(extractor, ExtractorProtocol)
    assert isinstance(stream_extractor, StreamExtractorProtocol)
    assert isinstance(consumer, LiveEventConsumerProtocol)
    assert isinstance(normalizer, NormalizerProtocol)
    assert isinstance(sink, SinkProtocol)


def test_normalizer_schema() -> None:
    normalizer = DummyNormalizer()
    schema = normalizer.schema
    assert "id" in schema.names
    assert "val" in schema.names
    assert schema.field("id").type == pa.int32()


def test_sink_write() -> None:
    normalizer = DummyNormalizer()
    sink = DummySink()
    tbl = normalizer.normalize(b"raw")
    rows = sink.write(tbl, "dummy.db")
    assert rows == 1
