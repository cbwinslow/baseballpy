"""Fetch each request once when several datasets are cut from the same answer.

Six MLB game datasets come from one boxscore URL and four from one live-feed URL. They are
ingested side by side, so a game's answer is asked for by several threads within moments. A
:class:`Coalescer` lets the first caller do the work, makes the others wait for that result, and
keeps the last few results so a caller that is slightly behind still finds it. Failures are not
kept: the next caller tries again.
"""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from concurrent.futures import Future
from typing import Generic, TypeVar

T = TypeVar("T")


class Coalescer(Generic[T]):
    """Single-flight memo of the last ``size`` results, safe across threads."""

    def __init__(self, size: int = 128) -> None:
        self._size = size
        self._lock = threading.Lock()
        self._items: OrderedDict[Hashable, Future[T]] = OrderedDict()

    def get(self, key: Hashable, fetch: Callable[[], T]) -> T:
        """The result for ``key``: computed once by one caller, shared with the others."""
        with self._lock:
            future = self._items.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._items[key] = future
                while len(self._items) > self._size:
                    self._items.popitem(last=False)
            else:
                self._items.move_to_end(key)
        if owner:
            try:
                future.set_result(fetch())
            except BaseException as exc:
                with self._lock:
                    if self._items.get(key) is future:
                        del self._items[key]  # never keep a failure
                future.set_exception(exc)
                raise
        return future.result()
