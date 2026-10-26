"""baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer.

Unified extraction, normalization, and ingestion for Statcast, MLB API, Lahman,
Chadwick Registers, and Retrosheet into DuckDB, Polars, PyArrow, and dlt.
"""

from baseballpy.core.protocols import (
    ExtractorProtocol,
    NormalizerProtocol,
    SinkProtocol,
)

__version__ = "0.1.0"
__all__ = [
    "ExtractorProtocol",
    "NormalizerProtocol",
    "SinkProtocol",
    "__version__",
]
