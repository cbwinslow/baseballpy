"""Lazy, resettable singleton factories (no work at import time)."""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class LazySingleton(Generic[T]):  # noqa: UP046 - kept simple for 3.11 compatibility
    """Callable that builds its value on first call and can be reset (for tests/config changes)."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: T | None = None

    def __call__(self) -> T:
        """Return the shared instance, creating it on first use."""
        if self._value is None:
            self._value = self._factory()
        return self._value

    def reset(self) -> None:
        """Drop the cached instance so the next call rebuilds it."""
        self._value = None


def lazy_singleton(factory: Callable[[], T]) -> LazySingleton[T]:
    """Wrap ``factory`` in a :class:`LazySingleton`."""
    return LazySingleton(factory)
