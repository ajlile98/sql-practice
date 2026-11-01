from decimal import Decimal
from pathlib import Path

import pytest

from sql_practice.database import SQLiteBackend
from sql_practice.datasets import FIXTURES, load_dataset
from sql_practice.exercises import load_bank
from sql_practice.grading import QueryResult, compare_results

ROOT = Path(__file__).resolve().parents[1]

REVENUE_BASE = {
    "revenue-customer-totals": ((1, 6000, 10500), (2, 5000, 9000), (3, 2000, 5000), (4, 0, 0), (5, 2500, 3500), (6, 0, 0), (7, 0, 0), (8, 0, 0)),
    "customer-product-revenue-windows": ((1, 1, 2000, 4000), (1, 2, 2000, 4000), (1, 3, 2000, 2500), (2, 1, 2000, 4000), (2, 2, 2000, 4000), (2, 3, 1000, 1000), (3, 4, 2000, 5000), (5, 5, 1000, 1000), (5, 6, 1000, 2000), (5, 7, 500, 500), (6, 7, 0, 0)),
    "revenue-product-growth": ((1, 1000, 4000, 3000), (2, 1000, 4000, 3000), (3, 0, 3000, 3000), (4, 500, 2000, 1500), (5, 0, 1000, 1000), (6, 1000, 1000, 0), (7, 0, 500, 500), (8, 0, 0, 0)),
    "revenue-customer-product-leaders": ((1, 1, 4000, 1), (1, 2, 4000, 1), (1, 3, 2500, 2), (2, 1, 4000, 1), (2, 2, 4000, 1), (2, 3, 1000, 2), (3, 4, 5000, 1), (5, 6, 2000, 1), (5, 5, 1000, 2), (6, 7, 0, 1)),
    "revenue-monthly-trends": (("2024-03", 2000, None, None, 2000), ("2024-04", 2000, 2000, 0, 4000), ("2024-05", 0, 2000, -2000, 4000), ("2024-06", 500, 0, 500, 2500), ("2024-07", 1500, 500, 1000, 2000), ("2024-08", 2000, 1500, 500, 4000), ("2024-09", 2000, 2000, 0, 5500), ("2024-10", 1500, 2000, -500, 5500), ("2024-11", 1000, 1500, -500, 4500), ("2024-12", 5000, 1000, 4000, 7500), ("2025-01", 4000, 5000, -1000, 10000), ("2025-02", 6500, 4000, 2500, 15500)),
    "revenue-customer-concentration": ((1, 10500, Decimal("37.50"), 10500), (2, 9000, Decimal("32.14"), 19500), (3, 5000, Decimal("17.86"), 24500), (5, 3500, Decimal("12.50"), 28000), (4, 0, Decimal("0.00"), 28000), (6, 0, Decimal("0.00"), 28000), (7, 0, Decimal("0.00"), 28000), (8, 0, Decimal("0.00"), 28000)),
}

REVENUE_EDGE = {
    "revenue-customer-totals": ((1, 1000, 2500), (2, 2500, 2500), (3, 0, 1000), (4, 0, 0), (5, 0, 0), (6, 0, 0), (7, 0, 0), (8, 0, 0)),
    "customer-product-revenue-windows": ((1, 1, 0, 1000), (1, 2, 1000, 1000), (1, 3, 0, 500), (1, 4, 0, 0), (2, 1, 1000, 1000), (2, 2, 1000, 1000), (2, 3, 500, 500), (3, 5, 0, 1000)),
    "revenue-product-growth": ((1, 0, 1000, 1000), (2, 0, 2000, 2000), (3, 500, 500, 0), (4, 0, 0, 0), (5, 1000, 0, -1000), (6, 0, 0, 0), (7, 0, 0, 0), (8, 0, 0, 0)),
    "revenue-customer-product-leaders": ((1, 1, 1000, 1), (1, 2, 1000, 1), (1, 3, 500, 2), (2, 1, 1000, 1), (2, 2, 1000, 1), (2, 3, 500, 2), (3, 5, 1000, 1)),
    "revenue-monthly-trends": (("2024-03", 1000, None, None, 1000), ("2024-04", 0, 1000, -1000, 1000), ("2024-05", 0, 0, 0, 1000), ("2024-06", 0, 0, 0, 0), ("2024-07", 0, 0, 0, 0), ("2024-08", 0, 0, 0, 0), ("2024-09", 1000, 0, 1000, 1000), ("2024-10", 0, 1000, -1000, 1000), ("2024-11", 500, 0, 500, 1500), ("2024-12", 2000, 500, 1500, 2500), ("2025-01", 1000, 2000, -1000, 3500), ("2025-02", 500, 1000, -500, 3500)),
    "revenue-customer-concentration": ((1, 2500, Decimal("41.67"), 2500), (2, 2500, Decimal("41.67"), 5000), (3, 1000, Decimal("16.67"), 6000), (4, 0, Decimal("0.00"), 6000), (5, 0, Decimal("0.00"), 6000), (6, 0, Decimal("0.00"), 6000), (7, 0, Decimal("0.00"), 6000), (8, 0, Decimal("0.00"), 6000)),
}


