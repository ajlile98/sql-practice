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
def test_scoped_sessions_mixed_datasets_and_unrelated_changes(tmp_path):
    import shutil
    from dataclasses import replace

    from sql_practice.database import SQLiteBackend
    from sql_practice.datasets import dataset_version, load_dataset
    from sql_practice.practice import PracticeService

    shutil.copytree(ROOT / "datasets/business", tmp_path / "datasets/business")
    shutil.copytree(ROOT / "datasets/business", tmp_path / "datasets/other")
    orders = tmp_path / "datasets/other/tables/orders.csv"
    orders.write_text(orders.read_text().replace("paid,5000\n", "paid,5001\n", 1))
    other_doc = tmp_path / "datasets/other/schema.md"
    other_doc.write_text("# Other schema\n")
    question = load_bank(ROOT)[0]
    other = replace(question, id="other-spending", dataset="other")
    store = SessionStore(tmp_path)
    store.save_sandbox_version("sqlite", "obsolete-global-version")
    facade = PracticeService(
        [question, other], "global1", store,
        lambda _engine: SQLiteBackend(store.directory),
        lambda fixture, *, name: load_dataset(tmp_path, fixture, name=name),
        dataset_versions=lambda name: dataset_version(tmp_path, name),
    )
    session = facade.start(engine="sqlite", count=2)
    assert session["format"] == 2
    paths = store.paths(session)
    for item in (question, other):
        Path(paths[item.id], "answer.sql").write_text(item.sql("sqlite"))
        result = facade.run(question=item.id)
        assert dict(result.rows)[1] == (11000 if item.dataset == "business" else 11001)
        assert facade.check(question=item.id)["passed"]
    manifest = (store._folder(session["id"]) / "session.json").read_bytes()
    assert "../../../../datasets/other/schema.md" in Path(paths[other.id], "prompt.md").read_text()
    facade.version = "global2"
    facade.bank.append(replace(question, id="unrelated"))
    assert facade.run(question=question.id).rows
    other_doc.write_text("# Changed documentation only\n")
    assert facade.run(question=other.id).rows
    facade.bank[1] = replace(other, prompt="Changed business rule")
    with pytest.raises(ValueError, match="Exercise other-spending changed"):
        facade.run(question=other.id)
    assert facade.run(question=question.id).rows
    facade.bank[1] = other
    table = tmp_path / "datasets/other/tables/customers.csv"
    table.write_text(table.read_text().replace("Ada", "Another name"))
    with pytest.raises(ValueError, match="Dataset other changed"):
        facade.run(question=other.id)
    assert facade.run(question=question.id).rows
    facade.start(engine="sqlite", identifier=other.id)
    assert len(list(store.directory.glob("sandbox*.sqlite"))) == 3
    assert (store._folder(session["id"]) / "session.json").read_bytes() == manifest
    assert Path(paths[question.id], "answer.sql").read_text() == question.sql("sqlite")


@pytest.mark.integration
def test_revenue_cli_session_schema_and_original_request(tmp_path, monkeypatch):
    import shutil

    shutil.copytree(ROOT / "exercises", tmp_path / "exercises")
    shutil.copytree(ROOT / "datasets", tmp_path / "datasets")
    shutil.copyfile(ROOT / "categories.yaml", tmp_path / "categories.yaml")
    monkeypatch.setenv("SQL_PRACTICE_ROOT", str(tmp_path))
    runner = CliRunner()
    exercise_id = "customer-product-revenue-windows"
    started = runner.invoke(app, ["start", "--engine", "sqlite", "--exercise", exercise_id, "--no-open"])
    assert started.exit_code == 0, started.output
    document = json.loads(started.output)
    assert document["session"]["bindings"][exercise_id]["dataset"] == "revenue"
    folder = Path(document["paths"][exercise_id])
    schema_link = "../../../../datasets/revenue/schema.md"
    prompt = (folder / "prompt.md").read_text()
    assert schema_link in prompt and (folder / schema_link).is_file()
    assert "Dataset: revenue" in prompt and "As-of: 2025-03-01" in prompt
    assert (folder / "answer.sql").read_text() == "-- Write one SELECT or WITH query here.\n"
    question = next(item for item in load_bank(tmp_path) if item.id == exercise_id)
    (folder / "answer.sql").write_text(question.sql("sqlite"))
    preview = runner.invoke(app, ["run", "--json"])
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["rows"][0] == [1, 1, 2000, 4000]
    checked = runner.invoke(app, ["check", "--json"])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["passed"]


