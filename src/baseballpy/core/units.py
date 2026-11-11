"""How a raw answer maps to its unit: the thing a segment writer stores as one piece (for MLB, a game).

A source registers a resolver (URL to unit id) next to its adapter. The converter and the rebuild use it to
keep all answers of one unit together; a source without a resolver has one unit per URL.
"""

from collections.abc import Callable

UnitResolver = Callable[[str], str]

_RESOLVERS: dict[str, UnitResolver] = {}


def register_unit_resolver(source: str, resolver: UnitResolver) -> None:
    """Register (or replace) the URL-to-unit function of ``source``."""
    _RESOLVERS[source] = resolver


def unit_resolver(source: str) -> UnitResolver:
    """The resolver of ``source``: its registered one, else the URL itself."""
    return _RESOLVERS.get(source, str)


__all__ = ["UnitResolver", "register_unit_resolver", "unit_resolver"]
