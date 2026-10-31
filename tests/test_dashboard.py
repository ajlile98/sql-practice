from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from sql_practice import cli
from sql_practice.exercises import Categories, Category, Exercise
from sql_practice.progress import learning_progress


@pytest.fixture(name="dashboard_service")
def dashboard_service_fixture(monkeypatch):
    practice = Mock()
    practice.bank = [
        Exercise(
            "example",
            "Example",
            "advanced",
            ("windows",),
            "Prompt",
            (),
            {"shared": "SELECT 1"},
            ("value",),
            False,
        )
    ]
    practice.categories = Categories(
        (Category("windows", "Windows", "Window skills", ("windows",)),)
    )
    practice.history = [
        {
            "exercise": "example",
            "engine": "postgres",
            "tags": ["windows"],
            "passed": False,
            "assisted": False,
            "session": "first",
        },
        {
            "exercise": "example",
            "engine": "postgres",
            "tags": ["windows"],
            "passed": True,
            "assisted": False,
            "session": "first",
        },
    ]
    practice.progress.side_effect = lambda **scope: learning_progress(
        practice.bank, practice.history, practice.categories, **scope
    )
    monkeypatch.setattr(cli, "service", lambda: practice)
    return practice


def dashboard_app():
    return AppTest.from_string(
        "from sql_practice.dashboard import main\nmain()", default_timeout=20
    )


def test_dashboard_shows_report_and_applies_filters(dashboard_service):
    app = dashboard_app().run()
    assert not app.exception
    assert app.title[0].value == "SQL Practice"
    assert app.metric[0].value == "1 / 1"
    assert app.metric[1].value == "0%"
    assert any("Limited evidence" in warning.value for warning in app.warning)
    assert any("example" in text.value for text in app.markdown)
    app.selectbox(key="engine").select("mysql").run()
    assert not app.exception
    assert app.metric[0].value == "0 / 1"
    dashboard_service.progress.assert_called_with(
        engine="mysql", difficulty=None, category=None, topic=None
    )
    app.selectbox(key="difficulty").select("advanced")
    app.selectbox(key="category").select("windows")
    app.selectbox(key="topic").select("windows")
    app.radio[0].set_value("Topics").run()
    assert not app.exception
    dashboard_service.progress.assert_called_with(
        engine="mysql", difficulty="advanced", category="windows", topic="windows"
    )
    app.button[0].click().run()
    assert not app.exception


def test_dashboard_handles_empty_history_and_empty_scope(dashboard_service):
    dashboard_service.history = []
    app = dashboard_app().run()
    assert not app.exception
    assert app.metric[1].value == "N/A"
    assert any("No graded attempts" in message.value for message in app.info)
    app.selectbox(key="difficulty").select("intermediate").run()
    assert not app.exception
    assert app.metric[0].value == "0 / 0"
    assert any("No exercises" in message.value for message in app.info)


def test_dashboard_reports_load_errors_without_traceback(monkeypatch):
    monkeypatch.setattr(cli, "service", Mock(side_effect=ValueError("Invalid category registry")))
    app = dashboard_app().run()
    assert not app.exception
    assert (
        app.error[0].value
        == "Could not load local progress. Check the exercise and category files."
    )
