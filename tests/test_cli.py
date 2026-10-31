from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from sql_practice import cli
from sql_practice.cli import app
from sql_practice.exercises import Categories, Category

pytestmark = pytest.mark.integration


def test_help_and_list_are_available_without_docker():
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["list", "--topic", "windows"])
    assert result.exit_code == 0, result.output
    assert "median-order-value" in result.output
    assert "never-paid" not in result.output


def test_invalid_filters_and_missing_session_have_useful_errors():
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--topic", "unknown"])
    assert result.exit_code == 1
    assert "No exercises" in result.output


@pytest.mark.parametrize(
    "history, expected",
    [
        ([], "NEW"),
        ([("other", True, False)], "NEW"),
        ([("example", False, False)], "ATTEMPTED"),
        ([("example", False, True)], "ATTEMPTED"),
        ([("example", True, True)], "ASSISTED"),
        ([("example", True, True), ("example", False, False)], "ASSISTED"),
        ([("example", True, False)], "SOLVED"),
        ([("example", True, True), ("example", True, False)], "SOLVED"),
        ([("example", True, False), ("example", False, False)], "SOLVED"),
    ],
)
def test_list_shows_best_recorded_status_without_mutating_history(monkeypatch, history, expected):
    bank = [SimpleNamespace(id="example", difficulty="intermediate", tags=("joins",))]
    store = Mock()
    store.attempts.return_value = [
        {"exercise": exercise_id, "passed": passed, "assisted": assisted}
        for exercise_id, passed, assisted in history
    ]
    monkeypatch.setattr(cli, "project_root", lambda: Path("/fake"))
    monkeypatch.setattr(cli, "load_bank", lambda _root: bank)
    monkeypatch.setattr(cli, "load_categories", lambda _root: Categories())
    monkeypatch.setattr(cli, "SessionStore", lambda _root: store)
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    line = next(line for line in result.output.splitlines() if "example" in line)
    assert line.split()[0] == expected
    store.attempts.assert_called_once_with()
    store.record.assert_not_called()
    store.save.assert_not_called()


def test_list_category_filter_keeps_tags_and_status(monkeypatch):
    bank = [
        SimpleNamespace(id="example", difficulty="advanced", tags=("windows",)),
        SimpleNamespace(id="other", difficulty="advanced", tags=("joins",)),
    ]
    store = Mock()
    store.attempts.return_value = []
    registry = Categories((Category("sequences", "Sequences", "Ranking", ("windows",)),))
    monkeypatch.setattr(cli, "project_root", lambda: Path("/fake"))
    monkeypatch.setattr(cli, "load_bank", lambda _root: bank)
    monkeypatch.setattr(cli, "load_categories", lambda _root: registry)
    monkeypatch.setattr(cli, "SessionStore", lambda _root: store)
    result = CliRunner().invoke(app, ["list", "--category", "sequences"])
    assert result.exit_code == 0, result.output
    assert "example" in result.output and "other" not in result.output
    assert "windows" in result.output and "Sequences" in result.output
    store.record.assert_not_called()
