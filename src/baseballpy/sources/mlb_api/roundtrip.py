"""MLB Stats API raw answers for the round-trip check, flattened by the ingest's own code.

Each sampled raw answer is decoded (:func:`.game_segments.decode_body`), walked with the endpoint's
``records`` path (:func:`.flatten.iter_records`, :func:`.generic.stats_payload` for a hydrate page) and given
the request's fan-out columns (:func:`.endpoints.request_extra`), exactly as the normalizer receives it. The
flattened scalars become text (:func:`baseballpy.core.roundtrip_json.records_table`) and the generic check
compares them with the stored cells. The normalizer itself is not run: its typing is what is checked, and it
would write to the quarantine.

Where the answers are:

* the per-game datasets are cut from game answers kept in the response log (ADR 95,
  ``raw/mlb_api/season=Y/seg-NNNN.parquet``); a sampled unit is one game, and of several answers for one URL
  (a refreshed segment) the one the processed rows name in ``_raw_sha256`` is used;
* every other dataset keeps one file per request (``<id>.json.gz``, ``<id>.p<n>.json.gz`` per page).
"""

import gzip
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from baseballpy.core.config import MANIFEST_NAME, LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.responselog import Response
from baseballpy.core.roundtrip import (
    RawNote,
    RawSample,
    RoundtripRefusedError,
    raw_files,
    spread,
)
from baseballpy.core.roundtrip_json import (
    SegmentUnit,
    lineage_hashes,
    records_table,
    segment_responses,
    segment_units,
)
from baseballpy.core.stores import manifest_key
from baseballpy.sources.mlb_api.endpoints import BY_NAME, MlbEndpoint, request_extra
from baseballpy.sources.mlb_api.flatten import iter_records
from baseballpy.sources.mlb_api.game_segments import (
    SOURCE,
    UrlGroup,
    decode_body,
    game_url_groups,
)
from baseballpy.sources.mlb_api.generic import (
    HYDRATE_MARKER,
    VIA_DIRECT,
    VIA_HYDRATE,
    VIA_KEY,
    stats_payload,
)

SUFFIXES = (".json", ".json.gz")
#: ``--full`` flattens every game answer of the chosen seasons into text tables held at once, so it is refused
#: above this many bytes of raw segment files (ADR 114: memory must stay bounded; a season is ~17 GB)
FULL_GAME_LIMIT = 256 * 1024**2


class FullCheckTooLargeError(RoundtripRefusedError):
    """``--full`` would hold more raw game answers in memory than the stated limit."""


_PAGE = re.compile(r"\.p\d+$")


def request_ident(file_name: str) -> str:
    """The request id of a raw file name (``x.json.gz``, ``x.p3.json``, ``x.hydrate.p0.json.gz`` -> ``x``)."""
    stem = _PAGE.sub("", file_name.removesuffix(".gz").removesuffix(".json"))
    return stem.removesuffix(HYDRATE_MARKER.rstrip("."))


def _sample(
    endpoint: MlbEndpoint,
    payload: Any,
    extra: dict[str, str],
    label: str,
    season: int | None,
    stem: str,
) -> RawSample | None:
    """The records of one answer as a text table, as the normalizer would get them (``None``: no record)."""
    records = [{**extra, **record} for record in iter_records(payload, endpoint.records)]
    if not records:
        return None
    return RawSample(label, season, records_table(records), stem)


def _file_sample(endpoint: MlbEndpoint, season: int | None, path: Path) -> RawSample | None:
    data = path.read_bytes()
    if path.name.endswith(".gz"):
        data = gzip.decompress(data)
    payload = decode_body(data)
    if HYDRATE_MARKER in path.name:
        payload = stats_payload(
            payload
        )  # the pool fallback's people answer, in the /v1/stats shape
    ident = request_ident(path.name)
    return _sample(endpoint, payload, request_extra(endpoint, ident), path.name, season, ident)


def _pick(answers: list[Response], used: frozenset[str]) -> Response | None:
    """The answer the stored rows were made from; else the newest one (the stored rows name none)."""
    named = [a for a in answers if a.sha256 in used]
    if named:
        return named[0]
    ok = [a for a in answers if a.status == 200]
    return max(ok, key=lambda a: a.fetched_at) if ok else None


