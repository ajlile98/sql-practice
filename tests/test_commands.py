import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from sql_practice import cli
from sql_practice.exercises import Categories, Category, Exercise
from sql_practice.grading import QueryResult
from sql_practice.progress import learning_progress


def test_dashboard_launches_local_streamlit_with_project_root(monkeypatch, tmp_path):
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(cli.subprocess, "run", launch)
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli.app, ["dashboard", "--port", "8511"])
    assert result.exit_code == 0, result.output
    arguments = launch.call_args.args[0]
    assert arguments[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert Path(arguments[4]).name == "dashboard.py"
    assert "--server.address=127.0.0.1" in arguments
    assert "--server.port=8511" in arguments
    assert launch.call_args.kwargs["env"]["SQL_PRACTICE_ROOT"] == str(tmp_path)
    assert "http://127.0.0.1:8511" in result.output


def test_dashboard_propagates_server_failure_and_rejects_invalid_port(monkeypatch):
    launch = Mock(return_value=Mock(returncode=2))
    monkeypatch.setattr(cli.subprocess, "run", launch)
    assert CliRunner().invoke(cli.app, ["dashboard"]).exit_code == 2
    launch.reset_mock()
    assert CliRunner().invoke(cli.app, ["dashboard", "--port", "0"]).exit_code == 2
    launch.assert_not_called()


def test_database_commands_dispatch_without_live_effects(monkeypatch):
    local = Mock()
    local.doctor.return_value = {"sqlite": "available"}
    local.up.return_value = "ready"
    local.down.return_value = "stopped"
    local.compose.return_value = "running"
    local.directory = MagicMock()
    (local.directory / "local.json").exists.return_value = False
    monkeypatch.setattr(cli, "environment", lambda: local)
    runner = CliRunner()
    for command in (["doctor"], ["db", "up"], ["db", "down"], ["db", "status"]):
        assert runner.invoke(cli.app, command).exit_code == 0
    (local.directory / "local.json").exists.return_value = True
    assert runner.invoke(cli.app, ["db", "status"]).exit_code == 0
    aborted = runner.invoke(cli.app, ["db", "reset"], input="n\n")
    assert aborted.exit_code != 0
    local.reset.assert_not_called()
    assert runner.invoke(cli.app, ["db", "reset"], input="y\n").exit_code == 0
    local.reset.assert_called_once_with("postgres")


def test_cli_sanitizes_database_setup_errors(monkeypatch):
    local = Mock()
    local.up.side_effect = OperationalError("secret sql", {}, Exception("private"))
    monkeypatch.setattr(cli, "environment", lambda: local)
    result = CliRunner().invoke(cli.app, ["db", "up"])
    assert result.exit_code == 1
    assert "doctor" in result.output
    assert "private" not in result.output


@pytest.fixture(name="result_cli")
def result_cli_fixture(monkeypatch):
    practice = Mock()
    practice.run.return_value = QueryResult(("customer_id", "paid_orders"), ((1, 2), (2, None)))
    monkeypatch.setattr(cli, "service", lambda: practice)
    return practice


@pytest.fixture(name="check_cli")
def check_cli_fixture(result_cli):
    result_cli.check.return_value = {
        "session": "saved",
        "exercise": "example",
        "engine": "sqlite",
        "tags": ["joins"],
        "passed": True,
        "assisted": False,
        "fixtures": [
            {"fixture": name, "passed": True, "message": "Correct (2 rows)"}
            for name in ("base", "edge", "empty", "no-sales")
        ],
    }
    return result_cli


def test_check_shows_each_verdict_and_overall_summary(check_cli):
    result = CliRunner().invoke(cli.app, ["check", "--session", "saved", "--question", "example"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    for name in ("base", "edge", "empty", "no-sales"):
        assert f"PASS {name}: Correct (2 rows)" in lines
    assert "PASS 4/4 tests passed" in lines
    assert '"fixtures"' not in result.output
    check_cli.check.assert_called_once_with("saved", "example")


def test_check_failures_are_clear_and_assistance_is_visible(check_cli):
    outcome = check_cli.check.return_value
    outcome["passed"] = False
    outcome["assisted"] = True
    outcome["fixtures"][1].update(passed=False, message="Expected 3 rows.\nGot 2 rows.")
    result = CliRunner().invoke(cli.app, ["check"])
    assert result.exit_code == 1
    assert "FAIL edge: Expected 3 rows. Got 2 rows." in result.output.splitlines()
    assert "PASS base:" in result.output
    assert "FAIL 3/4 tests passed (assisted)" in result.output


@pytest.mark.parametrize("passed, color", [(True, "\x1b[32m"), (False, "\x1b[31m")])
def test_check_verdicts_use_green_or_red(check_cli, passed, color):
    outcome = check_cli.check.return_value
    outcome["passed"] = passed
    for case in outcome["fixtures"]:
        case["passed"] = passed
    result = CliRunner().invoke(cli.app, ["check"], color=True)
    assert result.exit_code == (0 if passed else 1)
    assert color in result.output
    assert ("PASS" if passed else "FAIL") in result.output


@pytest.mark.parametrize("passed", [True, False])
def test_check_json_preserves_results_and_exit_codes(check_cli, passed):
    outcome = check_cli.check.return_value
    outcome["passed"] = passed
    outcome["fixtures"][0]["passed"] = passed
    result = CliRunner().invoke(cli.app, ["check", "--json"])
    assert result.exit_code == (0 if passed else 1)
    assert json.loads(result.output) == outcome
    assert "\x1b" not in result.output


def test_run_prints_a_table_by_default(result_cli):
    result = CliRunner().invoke(
        cli.app, ["run", "--session", "saved", "--question", "repeat-customers"]
    )
    assert result.exit_code == 0, result.output
    assert "| customer_id" in result.output
    assert "paid_orders" in result.output
    assert "NULL" in result.output
    assert "2 rows" in result.output
    assert '"columns"' not in result.output
    result_cli.run.assert_called_once_with("saved", "repeat-customers")


@pytest.mark.usefixtures("result_cli")
def test_run_json_preserves_machine_readable_format():
    result = CliRunner().invoke(cli.app, ["run", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "columns": ["customer_id", "paid_orders"],
        "rows": [[1, 2], [2, None]],
        "row_count": 2,
    }


def test_run_empty_results_keep_headers(result_cli):
    result_cli.run.return_value = QueryResult(("customer_id", "paid_orders"), ())
    result = CliRunner().invoke(cli.app, ["run"])
    assert result.exit_code == 0, result.output
    assert "customer_id" in result.output and "paid_orders" in result.output
    assert "0 rows" in result.output


@pytest.mark.parametrize("arguments", [["run"], ["run", "--json"]])
def test_run_preview_limit_is_explicit(result_cli, arguments):
    result_cli.run.return_value = QueryResult(("value",), tuple((number,) for number in range(35)))
    result = CliRunner().invoke(cli.app, arguments)
    assert result.exit_code == 0, result.output
    if "--json" in arguments:
        document = json.loads(result.output)
        assert len(document["rows"]) == 30
        assert document["row_count"] == 35
    else:
        assert "35 rows (showing first 30)" in result.output
        assert "34" not in result.output


def test_run_formats_values_without_interpreting_markup(result_cli):
    result_cli.run.return_value = QueryResult(
        ("label", "amount", "day", "empty"),
        (("[red]literal[/red]", Decimal("12.50"), date(2025, 1, 1), ""),),
    )
    result = CliRunner().invoke(cli.app, ["run"])
    assert result.exit_code == 0, result.output
    assert "[red]literal[/red]" in result.output
    assert "12.50" in result.output and "2025-01-01" in result.output
    assert "1 row" in result.output


@pytest.fixture(name="opening_cli")
def opening_cli_fixture(monkeypatch):
    store = Mock()
    session = {"id": "example", "exercises": ["first", "second"]}
    files = {
        question: {
            filename: f"/project with spaces/{question}/{filename}"
            for filename in ("prompt.md", "answer.sql")
        }
        for question in session["exercises"]
    }
    store.get.return_value = session
    store.paths.return_value = {}
    store.files.return_value = files
    store.attempts.return_value = []
    practice = Mock(store=store)
    practice.categories = Categories((Category("windows", "Windows", "Sequences", ("windows",)),))
    practice.bank = [
        Exercise(
            question,
            question,
            "advanced",
            ("windows",),
            "Prompt",
            ("Hint",),
            {"shared": "SELECT 1"},
            ("value",),
            False,
        )
        for question in session["exercises"]
    ]
    practice.start.return_value = session
    monkeypatch.setattr(cli, "service", lambda: practice)
    monkeypatch.setattr(cli, "environment", Mock())
    monkeypatch.setattr(cli, "project_root", lambda: Path("/fake"))
    monkeypatch.setattr(cli, "SessionStore", lambda _root: store)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/bin/code")
    launcher = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(cli.subprocess, "run", launcher)
    return store, launcher


def test_start_forwards_category_and_rejects_invalid_category_before_io(opening_cli, monkeypatch):
    store, _launcher = opening_cli
    practice = cli.service()
    start_session = Mock(return_value=store.get.return_value)
    monkeypatch.setattr(practice, "start", start_session)
    local = Mock()
    monkeypatch.setattr(cli, "environment", lambda: local)
    result = CliRunner().invoke(cli.app, ["start", "--category", "windows", "--no-open"])
    assert result.exit_code == 0, result.output
    assert start_session.call_args.kwargs["category"] == "windows"
    local.reset_mock()
    result = CliRunner().invoke(cli.app, ["start", "--category", "typo", "--no-open"])
    assert result.exit_code == 1
    assert "Unknown category" in result.output
    local.up.assert_not_called()


@pytest.fixture(name="progress_cli")
def progress_cli_fixture(opening_cli, monkeypatch):
    _store, _launcher = opening_cli
    practice = cli.service()
    registry = Categories(
        (
            Category("windows", "Windows", "Sequences", ("windows",)),
            Category("empty", "[red]Empty[/red]", "No material", ("filtering",)),
        )
    )
    outcome = learning_progress(practice.bank, [], registry)
    progress_call = Mock(return_value=outcome)
    monkeypatch.setattr(practice, "progress", progress_call)
    return progress_call, outcome


@pytest.mark.parametrize("width", [60, 120])
def test_progress_prints_readable_metrics_and_content_gaps(progress_cli, monkeypatch, width):
    _progress_call, _outcome = progress_cli
    from rich.console import Console

    monkeypatch.setattr(cli, "Console", lambda **kwargs: Console(width=width, **kwargs))
    result = CliRunner().invoke(cli.app, ["progress"])
    assert result.exit_code == 0, result.output
    assert "0/2" in result.output
    assert "[red]Empty[/red]" in result.output
    assert "No exercises available" in result.output
    assert "Limited evidence" in result.output
    assert '"overall"' not in result.output


def test_progress_json_preserves_counters_and_forwards_scope(progress_cli):
    progress_call, outcome = progress_cli
    result = CliRunner().invoke(
        cli.app,
        [
            "progress",
            "--json",
            "--category",
            "windows",
            "--engine",
            "sqlite",
            "--difficulty",
            "advanced",
            "--topic",
            "ranking",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == outcome
    progress_call.assert_called_once_with(
        engine="sqlite", difficulty="advanced", category="windows", topic="ranking"
    )


def test_progress_topic_view_and_invalid_view(progress_cli):
    progress_call, _outcome = progress_cli
    result = CliRunner().invoke(cli.app, ["progress", "--by", "topic"])
    assert result.exit_code == 0, result.output
    assert "filtering" in result.output
    progress_call.reset_mock()
    result = CliRunner().invoke(cli.app, ["progress", "--by", "typo"])
    assert result.exit_code == 1
    progress_call.assert_not_called()


def test_progress_displays_scope_and_history_notes(progress_cli):
    _progress_call, outcome = progress_cli
    outcome["scope"].update(engine="sqlite", difficulty="advanced", category="windows")
    outcome["archived_attempts"] = 2
    outcome["unmapped_tags"] = ["custom-tag"]
    result = CliRunner().invoke(cli.app, ["progress"])
    assert result.exit_code == 0, result.output
    assert "engine=sqlite" in result.output and "difficulty=advanced" in result.output
    assert "Archived checks excluded from current coverage: 2" in result.output
    assert "custom-tag" in result.output


@pytest.mark.parametrize("width", [60, 120])
def test_progress_displays_effort_medians_with_samples_and_review_ids(
    progress_cli, monkeypatch, width
):
    _progress_call, outcome = progress_cli
    from rich.console import Console

    monkeypatch.setattr(cli, "Console", lambda **kwargs: Console(width=width, **kwargs))
    outcome["categories"]["windows"].update(
        attempted=2,
        solved=1,
        solved_sample=1,
        median_checks_to_solve=3,
        median_failures_to_solve=1,
        sessions_sample=1,
        median_sessions_to_solve=2,
        assistance_questions=1,
        review_questions=1,
        unsolved_checks=2,
    )
    outcome["overall"]["unsolved_checks"] = 2
    outcome["recommendations"] = [
        {
            "category": "windows",
            "label": "Windows",
            "action": "review",
            "reason": "Retry a solved question",
            "exercises": ["first"],
        }
    ]
    result = CliRunner().invoke(cli.app, ["progress"])
    assert result.exit_code == 0, result.output
    assert "Effort" in result.output
    assert "3 (n=1)" in result.output
    assert "2 (n=1)" in result.output
    assert "1/2" in result.output
    assert "Review exercises: first" in result.output
    assert "Ongoing checks: 2" in result.output


def test_progress_without_solved_questions_shows_no_invented_medians(progress_cli):
    _progress_call, _outcome = progress_cli
    result = CliRunner().invoke(cli.app, ["progress"])
    assert result.exit_code == 0, result.output
    assert "effort metrics are N/A" in result.output


@pytest.mark.parametrize("filters", [[], ["--topic", "windows"]])
def test_start_prompts_to_generate_when_matching_bank_is_exhausted(opening_cli, filters):
    store, _launcher = opening_cli
    store.attempts.return_value = [
        {"exercise": question, "passed": True, "assisted": False}
        for question in ("first", "second")
    ]
    result = CliRunner().invoke(cli.app, ["start", "--no-open", *filters])
    assert result.exit_code == 0, result.output
    assert "All matching exercises are solved" in result.stderr
    assert "generate new SQL practice exercises" in result.stderr
    assert "files" in json.loads(result.stdout)


@pytest.mark.parametrize("assisted, explicit", [(True, False), (False, True)])
def test_start_does_not_warn_for_assisted_passes_or_explicit_retries(
    opening_cli, assisted, explicit
):
    store, _launcher = opening_cli
    store.attempts.return_value = [
        {"exercise": question, "passed": True, "assisted": assisted}
        for question in ("first", "second")
    ]
    command = ["start", "--no-open"]
    if explicit:
        command.extend(["--exercise", "first"])
    result = CliRunner().invoke(cli.app, command)
    assert result.exit_code == 0, result.output
    assert not result.stderr


def test_start_rejects_mixed_batch_before_starting_database(opening_cli, monkeypatch):
    store, _launcher = opening_cli
    store.attempts.return_value = [{"exercise": "first", "passed": True, "assisted": False}]
    local = Mock()
    start_session = Mock()
    monkeypatch.setattr(cli, "environment", lambda: local)
    monkeypatch.setattr(cli.service(), "start", start_session)
    result = CliRunner().invoke(cli.app, ["start", "--count", "2", "--no-open"])
    assert result.exit_code == 1
    assert "Only 1 unsolved" in result.output
    local.up.assert_not_called()
    start_session.assert_not_called()


@pytest.mark.parametrize("command", [["start", "--count", "2"], ["resume"]])
def test_start_and_resume_open_prompts_and_answers_by_default(opening_cli, command):
    store, launcher = opening_cli
    result = CliRunner().invoke(cli.app, command)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["files"] == store.files.return_value
    assert launcher.call_args.args[0] == [
        "/bin/code",
        "--reuse-window",
        "/project with spaces/first/prompt.md",
        store.files.return_value["first"]["answer.sql"],
        "/project with spaces/second/prompt.md",
        store.files.return_value["second"]["answer.sql"],
    ]
    assert launcher.call_args.kwargs["timeout"] == 10
    assert "shell" not in launcher.call_args.kwargs


@pytest.mark.parametrize("command", [["start", "--count", "2"], ["resume"]])
def test_start_and_resume_can_disable_opening(opening_cli, command):
    _store, launcher = opening_cli
    result = CliRunner().invoke(cli.app, [*command, "--no-open"])
    assert result.exit_code == 0, result.output
    assert "files" in json.loads(result.stdout)
    launcher.assert_not_called()


def test_missing_editor_does_not_fail_session(opening_cli, monkeypatch):
    _store, launcher = opening_cli
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    result = CliRunner().invoke(cli.app, ["resume"])
    assert result.exit_code == 0, result.output
    assert "code" in result.stderr and "Warning" in result.stderr
    assert "files" in json.loads(result.stdout)
    launcher.assert_not_called()


@pytest.mark.parametrize(
    "failure", [OSError("failed"), subprocess.TimeoutExpired("code", 10), None]
)
def test_editor_failure_does_not_fail_session(opening_cli, failure):
    _store, launcher = opening_cli
    if failure:
        launcher.side_effect = failure
    else:
        launcher.return_value = subprocess.CompletedProcess([], 1)
    result = CliRunner().invoke(cli.app, ["resume"])
    assert result.exit_code == 0, result.output
    assert "Warning" in result.stderr
    assert "files" in json.loads(result.stdout)


def test_validate_bank_dispatch_and_mismatches_with_fake_backend(monkeypatch):
    question = Exercise(
        "example",
        "Example",
        "advanced",
        ("windows",),
        "Prompt",
        ("Hint",),
        {"shared": "SELECT 1 AS value"},
        ("value",),
        False,
    )
    answer = QueryResult(("value",), ((1,),))
    query = Mock(return_value=answer)

    class FakeBackend:
        @contextmanager
        def fixture(self, _dataset):
            yield Mock(query=query)

    local = Mock()
    local.backend.return_value = FakeBackend()
    monkeypatch.setattr(cli, "environment", lambda: local)
    monkeypatch.setattr(cli, "project_root", lambda: Path("/fake"))
    monkeypatch.setattr(cli, "load_dataset", lambda _root, _fixture, **_kwargs: object())
    monkeypatch.setattr(cli, "load_bank", lambda _root: [question])
    runner = CliRunner()
    result = runner.invoke(cli.app, ["validate-bank", "--all-engines"])
    assert result.exit_code == 0, result.output
    assert "12 reference executions" in result.output
    result = runner.invoke(cli.app, ["validate-bank", "--engine", "unknown"])
    assert result.exit_code == 1
    query.return_value = QueryResult(("wrong",), ((1,),))
    assert runner.invoke(cli.app, ["validate-bank"]).exit_code == 1
    query.return_value = QueryResult(("value",), ())
    assert "positive base case" in runner.invoke(cli.app, ["validate-bank"]).output


@pytest.mark.integration
def test_sqlite_validate_command():
    result = CliRunner().invoke(cli.app, ["validate-bank"])
    assert result.exit_code == 0, result.output
    assert "104 reference executions" in result.output
