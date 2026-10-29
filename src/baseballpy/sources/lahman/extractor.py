"""Extractor for the SABR Lahman Baseball Database from the owner's GitHub repository.

Lahman data comes only from this repository (or from a user-supplied archive via
``LahmanSource.import_archive``). The ``chadwickbureau/baseballdatabank`` repository must
never be used: its data stops around 2023.

Every raw file has exactly one manifest entry (``raw/lahman/<Table>/manifest.json``, key
``<Table>.csv``) holding its sha256, size, data-row count, the commit it was fetched at and the
provider's git fingerprint of that file. Whether a raw file is current is decided by the shared
``core.upstream.is_current`` (ADR 43): a file is current when its stored fingerprint equals the blob
SHA the pinned git tree lists for it; with no tree available (offline and not yet listed) the pinned
commit decides. Files the user supplied are authoritative until ``refresh``.
"""

import logging
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker, cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.documents import keep_documents, tree_or_none
from baseballpy.core.github_tree import TreeEntry
from baseballpy.core.http import (
    HttpClient,
    HttpResult,
    HttpStatusError,
    TransportError,
    get_http_client,
)
from baseballpy.core.sources_lock import get_source_ref
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import GIT_BLOB, Fingerprint, is_current
from baseballpy.sources.lahman.schema import LahmanTable, canonical_table_name

logger = logging.getLogger(__name__)

#: Default (pinned) data URL; instances derive theirs from the lock / env override.
LOCAL_IMPORT = "local-import"
LAHMAN_GITHUB_BASE = f"{get_source_ref('lahman').raw_base()}/data"
#: raw dataset folder holding the provider's documentation (``raw/lahman/documents/``)
DOCUMENT_DATASET = "documents"
#: documentation files kept from the git tree (the data dictionary is renamed every release year)
DOCUMENT_PATTERNS = ("README.md", "LICENSE", "data/readme*.txt")


class LahmanSourceError(RuntimeError):
    """The configured Lahman remote could not deliver a table (no other repository is tried)."""


def data_rows(content: bytes) -> int:
    """Rows of a CSV file without its header line."""
    lines = content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0)
    return max(0, lines - 1)