@dataclass(frozen=True)
class _Answer:
    """One sampled raw answer: a loose file, or one game of a raw segment."""

    season: int | None
    path: Path | None = None
    unit: SegmentUnit | None = None


def _route_of(config: LakeConfig, spec: DatasetSpec, season: int | None, ident: str) -> str:
    """Which route filled a pool chunk: the manifest's ``via``, else direct (the extractor's own rule)."""
    path = config.processed_dir(spec.source, spec.name) / MANIFEST_NAME
    entry = (
        config.manifest_for_path(path).get_chunk(manifest_key(ident, season))
        if path.exists()
        else None
    )
    return str((entry or {}).get(VIA_KEY) or VIA_DIRECT)


def _one_route(
    config: LakeConfig, spec: DatasetSpec, files: list[tuple[int | None, Path]]
) -> list[tuple[int | None, Path]]:
    """The pages of a league-wide pool kept by both routes, limited to the route its stored rows came from.

    ``/v1/stats`` pages (``<id>.p<n>``) and the hydrate fallback's pages (``<id>.hydrate.p<n>``) answer the
    same request with different row sets (projected hitting 2024: 3,709 against 652); a chunk holds one.
    """
    direct = {(s, request_ident(p.name)) for s, p in files if HYDRATE_MARKER not in p.name}
    hydrate = {(s, request_ident(p.name)) for s, p in files if HYDRATE_MARKER in p.name}
    route = {key: _route_of(config, spec, *key) for key in direct & hydrate}
    keep = []
    for season, path in files:
        key = (season, request_ident(path.name))
        if key in route:
            wanted = VIA_HYDRATE if HYDRATE_MARKER in path.name else VIA_DIRECT
            if route[key] != wanted:
                continue
        keep.append((season, path))
    return keep


def _group_of(endpoint: MlbEndpoint) -> UrlGroup | None:
    return next((g for g in game_url_groups() if endpoint in g.endpoints), None)


def _game_of(spec: DatasetSpec, path: Path) -> str:
    """The game pk a loose file of a per-game dataset answers (``""`` for a name that carries none)."""
    try:
        return request_extra(BY_NAME[spec.name], request_ident(path.name)).get("game_pk", "")
    except (KeyError, ValueError):
        return ""


def _candidates(
    config: LakeConfig, spec: DatasetSpec, group: UrlGroup | None, season: int | None
) -> list[_Answer]:
    """Every raw answer of the dataset: games of the response log first, loose files of the other seasons."""
    units = (
        [u for u in segment_units(config, SOURCE, season) if u.unit.isdigit()]
        if group is not None
        else []
    )
    logged = {(u.season, u.unit) for u in units}
    # a loose file of a game the response log does not hold (a half-migrated season) is still an answer to check
    files = [
        (s, p)
        for s, p in raw_files(config, spec, SUFFIXES, season)
        if group is None or (s, _game_of(spec, p)) not in logged
    ]
    loose = [_Answer(s, path=p) for s, p in _one_route(config, spec, files)]
    return [_Answer(u.season, unit=u) for u in units] + loose


def raw_reader(
    config: LakeConfig, spec: DatasetSpec, sample_files: int, season: int | None, every: bool
) -> list[RawSample | RawNote]:
    """The raw answers of one MLB dataset as text tables (sampled, or every answer of ``season``).

    :class:`RawNote` items say what could not be checked (a listed game with no answer in its segment, a
    season whose stored rows name none of the raw answers).
    """
    endpoint = BY_NAME.get(spec.name)
    if endpoint is None:
        return []  # a hand-written dataset: no registry entry says how its answers are flattened
    group = _group_of(endpoint)
    candidates = _candidates(config, spec, group, season)
    if every:
        _refuse_if_too_large(config, candidates)
        return _read(config, spec, endpoint, group, candidates)
    # an answer with no record (a sport without games that season) proves nothing: another one is sampled
    out: list[RawSample | RawNote] = []
    tried: set[_Answer] = set()
    while (
        True
    ):  # ends when the sample is full or every answer was tried (empty answers are small and fast)
        need = sample_files - len(out)
        rest = [c for c in candidates if c not in tried]
        if need <= 0 or not rest:
            break
        batch = spread(rest, need)
        tried.update(batch)
        out += _read(config, spec, endpoint, group, batch)
    return out


