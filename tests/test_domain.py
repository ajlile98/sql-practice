from decimal import Decimal

import pytest

from sql_practice.exercises import Exercise, parse_categories, select_exercises
from sql_practice.grading import QueryResult, compare_results


def exercise(identifier, topic="windows", difficulty="advanced"):
    return Exercise(identifier, identifier, difficulty, (topic,), "Prompt", (), {}, (), False)


def category_document():
    return {
        "version": 1,
        "context_tags": ["interviews"],
        "categories": [
            {
                "id": "analytic",
                "label": "Analytic",
                "description": "Sequences",
                "tags": ["windows", "ranking"],
            },
            {
                "id": "advanced",
                "label": "Advanced",
                "description": "Advanced queries",
                "tags": ["windows"],
            },
        ],
    }


def test_categories_are_declarative_and_allow_overlap():
    registry = parse_categories(category_document())
    assert registry.labels_for(exercise("a")) == ["Analytic", "Advanced"]
    assert registry.tags_for("analytic") == ("windows", "ranking")
    assert registry.context_tags == ("interviews",)
    with pytest.raises(ValueError, match="Unknown category"):
        registry.tags_for("missing")


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"categories": []},
        {"categories": "wrong"},
        {"context_tags": "interviews"},
    ],
)
def test_category_registry_rejects_invalid_schema(change):
    with pytest.raises(ValueError):
        parse_categories({**category_document(), **change})


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Bad ID"},
        {"label": ""},
        {"description": None},
        {"tags": []},
        {"tags": ["windows", "windows"]},
        {"tags": [12]},
        {"tags": "windows"},
    ],
)
def test_category_registry_rejects_invalid_records(change):
    document = category_document()
    document["categories"][0].update(change)
    with pytest.raises(ValueError):
        parse_categories(document)


def test_category_registry_rejects_duplicate_ids():
    document = category_document()
    document["categories"].append(document["categories"][0])
    with pytest.raises(ValueError, match="duplicate"):
        parse_categories(document)


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {"version": 1, "categories": [12]},
        {**category_document(), "context_tags": ["interviews", "interviews"]},
    ],
)
def test_category_registry_malformed_documents_have_useful_errors(document):
    with pytest.raises(ValueError):
        parse_categories(document)


def test_new_category_requires_data_changes_only():
    document = category_document()
    document["categories"].append(
        {"id": "new-skill", "label": "New skill", "description": "Extension", "tags": ["new-topic"]}
    )
    registry = parse_categories(document)
    question = exercise("new", topic="new-topic")
    assert select_exercises([question], category="new-skill", categories=registry) == [question]


def test_category_filters_intersect_and_preserve_unsolved_policy():
    registry = parse_categories(category_document())
    bank = [exercise("a"), exercise("b", "ranking"), exercise("c", "joins")]
    assert select_exercises(bank, category="analytic", categories=registry, solved={"a"}) == [
        bank[1]
    ]
    assert select_exercises(bank, category="analytic", categories=registry, topic="windows") == [
        bank[0]
    ]
    assert select_exercises(bank, category="analytic", categories=registry, solved={"a", "b"})
    with pytest.raises(ValueError, match="Only 1 unsolved"):
        select_exercises(bank, category="analytic", categories=registry, count=2, solved={"a"})
    with pytest.raises(ValueError, match="No exercises"):
        select_exercises(bank, category="analytic", categories=registry, topic="joins")
    with pytest.raises(ValueError, match="explicit exercise"):
        select_exercises(bank, category="analytic", categories=registry, identifier="a")


def test_random_selection_is_reproducible_and_prefers_unsolved():
    bank = [exercise("a"), exercise("b"), exercise("c")]
    selected = select_exercises(bank, seed=4, solved={"a"})
    assert selected == select_exercises(bank, seed=4, solved={"a"})
    assert selected[0].id != "a"


