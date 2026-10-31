import os
from pathlib import Path

import pytest

from sql_practice.datasets import load_dataset
from sql_practice.environment import LocalEnvironment
from sql_practice.exercises import load_bank
from sql_practice.grading import QueryResult, compare_results

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("SQL_PRACTICE_TEST_SERVERS") != "1",
        reason="Set SQL_PRACTICE_TEST_SERVERS=1 after starting project containers",
    ),
]


@pytest.mark.parametrize("engine", ["postgres", "mysql"])
def test_server_restrictions_cleanup_and_percent_literals(engine):
    backend = LocalEnvironment(ROOT).backend(engine)
    with backend.fixture(load_dataset(ROOT)) as connection:
        for statement in (
            "DELETE FROM orders",
            "CREATE TABLE forbidden (id INTEGER)",
            "SELECT 1; SELECT 2",
            "SELECT load_extension('invalid')",
        ):
            with pytest.raises(ValueError):
                connection.query(statement)
        assert connection.query("SELECT '100%' AS percentage").rows == (("100%",),)
        with pytest.raises(ValueError, match="row limit"):
            connection.query("SELECT * FROM customers", max_rows=1)
        query = "SELECT pg_sleep(0.1)" if engine == "postgres" else "SELECT SLEEP(0.1)"
        with pytest.raises(ValueError):
            connection.query(query, timeout=0.01)
    with pytest.raises(ValueError, match="closed"):
        connection.query("SELECT 1")


@pytest.mark.parametrize("engine", ["postgres", "mysql"])
def test_server_persistent_sandbox_and_reference(engine):
    backend = LocalEnvironment(ROOT).backend(engine)
    question = load_bank(ROOT)[0]
    for _attempt in range(2):
        with backend.sandbox(load_dataset(ROOT)) as connection:
            result = connection.query(question.sql(engine))
            assert compare_results(
                QueryResult(
                    ("customer_id", "total_cents"),
                    (
                        (1, 11000),
                        (2, 9000),
                        (3, 3000),
                        (4, 0),
                        (5, 12000),
                        (6, 0),
                    ),
                ),
                result,
            ).passed
