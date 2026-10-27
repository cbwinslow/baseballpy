"""Baseball Savant (Statcast) Leaderboards Extractor and Normalizer."""

import csv
import io
import re
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.quarantine import safe_array
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key


def leaderboard_spec(name: str, schema: pa.Schema | None = None) -> DatasetSpec:
    """Unregistered spec for a Savant leaderboard (typed schemas arrive with coverage C-4)."""
    return DatasetSpec(
        source="statcast",
        name=f"leaderboard_{name}",
        view=f"statcast_leaderboard_{name}",
        schema=schema or pa.schema([]),
        partition="season",
        keys=(),
        description=f"Baseball Savant {name} leaderboard (schema inferred).",
        endpoint_doc="sources/statcast.md#2-dedicated-analytical-leaderboards-leaderboard",
    )


SAVANT_BASE = "https://baseballsavant.mlb.com/leaderboard"

LEADERBOARD_ROUTES = {
    "expected_statistics": "expected_statistics",
    "exit_velocity": "statcast",
    "sprint_speed": "sprint_speed",
    "running_splits": "running_splits",
    "bat_tracking": "bat-tracking",
    "outs_above_average": "outs_above_average",
    "arm_strength": "arm-strength",
    "poptime": "poptime",
    "catcher_framing": "catcher-framing",
    "pitch_arsenals": "pitch-arsenals",
    "pitch_movement": "pitch-movement",
    "abs_challenges": "abs-challenges",
}


def _safe_float(val: Any) -> float | None:
    if val is None or val == "" or val == "null" or val == "None":
        return None
    try:
        s = str(val).strip().rstrip("%")
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "" or val == "null" or val == "None":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


class StatcastLeaderboardNormalizer:
    """Normalizes raw Savant Leaderboard CSV payloads into strongly-typed PyArrow Tables."""

    def normalize(self, raw_bytes: bytes) -> pa.Table:
        """Parse CSV bytes (stripping BOM if present) into a typed PyArrow Table."""
        if not raw_bytes:
            return pa.table({})

        text = raw_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text, newline=""))
        header = next(reader, None)
        if not header:
            return pa.table({})

        # Clean header names (lowercase, strip, replace spaces/dashes with underscores)
        cleaned_headers = [
            h.strip().replace(" ", "_").replace("-", "_").replace(".", "_").lower() for h in header
        ]

        rows: list[list[Any]] = []
        for r in reader:
            if not r or all(c == "" for c in r):
                continue
            # Pad or truncate row to header length
            row_vals = r + [""] * (len(cleaned_headers) - len(r))
            rows.append(row_vals[: len(cleaned_headers)])

        if not rows:
            # Build empty string table
            fields = [(h, pa.string()) for h in cleaned_headers]
            return pa.Table.from_batches([], schema=pa.schema(fields))

        # Infer and cast column types
        arrays = []
        for col_idx, col_name in enumerate(cleaned_headers):
            raw_vals = [row[col_idx] for row in rows]

            # 1. Integer candidate
            if col_name == "id" or any(
                id_pattern in col_name
                for id_pattern in (
                    "_id",
                    "player_id",
                    "entity_id",
                    "pitcher",
                    "year",
                    "age",
                    "bolts",
                    "swings",
                    "attempts",
                )
            ):
                int_vals = [_safe_int(v) for v in raw_vals]
                arrays.append(
                    safe_array(
                        int_vals,
                        pa.int32(),
                        source="statcast",
                        dataset="leaderboard",
                        column=col_name,
                    )
                )
            # 2. Float candidate (metrics, speeds, percentages, runs)
            elif any(
                metric_pattern in col_name
                for metric_pattern in (
                    "speed",
                    "velo",
                    "rate",
                    "percent",
                    "pct",
                    "avg",
                    "est_",
                    "ba",
                    "slg",
                    "woba",
                    "diff",
                    "rv_",
                    "distance",
                    "pop_",
                    "arm_",
                    "length",
                    "value",
                )
            ):
                flt_vals = [_safe_float(v) for v in raw_vals]
                arrays.append(
                    safe_array(
                        flt_vals,
                        pa.float32(),
                        source="statcast",
                        dataset="leaderboard",
                        column=col_name,
                    )
                )
            # 3. String fallback
            else:
                str_vals = [v.strip() if v else None for v in raw_vals]
                arrays.append(pa.array(str_vals, type=pa.string()))

        schema = pa.schema(
            [(cleaned_headers[i], arrays[i].type) for i in range(len(cleaned_headers))]
        )
        return pa.Table.from_arrays(arrays, schema=schema)


