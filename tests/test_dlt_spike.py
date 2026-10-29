"""Tests for the dlt spike script (no network)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dlt_spike import dlt_resource, select_records  # noqa: E402


def test_select_records_follows_star_and_at_paths() -> None:
    # 1. ("stats", "*", "splits") path
    star_payload = {
        "stats": [
            {"splits": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]},
            {"splits": [{"id": 3, "value": "c"}]},
        ]
    }
    recs_star = list(select_records(star_payload, ("stats", "*", "splits")))
    assert recs_star == [
        {"id": 1, "value": "a"},
        {"id": 2, "value": "b"},
        {"id": 3, "value": "c"},
    ]

    # 2. "@" path
    at_payload = {
        "teams": {
            "team_a": {"name": "Yankees", "city": "New York"},
            "team_b": {"name": "Red Sox", "city": "Boston"},
        }
    }
    recs_at = list(select_records(at_payload, ("teams", "@")))
    assert recs_at == [
        {"name": "Yankees", "city": "New York"},
        {"name": "Red Sox", "city": "Boston"},
    ]

    # 3. Missing key yields nothing
    assert list(select_records({"other": 123}, ("stats", "*", "splits"))) == []

    # 4. Contradicting shapes raise ValueError
    with pytest.raises(ValueError):
        list(select_records({"stats": "not_a_list"}, ("stats", "*", "splits")))

    with pytest.raises(ValueError):
        list(select_records({"teams": [1, 2, 3]}, ("teams", "@")))

    with pytest.raises(ValueError):
        list(select_records(12345, ("teams",)))


def test_dlt_resource_loads_nested_lists_into_child_tables(tmp_path: Path) -> None:
    import dlt

    endpoint = SimpleNamespace(
        name="teams",
        records=("teams",),
        keys=("id",),
    )

    payload = {
        "teams": [
            {
                "id": 1,
                "name": "Yankees",
                "children": [
                    {"child_id": 101, "role": "batboy"},
                    {"child_id": 102, "role": "mascot"},
                ],
            },
            {
                "id": 2,
                "name": "Red Sox",
                "children": [
                    {"child_id": 201, "role": "mascot"},
                ],
            },
        ]
    }

    req = SimpleNamespace(extra={"sport_id": 1})
    payloads = [(req, payload)]

    db_path = tmp_path / "test.duckdb"
    pipeline = dlt.pipeline(
        pipeline_name="test_nested_pipeline",
        pipelines_dir=str(tmp_path / "pipelines"),
        destination=dlt.destinations.duckdb(str(db_path)),
        dataset_name="test_teams_dataset",
    )

    res = dlt_resource(endpoint, payloads)
    pipeline.run(
        res,
        schema_contract={"tables": "evolve", "columns": "evolve", "data_type": "evolve"},
    )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # Parent row count
        parent_count = con.execute("SELECT COUNT(*) FROM test_teams_dataset.teams").fetchone()
        assert parent_count is not None and parent_count[0] == 2

        # Check for child table
        tables = [
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'test_teams_dataset'"
            ).fetchall()
        ]
        child_tables = [t for t in tables if t != "teams" and not t.startswith("_dlt_")]
        assert len(child_tables) >= 1
        assert "teams__children" in child_tables

        # Child table row count
        child_count = con.execute(
            f'SELECT COUNT(*) FROM test_teams_dataset."{child_tables[0]}"'  # noqa: S608
        ).fetchone()
        assert child_count is not None and child_count[0] == 3

        # Request extra was merged into top-level parent records
        sport_id_val = con.execute(
            "SELECT DISTINCT sport_id FROM test_teams_dataset.teams"
        ).fetchone()
        assert sport_id_val is not None and sport_id_val[0] == 1
    finally:
        con.close()
