from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from sql_practice.exercises import Categories, Category, Exercise
from sql_practice.grading import QueryResult
from sql_practice.practice import PracticeService
from sql_practice.sessions import SessionStore


def make_service():
    question = Exercise(
        "example",
        "Example",
        "advanced",
        ("windows",),
        "Prompt",
        ("Hint 1", "Hint 2"),
        {"shared": "SELECT 1 AS value"},
        ("value",),
        False,
    )
    store = Mock(spec=SessionStore)
    session = {
        "id": "session",
        "engine": "sqlite",
        "version": "v1",
        "exercises": ["example"],
        "hints": {},
        "solutions": [],
    }
    store.get.return_value = session
    store.answer.return_value = "SELECT 1 AS value"
    connection = Mock()
    connection.query.return_value = QueryResult(("value",), ((1,),))

    class FakeBackend:
        @contextmanager
        def fixture(self, _data):
            yield connection

        sandbox = fixture

    service = PracticeService(
        [question],
        "v1",
        store,
        lambda engine: FakeBackend(),
        lambda fixture: object(),
    )
    return service, store, session, connection


def test_facade_accepts_additional_backend_without_changes():
    service, store, _session, connection = make_service()
    results = service.check()
    assert results["passed"]
    assert len(results["fixtures"]) == 4
    assert store.record.call_args.args[0]["assisted"] is False
    assert connection.query.call_count == 8


def test_assistance_is_tracked_and_hints_are_progressive():
    service, store, _session, _connection = make_service()
    assert service.hint() == "Hint 1"
    assert service.hint() == "Hint 2"
    assert service.hint() == "No more hints. Request the solution explicitly."
    assert service.solution() == "SELECT 1 AS value"
    service.check()
    assert store.record.call_args.args[0]["assisted"] is True


def test_stale_session_and_ambiguous_question_fail():
    service, _store, session, _connection = make_service()
    session["version"] = "old"
    with pytest.raises(ValueError, match="changed"):
        service.run()
    session["version"] = "v1"
    session["exercises"] = ["example", "other"]
    with pytest.raises(ValueError, match="question"):
        service.run()


def test_failed_checks_and_query_errors_are_recorded():
    service, store, _session, connection = make_service()
    connection.query.side_effect = ValueError("bad SQL")
    result = service.check()
    assert not result["passed"]
    assert "bad SQL" in result["fixtures"][0]["message"]
    assert store.record.called


def test_facade_accepts_new_comparison_strategy():
    service, _store, _session, _connection = make_service()

    class RejectComparison:
        def compare(self, _expected, _actual):
            return False

    service.comparison_factory = lambda _exercise: RejectComparison()
    assert not service.check()["passed"]


def test_facade_accepts_new_selection_strategy():
    service, store, _session, _connection = make_service()
    store.attempts.return_value = []
    policy = Mock()
    policy.choose.return_value = service.bank
    service.selection_strategy = policy
    service.start(seed=42)
    policy.choose.assert_called_once_with(service.bank, 1)
    assert store.create.call_args.args[0] == service.bank


def attempt(identifier, passed=False, assisted=False, engine="postgres", session=None):
    return {
        "exercise": identifier,
        "passed": passed,
        "assisted": assisted,
        "engine": engine,
        "tags": ["old-tag"],
        **({"session": session} if session is not None else {}),
    }


@pytest.fixture(name="learning")
def learning_fixture():
    service, store, _session, connection = make_service()
    question = service.bank[0]
    service.bank = [
        replace(question, tags=("windows", "ranking")),
        replace(question, id="assisted"),
        replace(question, id="unfinished"),
        replace(question, id="fresh", tags=("custom-tag", "interviews"), difficulty="intermediate"),
    ]
    service.categories = Categories(
        (
            Category("windows", "Windows", "Sequences", ("windows", "ranking")),
            Category("overlap", "Overlap", "Same questions", ("windows",)),
            Category("fundamentals", "Fundamentals", "Future material", ("filtering",)),
        ),
        ("interviews",),
    )
    store.attempts.return_value = [
        attempt("example"),
        attempt("example", True, engine="sqlite"),
        attempt("example", True, engine="sqlite"),
        attempt("example"),
        attempt("assisted", True, True),
        attempt("unfinished"),
        attempt("removed", True),
    ]
    return service, store, connection