def test_random_selection_prefers_unseen_over_seen_unsolved_questions():
    bank = [exercise("assisted"), exercise("failed"), exercise("unseen"), exercise("solved")]
    for seed in range(10):
        assert select_exercises(
            bank, seed=seed, solved={"solved"}, seen={"assisted", "failed", "solved"}
        ) == [bank[2]]


def test_unseen_first_batch_fills_with_seen_unsolved_and_remains_reproducible():
    bank = [exercise("seen-a"), exercise("seen-b"), exercise("new-a"), exercise("new-b")]
    options = {"seed": 7, "seen": {"seen-a", "seen-b"}, "count": 3}
    selected = select_exercises(bank, **options)
    assert {item.id for item in selected[:2]} == {"new-a", "new-b"}
    assert selected[2].id in options["seen"]
    assert selected == select_exercises(bank, **options)
    assert len({item.id for item in selected}) == 3


def test_unseen_preference_respects_filters_and_explicit_retries():
    bank = [exercise("seen"), exercise("new", topic="joins")]
    assert select_exercises(bank, topic="windows", seen={"seen"}) == [bank[0]]
    assert select_exercises(bank, identifier="seen", seen={"seen"}) == [bank[0]]
    assert select_exercises(bank, seen={"seen", "new"}, count=2)


def test_selection_does_not_relax_filters():
    with pytest.raises(ValueError, match="No exercises"):
        select_exercises([exercise("a")], topic="unknown")
    with pytest.raises(ValueError, match="count"):
        select_exercises([exercise("a")], count=2)


def test_explicit_selection_and_difficulty():
    bank = [exercise("a"), exercise("b", difficulty="intermediate")]
    assert select_exercises(bank, identifier="b")[0].id == "b"
    assert select_exercises(bank, difficulty="intermediate")[0].id == "b"


def test_selection_never_pads_unsolved_batch_with_solved_exercises():
    bank = [exercise("a"), exercise("b"), exercise("c")]
    with pytest.raises(ValueError, match="Only 1 unsolved.*generate new"):
        select_exercises(bank, count=2, solved={"a", "b"})


def test_selection_can_repeat_only_when_all_matching_exercises_are_solved():
    bank = [exercise("a"), exercise("b", topic="joins")]
    assert select_exercises(bank, topic="windows", solved={"a"}) == [bank[0]]
    assert select_exercises(bank, identifier="a", solved={"a"}) == [bank[0]]


def test_required_unsolved_filter_also_applies_to_injected_strategy():
    class FirstSelection:
        def choose(self, bank, count):
            return bank[:count]

    bank = [exercise("a"), exercise("b")]
    assert select_exercises(bank, solved={"a"}, strategy=FirstSelection()) == [bank[1]]


def test_unordered_comparison_preserves_duplicate_counts():
    expected = QueryResult(("value",), ((1,), (1,), (2,)))
    assert compare_results(expected, QueryResult(("value",), ((2,), (1,), (1,)))).passed
    assert not compare_results(expected, QueryResult(("value",), ((1,), (2,)))).passed


def test_order_columns_nulls_and_decimal_comparison():
    expected = QueryResult(("amount",), ((Decimal("1.10"),), (None,)))
    assert compare_results(expected, QueryResult(("amount",), ((None,), (Decimal("1.1"),)))).passed
    assert not compare_results(
        expected, QueryResult(("amount",), tuple(reversed(expected.rows))), ordered=True
    ).passed
    assert not compare_results(expected, QueryResult(("wrong",), expected.rows)).passed
    assert compare_results(QueryResult(("value",), ()), QueryResult(("value",), ())).passed


def test_duplicate_labels_and_numeric_strings_are_not_equivalent():
    with pytest.raises(ValueError, match="duplicate"):
        compare_results(QueryResult(("a", "a"), ()), QueryResult(("a", "a"), ()))
    assert not compare_results(QueryResult(("a",), ((1,),)), QueryResult(("a",), (("1",),))).passed