@pytest.mark.integration
def test_dataset_ids_and_semantic_exercise_hash(tmp_path):
    import shutil
    from dataclasses import replace

    from sql_practice.datasets import dataset_version, load_dataset
    from sql_practice.exercises import exercise_version

    for name in ("../business", "Bad", "business/other", "", None):
        with pytest.raises(ValueError, match="Invalid dataset"):
            load_dataset(tmp_path, name=name)
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_dataset(tmp_path, name="missing")
    shutil.copytree(ROOT / "datasets/business", tmp_path / "datasets/business")
    parsed = load_dataset(tmp_path)
    assert parsed.name == "business" and parsed.as_of == "2025-03-01"
    assert parsed.identity == load_dataset(tmp_path, "edge").identity
    version = dataset_version(tmp_path)
    (tmp_path / "datasets/business/schema.md").write_text("Documentation\n")
    assert dataset_version(tmp_path) == version
    item = load_bank(ROOT)[0]
    assert exercise_version(item) == exercise_version(replace(item, solutions=dict(reversed(list(item.solutions.items())))))
    assert exercise_version(item) != exercise_version(replace(item, prompt="Different"))


@pytest.mark.integration
def test_compatible_legacy_session_uses_original_sandbox(tmp_path):
    import shutil

    from sql_practice.database import SQLiteBackend
    from sql_practice.datasets import dataset_version, load_dataset
    from sql_practice.practice import PracticeService

    shutil.copytree(ROOT / "datasets/business", tmp_path / "datasets/business")
    store = SessionStore(tmp_path)
    question = load_bank(ROOT)[0]
    session = store.create([question], "sqlite", "legacy-version", 1)
    answer = Path(store.paths(session)[question.id]) / "answer.sql"
    answer.write_text(question.sql("sqlite"))
    store.save_sandbox_version("sqlite", "legacy-version")
    backend = SQLiteBackend(store.directory)
    legacy_data = load_dataset(tmp_path)
    legacy_data.identity = ""
    with backend.sandbox(legacy_data):
        pass
    facade = PracticeService(
        [question], "legacy-version", store, lambda _engine: backend,
        lambda fixture, *, name: load_dataset(tmp_path, fixture, name=name),
        dataset_versions=lambda name: dataset_version(tmp_path, name),
    )
    assert facade.run().rows[0] == (1, 11000)
    assert facade.check()["passed"]
    assert list(store.directory.glob("sandbox*.sqlite")) == [store.directory / "sandbox.sqlite"]
    facade.version = "changed-bank"
    with pytest.raises(ValueError, match="changed"):
        facade.run()
    assert answer.read_text() == question.sql("sqlite")


@pytest.mark.integration
def test_seen_exercises_include_unchecked_sessions_and_legacy_checks_without_writes(tmp_path):
    store = SessionStore(tmp_path)
    assert store.seen_exercises() == set()
    questions = load_bank(ROOT)[:2]
    store.create(questions, "sqlite", "v1", 1)
    store.record({"exercise": "legacy-question"})
    snapshot = {
        file_path: file_path.read_bytes()
        for file_path in store.directory.rglob("*")
        if file_path.is_file()
    }
    assert store.seen_exercises() == {questions[0].id, questions[1].id, "legacy-question"}
    assert snapshot == {
        file_path: file_path.read_bytes()
        for file_path in store.directory.rglob("*")
        if file_path.is_file()
    }


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
    shutil.copytree(ROOT / "datasets", tmp_path / "datasets")
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