@pytest.mark.integration
@pytest.mark.parametrize("fixture", FIXTURES)
def test_revenue_dataset_contract(fixture):
    dataset = load_dataset(ROOT, fixture, name="revenue")
    assert set(dataset.rows) == {"customers", "products", "orders", "order_items"}
    assert dataset.name == "revenue" and dataset.as_of == "2025-03-01"
    if fixture in ("empty", "no-sales"):
        assert not dataset.rows["orders"] and not dataset.rows["order_items"]
    assert bool(dataset.rows["customers"]) == (fixture != "empty")


@pytest.mark.integration
@pytest.mark.parametrize("fixture,anchors", [("base", REVENUE_BASE), ("edge", REVENUE_EDGE)])
def test_revenue_independent_anchors(fixture, anchors):
    bank = {item.id: item for item in load_bank(ROOT)}
    with SQLiteBackend().fixture(load_dataset(ROOT, fixture, name="revenue")) as connection:
        for exercise_id, rows in anchors.items():
            exercise = bank[exercise_id]
            assert exercise.dataset == "revenue"
            actual = connection.query(exercise.sql("sqlite"))
            assert compare_results(QueryResult(exercise.columns, rows), actual, ordered=True).passed, exercise_id


@pytest.mark.integration
def test_bank_contract():
    bank = load_bank(ROOT)
    assert len(bank) == 26
    assert sum(item.difficulty == "advanced" for item in bank) == 11
    assert sum(item.dataset == "revenue" for item in bank) == 6
    for name in {item.dataset for item in bank}:
        for fixture in FIXTURES:
            assert load_dataset(ROOT, fixture, name=name).metadata.tables


@pytest.mark.integration
@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_sqlite_reference_and_empty_wrong_answer(fixture):
    bank = load_bank(ROOT)
    for name in {item.dataset for item in bank}:
        with SQLiteBackend().fixture(load_dataset(ROOT, fixture, name=name)) as connection:
            for exercise in (item for item in bank if item.dataset == name):
                result = connection.query(exercise.sql("sqlite"))
                assert result.columns == exercise.columns, exercise.id
                assert compare_results(
                    result, connection.query(exercise.sql("sqlite")), ordered=exercise.ordered
                ).passed
                if fixture == "base":
                    assert result.rows, exercise.id
                    assert not compare_results(result, QueryResult(result.columns, ())).passed


REVENUE_WRONG = {
    "revenue-customer-totals": (("LEFT JOIN revenue", "JOIN revenue"),),
    "customer-product-revenue-windows": (
        (">= DATE('2025-03-01','-90 day')", "> DATE('2025-03-01','-90 day')"),
        (">= DATE('2025-03-01','-365 day')", "> DATE('2025-03-01','-365 day')"),
        ("o.ordered_on < '2025-03-01'", "o.ordered_on <= '2025-03-01'"),
        ("GROUP BY o.customer_id, i.product_id", "GROUP BY o.customer_id, i.product_id HAVING SUM(i.quantity*i.unit_price_cents)>0"),
    ),
    "revenue-product-growth": (("o.ordered_on < '2024-12-01'", "o.ordered_on <= '2024-12-01'"),),
    "revenue-customer-product-leaders": (("DENSE_RANK()", "ROW_NUMBER()"),),
    "revenue-monthly-trends": (("LEFT JOIN monthly", "JOIN monthly"),),
    "revenue-customer-concentration": (("ORDER BY revenue_365d_cents DESC,customer_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW", "ORDER BY revenue_365d_cents DESC"),),
}


@pytest.mark.integration
@pytest.mark.parametrize("fixture", ["base", "edge"])
def test_revenue_known_wrong_queries(fixture):
    with SQLiteBackend().fixture(load_dataset(ROOT, fixture, name="revenue")) as connection:
        for exercise in (item for item in load_bank(ROOT) if item.dataset == "revenue"):
            sql = exercise.sql("sqlite")
            correct = connection.query(sql)
            specific = REVENUE_WRONG[exercise.id]
            if fixture == "base" and exercise.id == "revenue-customer-concentration":
                specific = ()
            mutations = (*specific,
                         ("i.quantity*i.unit_price_cents", "i.unit_price_cents"),
                         ("o.status='paid'", "o.status<>'pending'"))
            for before, after in mutations:
                assert before in sql
                wrong = connection.query(sql.replace(before, after))
                assert not compare_results(correct, wrong, ordered=True).passed, (exercise.id, before)


@pytest.mark.integration
@pytest.mark.parametrize("fixture", ["empty", "no-sales"])
def test_revenue_zero_sales_rules(fixture):
    bank = {item.id: item for item in load_bank(ROOT)}
    ids = range(1, 9) if fixture == "no-sales" else ()
    expected = {
        "revenue-customer-totals": tuple((customer, 0, 0) for customer in ids),
        "customer-product-revenue-windows": (),
        "revenue-product-growth": tuple((product, 0, 0, 0) for product in ids),
        "revenue-customer-product-leaders": (),
        "revenue-customer-concentration": tuple((customer, 0, None, 0) for customer in ids),
        "revenue-monthly-trends": tuple(
            (row[0], 0, None if index == 0 else 0, None if index == 0 else 0, 0)
            for index, row in enumerate(REVENUE_BASE["revenue-monthly-trends"])
        ),
    }
    with SQLiteBackend().fixture(load_dataset(ROOT, fixture, name="revenue")) as connection:
        for exercise_id, rows in expected.items():
            item = bank[exercise_id]
            assert connection.query(item.sql("sqlite")).rows == rows, exercise_id


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