class StatcastLeaderboardExtractor:
    """Extracts analytical leaderboards from Baseball Savant with rate limiting and atomic caching."""

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
        self.normalizer = StatcastLeaderboardNormalizer()
        self.store = ProcessedStore(self.cache_config)
        self.raw = RawStore(self.cache_config)

    @staticmethod
    def _chunk_id(name: str, year: int, **params: Any) -> str:
        param_str = "_".join(f"{k}-{v}" for k, v in sorted(params.items()) if v is not None)
        chunk = f"{name}_{year}"
        return f"{chunk}_{param_str}" if param_str else chunk

    def _manifest(self, name: str) -> ManifestTracker:
        return self.cache_config.dataset_manifest("statcast", f"leaderboard_{name}")

    def _get_cache_path(self, name: str, year: int, **params: Any) -> Path:
        spec = leaderboard_spec(name)
        return self.store.part_path(spec, self._chunk_id(name, year, **params), year)

    def get_leaderboard(
        self,
        name: str,
        year: int = 2024,
        refresh: bool = False,
        **kwargs: Any,
    ) -> pa.Table:
        """Fetch and normalize a Savant leaderboard table."""
        route = LEADERBOARD_ROUTES.get(name.lower(), name)
        url = f"{SAVANT_BASE}/{route}"

        # Clean params
        params: dict[str, Any] = {"year": year, "csv": "true"}
        if "type" in kwargs:
            params["type"] = kwargs["type"]
        if "min" in kwargs:
            params["min"] = kwargs["min"]
        for k, v in kwargs.items():
            if k not in params and v is not None:
                params[k] = v

        lname = re.sub(r"[^a-z0-9_]+", "_", name.lower())
        cache_path = self._get_cache_path(lname, year, **kwargs)
        chunk_id = self._chunk_id(lname, year, **kwargs)
        manifest = self._manifest(lname)

        entry = manifest.get_chunk(manifest_key(chunk_id, year))
        if cache_path.exists() and self.cache_config.is_fresh(
            entry, "leaderboard", season=year, refresh=refresh
        ):
            with default_audit_logger.track(
                operation=f"savant_leaderboard_{name.lower()}",
                source="statcast",
                endpoint=url,
                destination=str(cache_path),
            ) as hit:
                hit.set_cache_hit(True)
                cached = pq.read_table(cache_path)
                hit.set_records(len(cached))
                return cached

        with default_audit_logger.track(
            operation=f"savant_leaderboard_{name.lower()}",
            source="statcast",
            endpoint=url,
            destination=str(cache_path),
        ) as tracker:
            result = self.http.get_sync(url, params=params)
            raw_bytes = result.content
            table = self.normalizer.normalize(raw_bytes)

            if self.cache_config.enabled and len(table) > 0:
                spec = leaderboard_spec(lname, table.schema)
                self.raw.put(
                    "statcast",
                    spec.name,
                    f"{chunk_id}.csv",
                    raw_bytes,
                    season=year,
                    etag=result.etag or "",
                )
                self.store.put(spec, table, chunk_id=chunk_id, season=year)

            tracker.set_cache_hit(False)
            tracker.set_records(len(table))
            return table


# Module-level convenience functions
get_default_extractor = lazy_singleton(StatcastLeaderboardExtractor)


def get_leaderboard(name: str, year: int = 2024, refresh: bool = False, **kwargs: Any) -> pa.Table:
    """Extract any Baseball Savant leaderboard by name."""
    return get_default_extractor().get_leaderboard(name=name, year=year, refresh=refresh, **kwargs)


def expected_statistics(
    year: int = 2024, player_type: str = "batter", min_pa: str = "q", refresh: bool = False
) -> pa.Table:
    """Extract Expected Statistics (xBA, xSLG, xwOBA) leaderboard."""
    return get_default_extractor().get_leaderboard(
        "expected_statistics", year=year, type=player_type, min=min_pa, refresh=refresh
    )


def exit_velocity(
    year: int = 2024, player_type: str = "batter", min_bbe: str = "q", refresh: bool = False
) -> pa.Table:
    """Extract Exit Velocity & Barrels leaderboard."""
    return get_default_extractor().get_leaderboard(
        "exit_velocity", year=year, type=player_type, min=min_bbe, refresh=refresh
    )


def sprint_speed(year: int = 2024, min_runs: int = 10, refresh: bool = False) -> pa.Table:
    """Extract Sprint Speed and Running Splits leaderboard."""
    return get_default_extractor().get_leaderboard(
        "sprint_speed", year=year, min=min_runs, refresh=refresh
    )


def bat_tracking(
    year: int = 2024, player_type: str = "batter", min_swings: str = "q", refresh: bool = False
) -> pa.Table:
    """Extract 2024+ Bat Tracking (bat speed, swing length, squared up %) leaderboard."""
    return get_default_extractor().get_leaderboard(
        "bat_tracking", year=year, type=player_type, min=min_swings, refresh=refresh
    )


def outs_above_average(
    year: int = 2024, fielder_type: str = "Fielder", min_att: str = "q", refresh: bool = False
) -> pa.Table:
    """Extract Outs Above Average (OAA) defensive leaderboard."""
    return get_default_extractor().get_leaderboard(
        "outs_above_average",
        year=year,
        startYear=year,
        endYear=year,
        type=fielder_type,
        min=min_att,
        refresh=refresh,
    )
