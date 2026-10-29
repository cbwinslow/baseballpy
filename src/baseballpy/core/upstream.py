"""Upstream fingerprints and the one shared rule for "is my cached copy still current?" (ADR 43).

A fingerprint is whatever the provider offers to say that a file changed: a git blob or commit SHA
for GitHub sources, an ETag or Last-Modified for plain HTTP, the content hash for API payloads. It is
stored in the manifest entry of the raw file (``RawStore.put(upstream=...)``). :func:`is_current` is
the single decision every source uses; sources only supply what they know (the expected upstream
fingerprint, a probe that asks upstream, the time-to-live).
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from baseballpy.core.freshness import is_fresh

logger = logging.getLogger(__name__)

#: fingerprint kinds in use
GIT_COMMIT = "git_commit"
GIT_BLOB = "git_blob"
ETAG = "etag"
LAST_MODIFIED = "last_modified"
CONTENT_SHA256 = "content_sha256"


@dataclass(frozen=True)
class Fingerprint:
    """What identifies one version of an upstream file.

    ``origin`` says where it came from (``owner/repo:path`` for git, the URL otherwise); it is
    informational and not part of the comparison.
    """

    kind: str
    value: str
    origin: str = ""

    def matches(self, other: "Fingerprint") -> bool:
        """True when both name the same version (kind and value; ``origin`` is ignored)."""
        return self.kind == other.kind and self.value == other.value

    def to_dict(self) -> dict[str, str]:
        """JSON form stored in manifest entries."""
        data = {"kind": self.kind, "value": self.value}
        if self.origin:
            data["origin"] = self.origin
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Fingerprint | None":
        """The fingerprint stored as ``data`` (``None`` when it is not a valid one)."""
        kind, value = data.get("kind"), data.get("value")
        if isinstance(kind, str) and isinstance(value, str) and kind and value:
            return cls(kind, value, str(data.get("origin") or ""))
        return None


def stored_fingerprint(entry: Mapping[str, Any] | None) -> Fingerprint | None:
    """The fingerprint recorded in a manifest entry.

    Reads the ``upstream`` field; entries written before it existed fall back to a ``sha`` (the
    Chadwick commit chunk) or an ``etag``.
    """
    if not entry:
        return None
    upstream = entry.get("upstream")
    if isinstance(upstream, Mapping) and (fp := Fingerprint.from_dict(upstream)) is not None:
        return fp
    if sha := entry.get("sha"):
        return Fingerprint(GIT_COMMIT, str(sha))
    if etag := entry.get("etag"):
        return Fingerprint(ETAG, str(etag))
    return None


def is_current(
    entry: Mapping[str, Any] | None,
    *,
    refresh: bool = False,
    expected: Fingerprint | None = None,
    probe: Callable[[], Fingerprint | None] | None = None,
    on_confirmed: Callable[[], None] | None = None,
    ttl_seconds: float | None = None,
    season: int | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> bool:
    """Decide whether the cached copy described by manifest ``entry`` can be served as is.

    In order:

    1. ``refresh``, a missing entry or one that is not COMPLETED: not current.
    2. ``expected`` (the upstream fingerprint the caller already knows is wanted, for example the
       pinned commit or the file's blob SHA in the pinned tree): current exactly when the stored
       fingerprint matches it. No time-to-live applies; this is the reproducible mode.
    3. Within the time-to-live (``ttl_seconds``; ``None`` = never expires; a season before the
       current year is immutable): current.
    4. Otherwise ask upstream with ``probe`` (only now, so a fresh copy costs no request): a
       matching answer is current (``on_confirmed`` then lets the caller renew the timestamp); a
       different one is stale; no answer (the probe returned ``None``) is logged and the copy is
       served rather than failing offline users.
    5. No probe: stale.
    """
    if refresh or not entry or entry.get("status") != "COMPLETED":
        return False
    stored = stored_fingerprint(entry)
    if expected is not None:
        return stored is not None and stored.matches(expected)
    if is_fresh(entry, ttl_seconds=ttl_seconds, season=season, today=today, now=now):
        return True
    if probe is None:
        return False
    latest = probe()
    if latest is None:
        logger.warning("could not ask upstream whether the cached copy is current; serving it")
        return True
    if stored is not None and stored.matches(latest):
        if on_confirmed is not None:
            on_confirmed()
        return True
    return False


__all__ = [
    "CONTENT_SHA256",
    "ETAG",
    "GIT_BLOB",
    "GIT_COMMIT",
    "LAST_MODIFIED",
    "Fingerprint",
    "is_current",
    "stored_fingerprint",
]
