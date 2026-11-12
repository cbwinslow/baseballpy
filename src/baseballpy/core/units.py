"""How a raw answer maps to its unit: the thing a segment writer stores as one piece (for MLB, a game).

A source registers a resolver (URL to unit id) next to its adapter. The converter and the rebuild use it to
keep all answers of one unit together; a source without a resolver has one unit per URL.
"""

from collections.abc import Callable, Mapping, Sequence

from baseballpy.core.responselog import Response
from baseballpy.core.segments import DatasetRows

UnitResolver = Callable[[str], str]

Normalize = Callable[[str, Sequence[Response]], Mapping[str, DatasetRows]]

_RESOLVERS: dict[str, UnitResolver] = {}
_NORMALIZERS: dict[str, Callable[[], Normalize]] = {}
_SEGMENT_DATASETS: dict[str, Callable[[], frozenset[str]]] = {}


def register_unit_resolver(source: str, resolver: UnitResolver) -> None:
    """Register (or replace) the URL-to-unit function of ``source``."""
    _RESOLVERS[source] = resolver


def unit_resolver(source: str) -> UnitResolver:
    """The resolver of ``source``: its registered one, else the URL itself."""
    return _RESOLVERS.get(source, str)


def register_normalizer(
    source: str,
    factory: Callable[[], Normalize],
    datasets: Callable[[], frozenset[str]] | None = None,
) -> None:
    """Register the factory of the parsing function of ``source`` (unit id and answers to rows).

    ``datasets`` returns the names of the datasets that function writes (a rebuild hides only their old files).
    """
    _NORMALIZERS[source] = factory
    if datasets is not None:
        _SEGMENT_DATASETS[source] = datasets


def segment_datasets(source: str) -> frozenset[str] | None:
    """The datasets ``source`` writes as segments; ``None`` when it did not say (then every dataset counts)."""
    factory = _SEGMENT_DATASETS.get(source)
    return factory() if factory is not None else None


def normalizer_for(source: str) -> Normalize:
    """The parsing function of ``source``; ``KeyError`` when the source does not write segments yet."""
    try:
        return _NORMALIZERS[source]()
    except KeyError:
        raise KeyError(f"{source} has no registered segment normalizer") from None


__all__ = [
    "UnitResolver",
    "normalizer_for",
    "register_normalizer",
    "register_unit_resolver",
    "segment_datasets",
    "unit_resolver",
]
