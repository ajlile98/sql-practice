from pathlib import Path

import pytest

from sql_practice.database import SQLiteBackend
from sql_practice.datasets import FIXTURES, load_dataset
from sql_practice.exercises import load_bank
from sql_practice.grading import QueryResult, compare_results

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_bank_contract():
    bank = load_bank(ROOT)
    assert len(bank) == 20
    assert sum(item.difficulty == "advanced" for item in bank) == 8
    for fixture in FIXTURES:
        assert load_dataset(ROOT, fixture).metadata.tables


@pytest.mark.integration
@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_sqlite_reference_and_empty_wrong_answer(fixture):
    with SQLiteBackend().fixture(load_dataset(ROOT, fixture)) as connection:
        for exercise in load_bank(ROOT):
            result = connection.query(exercise.sql("sqlite"))
            assert result.columns == exercise.columns, exercise.id
            assert compare_results(
                result, connection.query(exercise.sql("sqlite")), ordered=exercise.ordered
            ).passed
            if fixture == "base":
                assert result.rows, exercise.id
                assert not compare_results(result, QueryResult(result.columns, ())).passed


@pytest.mark.integration
def test_independent_anchors_and_known_wrong_queries():
    with SQLiteBackend().fixture(load_dataset(ROOT)) as connection:
        bank = {item.id: item for item in load_bank(ROOT)}
        result = connection.query(bank["customer-spending"].sql("sqlite"))
        assert dict(result.rows) == {1: 11000, 2: 9000, 3: 3000, 4: 0, 5: 12000, 6: 0}
        result = connection.query(bank["never-paid"].sql("sqlite"))
        assert {row[0] for row in result.rows} == {4, 6}
        result = connection.query(bank["payment-reconciliation"].sql("sqlite"))
        assert result.rows == ((9, 12000, 11000),)
        correct = connection.query(bank["latest-order"].sql("sqlite"))
        wrong = connection.query(
            "SELECT customer_id, MAX(id) AS order_id FROM orders GROUP BY customer_id"
        )
        assert not compare_results(correct, wrong).passed


@pytest.mark.integration
def test_ties_boundaries_cohorts_and_zero_sales_anchors():
    bank = {item.id: item for item in load_bank(ROOT)}
    backend = SQLiteBackend()
    with backend.fixture(load_dataset(ROOT)) as connection:
        active = connection.query(bank["active-subscribers"].sql("sqlite"))
        assert {row[0] for row in active.rows} == {1, 2, 3}
        cohorts = connection.query(bank["next-month-retention"].sql("sqlite"))
        assert set(cohorts.rows) == {("2025-01", 2, 2), ("2025-02", 1, 0), ("2025-03", 1, 0)}
        leaders = connection.query(bank["category-leaders"].sql("sqlite"))
        assert ("Courses", 6, 0, 2) in leaders.rows
        assert ("Courses", 7, 0, 2) in leaders.rows
        wrong = connection.query(
            bank["category-leaders"].sql("sqlite").replace("DENSE_RANK()", "ROW_NUMBER()")
        )
        assert not compare_results(leaders, wrong).passed
    with backend.fixture(load_dataset(ROOT, "edge")) as connection:
        latest = connection.query(bank["latest-order"].sql("sqlite"))
        assert dict(latest.rows)[1] == 10
    with backend.fixture(load_dataset(ROOT, "no-sales")) as connection:
        shares = connection.query(bank["revenue-share"].sql("sqlite"))
        assert len(shares.rows) == 6
        assert all(total == 0 and share is None for _customer, total, share in shares.rows)
    catalog_empty = load_dataset(ROOT)
    catalog_empty.rows["products"] = []
    catalog_empty.rows["order_items"] = []
    with backend.fixture(catalog_empty) as connection:
        assert {row[0] for row in connection.query(bank["all-categories"].sql("sqlite")).rows} == {
            1,
            2,
            3,
            4,
            5,
            6,
        }