def _refuse_if_too_large(config: LakeConfig, candidates: list[_Answer]) -> None:
    """Refuse a full read of raw answers (game segments and loose files) above :data:`FULL_GAME_LIMIT` bytes."""
    files = {(u.season, u.raw_file) for c in candidates if (u := c.unit) is not None}
    size = sum(
        (config.raw_root / SOURCE / f"season={season}" / name).stat().st_size
        for season, name in files
    ) + sum(c.path.stat().st_size for c in candidates if c.path is not None)
    if size > FULL_GAME_LIMIT:
        raise FullCheckTooLargeError(
            f"--full would read {size / 1024**2:,.0f} MiB of raw answers at once (limit "
            f"{FULL_GAME_LIMIT / 1024**2:,.0f} MiB, ADR 114); compare a sample instead (leave out --full, "
            "raise --files)"
        )


def _read(
    config: LakeConfig,
    spec: DatasetSpec,
    endpoint: MlbEndpoint,
    group: UrlGroup | None,
    chosen: list[_Answer],
) -> list[RawSample | RawNote]:
    """The chosen answers as text tables (answers without a record give none)."""
    out: list[RawSample | RawNote] = []
    games: dict[tuple[int, str], list[str]] = {}
    for answer in chosen:
        if answer.path is not None:
            sample = _file_sample(endpoint, answer.season, answer.path)
            out += [sample] if sample is not None else []
        elif answer.unit is not None:
            games.setdefault((answer.unit.season, answer.unit.raw_file), []).append(
                answer.unit.unit
            )
    if group is not None:
        out += _game_samples(config, spec, endpoint, group, games)
    return out


def _game_samples(
    config: LakeConfig,
    spec: DatasetSpec,
    endpoint: MlbEndpoint,
    group: UrlGroup,
    games: dict[tuple[int, str], list[str]],
) -> list[RawSample | RawNote]:
    """The sampled games of each raw segment (one read of the segment per file, not per game)."""
    out: list[RawSample | RawNote] = []
    used: dict[int, frozenset[str]] = {}
    absent: dict[int, list[str]] = {}
    unnamed: dict[int, int] = {}
    for (season, raw_file), pks in games.items():
        if season not in used:
            used[season] = lineage_hashes(config, spec, season)
        urls = {pk: group.url(int(pk)) for pk in pks}
        answers = segment_responses(config, SOURCE, season, raw_file, urls.values())
        for pk, url in urls.items():
            found = answers.get(url, [])
            if (
                not found
            ):  # the commit line lists the game but the segment holds no answer: not a 404
                absent.setdefault(season, []).append(pk)
                continue
            if not any(a.sha256 in used[season] for a in found):
                unnamed[season] = unnamed.get(season, 0) + 1
            answer = _pick(found, used[season])
            if answer is None or answer.status != 200:
                continue  # a recorded 404: the game has nothing at this URL
            label = f"season={season}/{raw_file}#{pk}"
            sample = _sample(endpoint, decode_body(answer.body), {"game_pk": pk}, label, season, pk)
            out += [sample] if sample is not None else []
    for season, pks in sorted(absent.items()):
        shown = ", ".join(pks[:3]) + (", ..." if len(pks) > 3 else "")
        out.append(
            RawNote(
                f"season={season}: {len(pks)} game(s) listed by the commit line have no answer in the raw "
                f"segment ({shown}); their stored rows were not checked"
            )
        )
    for season, count in sorted(unnamed.items()):
        out.append(
            RawNote(
                f"season={season}: no stored row names the raw answer of {count} sampled game(s) "
                "(_raw_sha256); the newest answer was compared and the rows may come from another one"
            )
        )
    return out


__all__ = ["FULL_GAME_LIMIT", "SUFFIXES", "FullCheckTooLargeError", "raw_reader", "request_ident"]