def test_progress_counts_unique_questions_and_preserves_legacy_history(learning):
    service, store, connection = learning
    original = deepcopy(store.attempts.return_value)
    result = service.progress()
    assert result["total_attempts"] == 7
    assert result["topics"]["old-tag"] == {"attempts": 7, "passes": 3, "assisted_passes": 1}
    overall = result["overall"]
    assert (
        overall["available"],
        overall["attempted"],
        overall["solved"],
        overall["assisted_only"],
        overall["needs_work"],
        overall["unattempted"],
    ) == (4, 3, 1, 1, 1, 1)
    assert overall["coverage_percent"] == 25
    assert overall["first_try_passes"] == 0
    assert overall["first_try_percent"] == 0
    assert overall["limited_evidence"]
    assert result["archived_attempts"] == 1
    windows = result["categories"]["windows"]
    assert windows["available"] == 3 and windows["attempts"] == 6
    assert windows["solved"] == result["categories"]["overlap"]["solved"] == 1
    assert result["topic_progress"]["ranking"]["solved"] == 1
    assert result["unmapped_tags"] == ["custom-tag"]
    assert result["categories"]["fundamentals"]["coverage_percent"] is None
    assert result["recommendations"][0]["action"] == "revisit"
    assert store.attempts.return_value == original
    store.answer.assert_not_called()
    store.record.assert_not_called()
    store.save.assert_not_called()
    connection.query.assert_not_called()


def test_progress_filters_engine_before_status_and_first_attempt(learning):
    service, _store, _connection = learning
    postgres = service.progress(engine="postgres")
    assert postgres["overall"]["solved"] == 0
    assert postgres["overall"]["needs_work"] == 2
    sqlite = service.progress(engine="sqlite", category="windows", topic="ranking")
    assert sqlite["overall"]["solved"] == 1
    assert sqlite["overall"]["first_try_passes"] == 1
    assert sqlite["overall"]["first_try_percent"] == 100
    assert list(sqlite["categories"]) == ["windows"]
    assert sqlite["total_attempts"] == 2
    assert service.progress(difficulty="intermediate")["overall"]["available"] == 1


def test_progress_empty_history_and_bank_gaps_are_not_failure(learning):
    service, store, _connection = learning
    store.attempts.return_value = []
    result = service.progress()
    assert result["overall"]["first_try_percent"] is None
    assert result["overall"]["unattempted"] == 4
    assert result["recommendations"][0]["action"] == "explore"
    gap = service.progress(category="fundamentals")
    assert gap["overall"]["available"] == 0
    assert gap["recommendations"][0]["action"] == "generate"
    assert service.progress(topic="filtering")["overall"]["available"] == 0


@pytest.mark.parametrize(
    "filters",
    [
        {"engine": "oracle"},
        {"difficulty": "easy"},
        {"category": "unknown"},
        {"topic": "typo"},
    ],
)
def test_progress_rejects_unknown_filters(learning, filters):
    service, _store, _connection = learning
    with pytest.raises(ValueError, match="Unknown"):
        service.progress(**filters)


def test_progress_solved_categories_recommend_new_material_without_erasing_passes(learning):
    service, store, _connection = learning
    store.attempts.return_value = [attempt(item.id, True) for item in service.bank]
    result = service.progress(category="windows")
    assert result["overall"]["first_try_percent"] == 100
    assert result["overall"]["solved"] == 3
    assert result["recommendations"][0]["action"] == "generate"


def test_facade_uses_category_filters_before_provisioning(learning):
    service, store, _connection = learning
    service.start(category="windows", topic="ranking")
    assert store.create.call_args.args[0][0].id == "example"
    with pytest.raises(ValueError, match="No exercises"):
        service.start(category="fundamentals")


def test_independent_retry_does_not_rewrite_first_attempt(learning):
    service, store, _connection = learning
    store.attempts.return_value.append(attempt("assisted", True))
    result = service.progress(category="windows")
    assert result["overall"]["solved"] == 2
    assert result["overall"]["assisted_only"] == 0
    assert result["overall"]["first_try_passes"] == 0
    assert result["overall"]["assisted_passes"] == 1


def test_evidence_caution_uses_distinct_questions_not_check_count(learning):
    service, store, _connection = learning
    service.bank = [replace(service.bank[0], id=f"question-{index}") for index in range(5)]
    store.attempts.return_value = [attempt(item.id, True) for item in service.bank]
    assert not service.progress()["overall"]["limited_evidence"]
    store.attempts.return_value = [attempt(service.bank[0].id, True)] * 20
    assert service.progress()["overall"]["limited_evidence"]


