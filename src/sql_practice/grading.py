"""Driver-independent result contracts and comparison strategies."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class Comparison:
    passed: bool
    message: str


class ComparisonStrategy(Protocol):
    def compare(self, expected: tuple, actual: tuple) -> bool: ...


class MultisetComparison:
    def compare(self, expected: tuple, actual: tuple) -> bool:
        return Counter(expected) == Counter(actual)


class OrderedComparison:
    def compare(self, expected: tuple, actual: tuple) -> bool:
        return expected == actual


def normalize(value: Any) -> Any:
    if value is None:
        return ("null",)
    if isinstance(value, (int, float, Decimal)):
        return ("number", Decimal(str(value)))
    if isinstance(value, (date, datetime)):
        return (
            "text",
            value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat(),
        )
    return (type(value).__name__ if not isinstance(value, str) else "text", value)


def compare_results(
    expected: QueryResult,
    actual: QueryResult,
    *,
    ordered: bool = False,
    strategy: ComparisonStrategy | None = None,
) -> Comparison:
    for result in (expected, actual):
        if len(set(result.columns)) != len(result.columns):
            raise ValueError("Result contains duplicate column labels; use explicit aliases")
        if any(len(row) != len(result.columns) for row in result.rows):
            raise ValueError("Result row does not match column count")
    if expected.columns != actual.columns:
        return Comparison(False, f"Expected columns {expected.columns}; got {actual.columns}")
    expected_rows = tuple(tuple(normalize(value) for value in row) for row in expected.rows)
    actual_rows = tuple(tuple(normalize(value) for value in row) for row in actual.rows)
    policy = strategy or (OrderedComparison() if ordered else MultisetComparison())
    if policy.compare(expected_rows, actual_rows):
        return Comparison(True, f"Correct ({len(actual.rows)} rows)")
    missing = list((Counter(expected_rows) - Counter(actual_rows)).elements())[:3]
    extra = list((Counter(actual_rows) - Counter(expected_rows)).elements())[:3]
    detail = (
        "Row order differs"
        if not missing and not extra
        else f"Missing: {missing}; unexpected: {extra}"
    )
    return Comparison(
        False, f"Expected {len(expected.rows)} rows, got {len(actual.rows)}. {detail}"
    )