class LahmanExtractor:
    """Extracts raw CSV files for the Lahman database with local caching and atomic guarantees."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.raw = RawStore(self.cache_config)
        self.source_ref = get_source_ref("lahman", self.cache_config.home)
        self.base_url = f"{self.source_ref.raw_base()}/data"
        self._tree: list[TreeEntry] | None = None
        self._tree_listed = False
        self._documents_done = False
        self._mixed_warned = False
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "lahman")

    # -- manifest and paths ----------------------------------------------------------------

    def manifest_for(self, table_name: str | LahmanTable) -> ManifestTracker:
        """Per-table raw manifest at ``raw/lahman/<Table>/manifest.json``."""
        return self.cache_config.dataset_manifest("lahman", str(table_name), "raw")

    def get_raw_path(self, table_name: str | LahmanTable) -> Path:
        """Return local path to raw CSV file (``raw/lahman/<Table>/<Table>.csv``)."""
        return self.cache_config.raw_dir("lahman", str(table_name)) / f"{table_name}.csv"

    def file_entry(self, table_name: str | LahmanTable) -> dict[str, object] | None:
        """The one manifest entry of a raw file (``None`` when it was never stored)."""
        return self.manifest_for(table_name).get_chunk(f"{table_name}.csv")

    def is_local(self, table_name: str | LahmanTable) -> bool:
        """True when the raw file came from a user-supplied archive."""
        entry = self.file_entry(table_name)
        return entry is not None and entry.get("source_ref") == LOCAL_IMPORT

    # -- the provider's git tree -----------------------------------------------------------

    def tree_entries(self) -> list[TreeEntry] | None:
        """The git tree of the pinned ref (listed once per extractor; ``None`` when unavailable)."""
        if not self._tree_listed:
            self._tree_listed = True
            self._tree = tree_or_none(
                self.source_ref, self.cache_config, self.http, what="Lahman files"
            )
        return self._tree

    def blob_fingerprint(self, table_name: str | LahmanTable) -> Fingerprint | None:
        """The git blob fingerprint the tree lists for ``data/<Table>.csv`` (``None`` if unknown)."""
        path = f"data/{table_name}.csv"
        for entry in self.tree_entries() or ():
            if entry.path == path:
                return Fingerprint(
                    GIT_BLOB, entry.sha, origin=f"{self.source_ref.repo}:{entry.path}"
                )
        return None

    # -- currency ---------------------------------------------------------------------------

    def is_current(self, table_name: str | LahmanTable, refresh: bool = False) -> bool:
        """Whether the raw file can be served without asking the provider for the file again."""
        path = self.get_raw_path(table_name)
        entry = self.file_entry(table_name)
        if entry is None or not path.exists() or path.stat().st_size == 0:
            return False
        if entry.get("source_ref") == LOCAL_IMPORT:
            return not refresh  # user-supplied data is authoritative until an explicit refresh
        expected = self.blob_fingerprint(table_name)
        if expected is not None:
            return is_current(entry, refresh=refresh, expected=expected)
        # no tree to compare with (offline and never listed): the pinned commit decides
        if entry.get("source_ref") != self.source_ref.ref:
            return False
        return is_current(entry, refresh=refresh, ttl_seconds=None)

    # -- documents and mixed releases ----------------------------------------------------------

    def ensure_documents(self) -> None:
        """Keep the provider's README, licence and data dictionary in ``raw/lahman/documents/``."""
        if self._documents_done or not self.cache_config.enabled:
            return
        self._documents_done = True
        entries = self.tree_entries()
        if entries is None:
            return
        keep_documents(
            raw=self.raw,
            http=self.http,
            ref=self.source_ref,
            entries=entries,
            source="lahman",
            dataset=DOCUMENT_DATASET,
            patterns=DOCUMENT_PATTERNS,
            source_ref=self.source_ref.ref,
            only_missing=True,
        )

    def supplied_tables(self) -> list[str]:
        """Tables whose raw file came from a user-supplied archive."""
        root = self.cache_config.raw_root / "lahman"
        if not root.is_dir():
            return []
        return sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir() and d.name != DOCUMENT_DATASET and self.is_local(d.name)
        )

    def _warn_if_mixed(self, table_name: str) -> None:
        """Warn once when a table is fetched from the mirror next to supplied tables."""
        if self._mixed_warned:
            return
        supplied = self.supplied_tables()
        if supplied:
            self._mixed_warned = True
            logger.warning(
                "mixed Lahman release: %d table(s) were imported from a supplied archive (%s) and "
                "%s is now fetched from the mirror at %s; the tables may come from different "
                "releases. Import the complete supplied release, or refresh from the mirror.",
                len(supplied),
                ", ".join(supplied[:5]) + (", ..." if len(supplied) > 5 else ""),
                table_name,
                self.source_ref.ref[:10],
            )

    # -- extraction ---------------------------------------------------------------------------

    def _store(self, name: str, result: HttpResult) -> bytes:
        content = result.content
        if self.cache_config.enabled:
            self.raw.put(
                "lahman",
                name,
                f"{name}.csv",
                content,
                source_ref=self.source_ref.ref,
                etag=result.etag or "",
                upstream=self.blob_fingerprint(name),
                records=data_rows(content),
                extra={
                    "source": f"{self.base_url}/{name}.csv",
                    "origin": f"{self.source_ref.repo}@{self.source_ref.ref}",
                },
            )
        return content

    def _hint(self, name: str, exc: Exception) -> LahmanSourceError:
        return LahmanSourceError(
            f"could not fetch Lahman table {name} from {self.source_ref.repo}@{self.source_ref.ref} "
            f"({exc}). No other repository is tried; download the release yourself and call "
            "LahmanSource.import_archive(path) or point BASEBALLPY_LAHMAN_REPO at your own fork."
        )

    def _get(self, url: str, name: str) -> HttpResult:
        try:
            return self.http.get_sync(url)
        except (HttpStatusError, TransportError) as exc:
            raise self._hint(name, exc) from exc

    def extract_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> bytes:
        """Extract a single Lahman table CSV, hitting cache if it is current."""
        name_str = canonical_table_name(table_name)
        url = f"{self.base_url}/{name_str}.csv"
        with default_audit_logger.track(
            operation="lahman_extract_table",
            source="lahman",
            endpoint=url,
            destination=str(self.get_raw_path(name_str)),
        ) as tracker:
            if self.is_current(name_str, refresh):
                content = self.get_raw_path(name_str).read_bytes()
                tracker.set_cache_hit(True)
                tracker.set_records(data_rows(content))
                if not self.is_local(name_str):
                    self.ensure_documents()
                return content

            self._warn_if_mixed(name_str)
            content = self._store(name_str, self._get(url, name_str))
            self.ensure_documents()
            tracker.set_cache_hit(False)
            tracker.set_records(data_rows(content))
            return content


__all__ = [
    "DOCUMENT_DATASET",
    "DOCUMENT_PATTERNS",
    "LAHMAN_GITHUB_BASE",
    "LOCAL_IMPORT",
    "LahmanExtractor",
    "LahmanSourceError",
    "data_rows",
]