def test_effort_medians_stop_at_first_independent_pass_and_count_question_assistance(learning):
    service, store, _connection = learning
    store.attempts.return_value = [
        attempt("example", session="one"),
        attempt("example", True, True, session="one"),
        attempt("example", True, session="two"),
        attempt("example", session="later"),
        attempt("assisted", True, True, session="three"),
        attempt("unfinished", session="four"),
        attempt("unfinished", session="four"),
        attempt("fresh", True, session="five"),
    ]
    original = deepcopy(store.attempts.return_value)
    result = service.progress()
    overall = result["overall"]
    assert overall["solved_sample"] == 2
    assert overall["median_checks_to_solve"] == 2
    assert overall["median_failures_to_solve"] == 0.5
    assert overall["sessions_sample"] == 2
    assert overall["median_sessions_to_solve"] == 1.5
    assert overall["assistance_questions"] == 2
    assert overall["assistance_percent"] == 50
    assert overall["review_questions"] == 1
    assert overall["review_exercises"] == ["example"]
    assert overall["unsolved_checks"] == 3
    assert overall["attempts"] == 8
    assert result["categories"]["windows"]["median_checks_to_solve"] == 3
    assert result["topic_progress"]["ranking"]["review_questions"] == 1
    assert store.attempts.return_value == original


def test_effort_missing_session_ids_do_not_invent_complete_session_counts(learning):
    service, store, _connection = learning
    store.attempts.return_value = [
        attempt("example"),
        attempt("example", True, session="known"),
        attempt("fresh", True, session="complete"),
    ]
    overall = service.progress()["overall"]
    assert overall["solved_sample"] == 2
    assert overall["median_checks_to_solve"] == 1.5
    assert overall["sessions_sample"] == 1
    assert overall["median_sessions_to_solve"] == 1
    assert overall["assistance_percent"] == 0


def test_effort_unsolved_only_has_no_solved_median_and_retains_open_effort(learning):
    service, store, _connection = learning
    store.attempts.return_value = [attempt("example"), attempt("example", True, True)]
    overall = service.progress()["overall"]
    assert overall["solved_sample"] == overall["sessions_sample"] == 0
    assert overall["median_checks_to_solve"] is None
    assert overall["median_failures_to_solve"] is None
    assert overall["median_sessions_to_solve"] is None
    assert overall["unsolved_checks"] == 2
    assert overall["assistance_questions"] == 1
    assert overall["review_questions"] == 0


def test_effort_scope_is_applied_before_first_solve(learning):
    service, store, _connection = learning
    store.attempts.return_value = [
        attempt("example", session="one"),
        attempt("example", True, engine="sqlite", session="two"),
        attempt("example", True, True, session="three"),
    ]
    combined = service.progress()["overall"]
    assert combined["median_checks_to_solve"] == 2
    assert combined["assistance_questions"] == 0
    sqlite = service.progress(engine="sqlite")["overall"]
    assert sqlite["median_checks_to_solve"] == 1
    assert sqlite["median_sessions_to_solve"] == 1
    assert sqlite["review_questions"] == 0
    postgres = service.progress(engine="postgres")["overall"]
    assert postgres["median_checks_to_solve"] is None
    assert postgres["assistance_questions"] == 1
    assert postgres["unsolved_checks"] == 2


def test_practice_priorities_review_retry_solved_work_before_unattempted_categories(learning):
    service, store, _connection = learning
    store.attempts.return_value = [attempt("example"), attempt("example", True)]
    recommendation = service.progress()["recommendations"][0]
    assert recommendation["action"] == "review"
    assert recommendation["exercises"] == ["example"]
    assert "failed checks" in recommendation["reason"]
    assert service.progress()["overall"]["solved"] == 1


def test_unresolved_categories_rank_before_historical_review_and_new_work(learning):
    service, store, _connection = learning
    question = service.bank[0]
    service.bank = [
        replace(question, id="retry", tags=("ranking",)),
        replace(question, id="open", tags=("joins",)),
        replace(question, id="new", tags=("dates",)),
    ]
    service.categories = Categories(
        (
            Category("retry", "Retry", "Historical effort", ("ranking",)),
            Category("open", "Open", "Unfinished", ("joins",)),
            Category("new", "New", "Unexplored", ("dates",)),
        )
    )
    store.attempts.return_value = [attempt("retry"), attempt("retry", True), attempt("open")]
    result = service.progress()
    assert [item["action"] for item in result["recommendations"]] == [
        "revisit",
        "review",
        "explore",
    ]
    assert [item["category"] for item in result["recommendations"]] == ["open", "retry", "new"]
    store.record.assert_not_called()
