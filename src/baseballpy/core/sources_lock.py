"""Pinned upstream refs so GitHub-hosted sources are reproducible.

The lock (``sources_lock.json``) maps each GitHub-hosted source to ``{repo, ref}`` where ``ref``
is a commit SHA. A ``$BASEBALLPY_HOME/sources.lock.json`` file (written by ``refs update`` when
the packaged lock is not writable) overrides the packaged one, and
``BASEBALLPY_RETROSHEET_REF`` / ``BASEBALLPY_CHADWICK_REF`` / ``BASEBALLPY_LAHMAN_REF`` override
individual refs (use a branch name such as ``master`` to float on purpose).

Lahman data comes only from ``cbwinslow/lahman-database-csv`` (see the lahman-database spec);
``chadwickbureau/baseballdatabank`` must never appear here.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LakeConfig, get_default_base_dir
from baseballpy.core.http import HttpClient, get_http_client

logger = logging.getLogger(__name__)

PACKAGED_LOCK = Path(__file__).with_name("sources_lock.json")
LOCK_FILENAME = "sources.lock.json"
RAW_HOST = "https://raw.githubusercontent.com"
API_HOST = "https://api.github.com"

#: lock key -> environment variable that overrides its ref
ENV_OVERRIDES = {
    "retrosheet": "BASEBALLPY_RETROSHEET_REF",
    "chadwick_register": "BASEBALLPY_CHADWICK_REF",
    "lahman": "BASEBALLPY_LAHMAN_REF",
}
#: lock key -> environment variable that overrides its repository (own fork / mirror)
REPO_OVERRIDES = {"lahman": "BASEBALLPY_LAHMAN_REPO"}
FORBIDDEN_REPOS = ("baseballdatabank",)
_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SourceRef:
    """A GitHub repository pinned at ``ref`` (a commit SHA, or a branch when floating)."""

    key: str
    repo: str
    ref: str

    @property
    def pinned(self) -> bool:
        """True when ``ref`` is a full commit SHA (immutable)."""
        return bool(_SHA.match(self.ref))

    def raw_base(self) -> str:
        """``https://raw.githubusercontent.com/<repo>/<ref>`` (append ``/<path>``)."""
        return f"{RAW_HOST}/{self.repo}/{self.ref}"

    def raw_url(self, path: str) -> str:
        """Raw file URL at the pinned ref."""
        return f"{self.raw_base()}/{path.lstrip('/')}"


def user_lock_path(home: Path | None = None) -> Path:
    """Per-lake override location for the lock file."""
    return (home or get_default_base_dir()) / LOCK_FILENAME


def _read(path: Path) -> dict[str, dict[str, str]] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"unreadable sources lock {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"sources lock {path} must be a JSON object")
    return {k: dict(v) for k, v in loaded.items() if isinstance(v, dict)}


def load_lock(home: Path | None = None) -> dict[str, dict[str, str]]:
    """The effective lock: lake-level override if present, else the packaged lock."""
    return _read(user_lock_path(home)) or _read(PACKAGED_LOCK) or {}


def get_source_ref(key: str, home: Path | None = None) -> SourceRef:
    """Resolve a source's repo and ref (env override > lock)."""
    lock = load_lock(home)
    if key not in lock:
        raise KeyError(f"no pinned ref for {key!r}; known: {sorted(lock)}")
    repo = os.getenv(REPO_OVERRIDES.get(key, ""), "") or lock[key]["repo"]
    if any(bad in repo.lower() for bad in FORBIDDEN_REPOS):
        raise ValueError(
            f"{repo!r} is not an allowed source for {key}: its data stops around 2023. "
            "Use cbwinslow/lahman-database-csv, your own fork, or LahmanSource.import_archive()."
        )
    ref = os.getenv(ENV_OVERRIDES.get(key, ""), "") or lock[key]["ref"]
    return SourceRef(key=key, repo=repo, ref=ref)


def write_lock(lock: dict[str, dict[str, str]], config: LakeConfig | None = None) -> Path:
    """Persist ``lock``: the packaged file when writable, else the lake-level override."""
    payload = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    user = user_lock_path((config or LakeConfig()).home)
    for target in [user, PACKAGED_LOCK] if user.exists() else [PACKAGED_LOCK, user]:
        try:
            with atomic_write(target, mode="w") as part:
                part.write_text(payload, encoding="utf-8")
        except OSError as exc:
            logger.info("could not write lock to %s (%s); trying the next location", target, exc)
            continue
        return target
    raise OSError("could not write the sources lock to any location")


@dataclass(frozen=True)
class RefChange:
    """One source's old and newly resolved ref."""

    key: str
    repo: str
    old: str
    new: str

    @property
    def changed(self) -> bool:
        """True when upstream moved past the locked ref."""
        return self.old != self.new


def resolve_latest_sha(repo: str, http: HttpClient | None = None) -> str:
    """Latest commit SHA of the default branch (``GITHUB_TOKEN`` lifts the 60 req/h limit)."""
    client = http or get_http_client()
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    result = client.get_sync(f"{API_HOST}/repos/{repo}/commits?per_page=1", headers=headers)
    commits = result.json()
    if not (isinstance(commits, list) and commits and isinstance(commits[0], dict)):
        raise ValueError(f"unexpected GitHub response for {repo}: {str(commits)[:200]}")
    sha = commits[0].get("sha")
    if not isinstance(sha, str) or not _SHA.match(sha):
        raise ValueError(f"GitHub returned no commit SHA for {repo}")
    return sha


def update_lock(
    http: HttpClient | None = None,
    config: LakeConfig | None = None,
    *,
    dry_run: bool = False,
) -> list[RefChange]:
    """Resolve the latest SHA of every locked repo and rewrite the lock (unless ``dry_run``)."""
    cfg = config or LakeConfig()
    lock = load_lock(cfg.home)
    changes: list[RefChange] = []
    new_lock = {k: dict(v) for k, v in lock.items()}
    for key, entry in sorted(lock.items()):
        latest = resolve_latest_sha(entry["repo"], http)
        changes.append(RefChange(key, entry["repo"], entry["ref"], latest))
        new_lock[key]["ref"] = latest
        new_lock[key]["resolved_at"] = date.today().isoformat()
    if not dry_run and any(c.changed for c in changes):
        write_lock(new_lock, cfg)
    return changes
