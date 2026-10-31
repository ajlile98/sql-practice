from datetime import date

import pytest

from sql_practice.database import SQLiteBackend
from sql_practice.datasets import parse_dataset

SCHEMA = {
    "version": 1,
    "tables": {
        "people": {
            "columns": {
                "id": {"type": "integer", "primary_key": True},
                "name": {"type": "text", "nullable": True},
                "joined": {"type": "date"},
            }
        }
    },
}


def dataset():
    return parse_dataset(SCHEMA, {"people": "id,name,joined\n1,\\N,2025-01-01\n2,,2025-01-02\n"})


def test_seed_distinguishes_null_empty_and_parses_dates():
    parsed = dataset()
    assert parsed.rows["people"][0]["name"] is None
    assert parsed.rows["people"][1]["name"] == ""
    assert parsed.rows["people"][0]["joined"] == date(2025, 1, 1)


def test_invalid_schema_or_rows_fail_before_loading():
    with pytest.raises(ValueError):
        parse_dataset({"version": 1, "tables": {"bad-name": {"columns": {}}}}, {})
    with pytest.raises(ValueError):
        parse_dataset(SCHEMA, {"people": "id,name,joined\n1,a,not-a-date\n"})
    with pytest.raises(ValueError, match="duplicate"):
        parse_dataset(SCHEMA, {"people": "id,name,joined\n1,a,2025-01-01\n1,b,2025-01-01\n"})


@pytest.mark.integration
def test_sqlite_backend_contract():
    backend = SQLiteBackend()
    with backend.fixture(dataset()) as connection:
        result = connection.query("SELECT id, name FROM people ORDER BY id")
        assert result.columns == ("id", "name")
        assert result.rows == ((1, None), (2, ""))
        for statement in ("DELETE FROM people", "PRAGMA user_version", "SELECT 1; SELECT 2"):
            with pytest.raises(ValueError):
                connection.query(statement)
        with pytest.raises(ValueError, match="row limit"):
            connection.query("SELECT * FROM people", max_rows=1)
        assert connection.query("SELECT COUNT(*) AS n FROM people").rows == ((2,),)
    with pytest.raises(ValueError, match="closed"):
        connection.query("SELECT 1")


@pytest.mark.integration
def test_sqlite_timeout():
    with (
        SQLiteBackend().fixture(dataset()) as connection,
        pytest.raises(ValueError, match="interrupted"),
    ):
        connection.query(
            "WITH RECURSIVE numbers(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM numbers) SELECT sum(n) FROM numbers",
            timeout=0.001,
        )
