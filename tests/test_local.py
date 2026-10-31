import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from sql_practice.cli import app
from sql_practice.environment import LocalEnvironment, project_root
from sql_practice.exercises import content_version, load_bank, load_categories
from sql_practice.sessions import SessionStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_session_persistence_resume_and_reset(tmp_path):
    store = SessionStore(tmp_path)
    question = load_bank(ROOT)[0]
    schema_document = tmp_path / "docs/schema.md"
    schema_document.parent.mkdir()
    schema_document.write_text("# Business schema\n")
    with pytest.raises(ValueError, match="No current"):
        store.get()
    session = store.create([question], "sqlite", "v1", 42)
    folder = Path(store.paths(session)[question.id])
    schema_link = "../../../../docs/schema.md"
    assert f"[Business schema]({schema_link})" in (folder / "prompt.md").read_text()
    assert (folder / schema_link).resolve() == schema_document.resolve()
    assert (folder / schema_link).is_file()
    (folder / "answer.sql").write_text("SELECT 1")
    assert store.get()["id"] == session["id"]
    assert store.answer(session["id"], question.id) == "SELECT 1"
    session["hints"][question.id] = 1
    store.save(session)
    assert store.get()["hints"][question.id] == 1
    store.record({"passed": True})
    assert store.attempts()[0]["passed"]
    with pytest.raises(ValueError, match="Invalid session"):
        store.get("../../something")
    with pytest.raises(ValueError, match="not part"):
        store.answer(session["id"], "../no")
    with pytest.raises(ValueError, match="not found"):
        store.get("aaaaaaaaaaaa")
    store.save_sandbox_version("sqlite", "v1")
    store.assert_sandbox_version("sqlite", "v1")
    with pytest.raises(ValueError, match="reset"):
        store.assert_sandbox_version("sqlite", "v2")
    LocalEnvironment(tmp_path).reset("sqlite")
    assert store.answer(session["id"], question.id) == "SELECT 1"


@pytest.mark.integration
def test_environment_configuration_and_scoped_commands(tmp_path, monkeypatch):
    local = LocalEnvironment(tmp_path)
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="ok", stderr=""))
    monkeypatch.setattr("sql_practice.environment.subprocess.run", runner)
    monkeypatch.setattr("sql_practice.environment.shutil.which", lambda _name: "/bin/docker")
    assert local.up("postgres") == "ok"
    assert local.up("sqlite").startswith("SQLite")
    assert local.backend("mysql").kind == "mysql"
    assert local.backend("postgres").kind == "postgres"
    local.down("mysql")
    local.reset("mysql")
    volume_call = runner.call_args.args[0]
    assert volume_call == ["docker", "volume", "rm", f"{local.project}_mysql_data"]
    assert "password" in local.configuration()
    assert (local.directory / "local.json").stat().st_mode & 0o777 == 0o600
    assert local.doctor()["docker"] == "ok"
    for action in (local.up, local.down, local.reset, local.backend):
        with pytest.raises(ValueError, match="Unknown engine"):
            action("production")


def test_environment_failure_paths_with_fakes(monkeypatch):
    local = LocalEnvironment(Path("/fake"))
    monkeypatch.setattr("sql_practice.environment.shutil.which", lambda _name: None)
    assert local.doctor()["docker"] == "not installed"
    with pytest.raises(ValueError, match="not installed"):
        local.compose("ps")
    monkeypatch.setattr("sql_practice.environment.shutil.which", lambda _name: "docker")
    monkeypatch.setattr(
        "sql_practice.environment.subprocess.run",
        Mock(side_effect=subprocess.TimeoutExpired("docker", 10)),
    )
    assert "did not respond" in local.doctor()["docker"]
    monkeypatch.setenv("SQL_PRACTICE_ROOT", "/not/a/practice/project")
    monkeypatch.setattr(Path, "is_file", lambda _self: False)
    with pytest.raises(ValueError, match="repository"):
        project_root()


@pytest.mark.integration
def test_cli_sqlite_learner_flow(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(ROOT / "exercises", tmp_path / "exercises")
    shutil.copytree(ROOT / "datasets", tmp_path / "datasets")
    shutil.copyfile(ROOT / "categories.yaml", tmp_path / "categories.yaml")
    monkeypatch.setenv("SQL_PRACTICE_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "start",
            "--engine",
            "sqlite",
            "--exercise",
            "customer-spending",
            "--seed",
            "42",
            "--no-open",
        ],
    )
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    directory = Path(document["paths"]["customer-spending"])
    assert document["files"]["customer-spending"] == {
        "prompt.md": str(directory / "prompt.md"),
        "answer.sql": str(directory / "answer.sql"),
    }
    assert all(
        Path(file_path).is_file() for file_path in document["files"]["customer-spending"].values()
    )
    (directory / "answer.sql").write_text(
        "SELECT id AS customer_id, 0 AS total_cents FROM customers"
    )
    assert runner.invoke(app, ["check"]).exit_code == 1
    assert runner.invoke(app, ["hint"]).exit_code == 0
    revealed = runner.invoke(app, ["solution"])
    (directory / "answer.sql").write_text(revealed.output)
    assert runner.invoke(app, ["run"]).exit_code == 0
    checked = runner.invoke(app, ["check", "--json"])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["assisted"]
    resumed = runner.invoke(app, ["resume", "--no-open"])
    assert resumed.exit_code == 0
    assert json.loads(resumed.output)["files"] == document["files"]
    assert (directory / "answer.sql").read_text() == revealed.output
    assert json.loads(runner.invoke(app, ["progress", "--json"]).output)["total_attempts"] == 2
    assert runner.invoke(app, ["db", "reset", "--engine", "sqlite", "--yes"]).exit_code == 0
    assert (directory / "answer.sql").exists()
    assert content_version(tmp_path) == content_version(ROOT)


@pytest.mark.integration
def test_category_edits_preserve_sessions_and_progress_is_read_only(tmp_path, monkeypatch):
    import shutil

    import yaml

    shutil.copytree(ROOT / "exercises", tmp_path / "exercises")
    shutil.copyfile(ROOT / "categories.yaml", tmp_path / "categories.yaml")
    version = content_version(tmp_path)
    question = load_bank(tmp_path)[0]
    store = SessionStore(tmp_path)
    session = store.create([question], "sqlite", version, 1)
    store.save_sandbox_version("sqlite", version)
    store.record(
        {
            "exercise": question.id,
            "engine": "sqlite",
            "tags": list(question.tags),
            "passed": True,
            "assisted": False,
        }
    )
    document = yaml.safe_load((tmp_path / "categories.yaml").read_text())
    document["categories"][0]["label"] = "Updated label"
    (tmp_path / "categories.yaml").write_text(yaml.safe_dump(document))
    assert content_version(tmp_path) == version
    assert load_categories(tmp_path).entries[0].label == "Updated label"
    snapshot = {
        file_path: file_path.read_bytes()
        for file_path in store.directory.rglob("*")
        if file_path.is_file()
    }
    monkeypatch.setenv("SQL_PRACTICE_ROOT", str(tmp_path))
    forbidden = Mock(side_effect=AssertionError("Reporting must not provision or query a database"))
    monkeypatch.setattr(LocalEnvironment, "up", forbidden)
    monkeypatch.setattr(LocalEnvironment, "backend", forbidden)
    result = CliRunner().invoke(app, ["progress", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["overall"]["solved"] == 1
    assert store.get()["id"] == session["id"]
    assert snapshot == {
        file_path: file_path.read_bytes()
        for file_path in store.directory.rglob("*")
        if file_path.is_file()
    }
    forbidden.assert_not_called()


@pytest.mark.integration
def test_category_loader_reports_missing_and_malformed_files(tmp_path):
    with pytest.raises(OSError):
        load_categories(tmp_path)
    (tmp_path / "categories.yaml").write_text("categories: [")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_categories(tmp_path)
