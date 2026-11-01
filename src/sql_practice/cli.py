"""Thin terminal interface and explicit dependency composition root."""

import json
import os
import secrets
import shutil
import subprocess
import sys
from functools import wraps
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy.exc import SQLAlchemyError

from sql_practice.datasets import FIXTURES, dataset_version, load_dataset
from sql_practice.environment import LocalEnvironment, project_root
from sql_practice.exercises import (
    ENGINES,
    content_version,
    exercise_statuses,
    load_bank,
    load_categories,
    matching_exercises,
)
from sql_practice.grading import QueryResult, compare_results
from sql_practice.practice import PracticeService
from sql_practice.sessions import SessionStore

app = typer.Typer(
    no_args_is_help=True, help="Local SQL practice. Edit SQL in VS Code; grade in the terminal."
)
db = typer.Typer(no_args_is_help=True)
app.add_typer(db, name="db")


def handled(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from None
        except SQLAlchemyError:
            typer.echo(
                "Database connection/setup failed. Run doctor and db up; check local credentials and ports.",
                err=True,
            )
            raise typer.Exit(1) from None

    return wrapper


def emit(value):
    typer.echo(json.dumps(value, indent=2, default=str))


def verdict_line(passed, detail):
    typer.secho(
        "PASS" if passed else "FAIL",
        fg=typer.colors.GREEN if passed else typer.colors.RED,
        bold=True,
        nl=False,
    )
    typer.echo(f" {detail}")


def show_session(store, session, open_prompt):
    files = store.files(session)
    emit({"session": session, "paths": store.paths(session), "files": files})
    if not open_prompt:
        return
    executable = shutil.which("code")
    if not executable:
        typer.echo(
            "Warning: VS Code 'code' command not found. Open the printed file paths manually "
            "or install 'code' in PATH from the VS Code Command Palette. Use --no-open to skip opening.",
            err=True,
        )
        return
    editor_files = [
        file_paths[filename]
        for file_paths in files.values()
        for filename in ("prompt.md", "answer.sql")
    ]
    try:
        result = subprocess.run(
            [executable, "--reuse-window", *editor_files],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    typer.echo("Warning: Could not open files in VS Code. Use the printed file paths.", err=True)


def environment():
    return LocalEnvironment(project_root())


def service():
    root = project_root()
    local = LocalEnvironment(root)
    return PracticeService(
        load_bank(root),
        content_version(root),
        SessionStore(root),
        local.backend,
        lambda fixture, *, name="business": load_dataset(root, fixture, name=name),
        categories=load_categories(root),
        dataset_versions=lambda name: dataset_version(root, name),
    )


@app.command()
@handled
def dashboard(port: int = typer.Option(8501, min=1, max=65535)):
    """Open a read-only local statistics dashboard. Stop with Ctrl+C."""
    typer.echo(f"SQL Practice dashboard: http://127.0.0.1:{port}")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).with_name("dashboard.py")),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ],
        env={**os.environ, "SQL_PRACTICE_ROOT": str(project_root())},
        check=False,
    )
    raise typer.Exit(result.returncode)


@app.command()
@handled
def doctor():
    """Inspect local prerequisites without starting services."""
    emit(environment().doctor())


@db.command()
@handled
def up(engine: str = "postgres"):
    """Start only the selected project-owned local service."""
    typer.echo(environment().up(engine))


@db.command()
@handled
def status():
    """Show this project's container status."""
    local = environment()
    typer.echo(
        local.compose("ps", "--all")
        if (local.directory / "local.json").exists()
        else "No local containers configured"
    )


@db.command()
@handled
def down(engine: str = "postgres"):
    """Stop a service, preserving its data."""
    typer.echo(environment().down(engine))


@db.command()
@handled
def reset(engine: str = "postgres", yes: bool = False):
    """Delete ONLY the selected engine's project data, preserving answers/history."""
    if not yes:
        typer.confirm(
            f"Delete this project's {engine} practice database? Answers and history remain.",
            abort=True,
        )
    environment().reset(engine)
    typer.echo("Practice database reset. Start a new session to reseed.")


@app.command(name="list")
@handled
def list_exercises(
    topic: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
):
    """List curated exercises with their best recorded practice status."""
    root = project_root()
    bank = load_bank(root)
    categories = load_categories(root)
    matches = matching_exercises(
        bank, topic=topic, difficulty=difficulty, category=category, categories=categories
    )
    if not matches:
        raise ValueError("No exercises match these filters")
    statuses = exercise_statuses(SessionStore(root).attempts())
    typer.echo(f"{'Status':10} {'Exercise':28} {'Difficulty':12} Topics | Categories")
    for item in matches:
        state = statuses.get(item.id, "NEW")
        labels = ", ".join(categories.labels_for(item)) or "Uncategorized"
        typer.echo(
            f"{state:10} {item.id:28} {item.difficulty:12} {', '.join(item.tags)} | {labels}"
        )


@app.command()
@handled
def start(
    engine: str = typer.Option(os.environ.get("SQL_PRACTICE_ENGINE", "postgres")),
    topic: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    count: int = 1,
    exercise: str | None = None,
    seed: int | None = None,
    open_prompt: bool = typer.Option(True, "--open/--no-open", help="Open prompts and answers in VS Code."),
):
    """Create a new session; no filters means random unsolved-first practice."""
    practice = service()
    from sql_practice.exercises import select_exercises, solved_exercises

    solved = solved_exercises(practice.store.attempts())
    selected = select_exercises(
        practice.bank,
        engine=engine,
        topic=topic,
        difficulty=difficulty,
        count=count,
        identifier=exercise,
        solved=solved,
        category=category,
        categories=practice.categories,
    )
    if not exercise and all(item.id in solved for item in selected):
        typer.echo(
            "All matching exercises are solved. Repeating solved exercises.\n"
            "Want fresh material? Ask Copilot to generate new SQL practice exercises "
            "matching these filters, then validate them before use.",
            err=True,
        )
    environment().up(engine)
    session = practice.start(
        engine=engine,
        topic=topic,
        difficulty=difficulty,
        count=count,
        identifier=exercise,
        category=category,
        seed=seed if seed is not None else secrets.randbits(32),
    )
    show_session(practice.store, session, open_prompt)


@app.command()
@handled
def resume(
    session: str | None = None,
    open_prompt: bool = typer.Option(True, "--open/--no-open", help="Open prompts and answers in VS Code."),
):
    """Display an existing session without changing its answer files."""
    store = SessionStore(project_root())
    saved = store.get(session)
    show_session(store, saved, open_prompt)


@app.command()
@handled
def run(
    session: str | None = None,
    question: str | None = None,
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
):
    """Preview the answer's results on the reusable sandbox (first 30 rows shown)."""
    result = service().run(session, question)
    preview = result.rows[:30]
    total = len(result.rows)
    if json_output:
        emit({"columns": result.columns, "rows": preview, "row_count": total})
        return
    table = Table(box=box.ASCII, header_style="bold")
    for column in result.columns:
        table.add_column(Text(column))
    for row in preview:
        table.add_row(*(Text("NULL" if value is None else str(value)) for value in row))
    Console(highlight=False, markup=False).print(table)
    summary = f"{total} {'row' if total == 1 else 'rows'}"
    if total > len(preview):
        summary += f" (showing first {len(preview)})"
    typer.echo(summary)


@app.command()
@handled
def check(
    session: str | None = None,
    question: str | None = None,
    json_output: bool = typer.Option(
        False, "--json", help="Output JSON instead of colored verdicts."
    ),
):
    """Grade against all isolated fixtures; record the attempt."""
    result = service().check(session, question)
    if json_output:
        emit(result)
    else:
        for case in result["fixtures"]:
            message = " ".join(case["message"].splitlines())
            verdict_line(case["passed"], f"{case['fixture']}: {message}")
        passed_count = sum(case["passed"] for case in result["fixtures"])
        summary = f"{passed_count}/{len(result['fixtures'])} tests passed"
        if result["assisted"]:
            summary += " (assisted)"
        typer.echo()
        verdict_line(result["passed"], summary)
    if not result["passed"]:
        raise typer.Exit(1)


@app.command()
@handled
def hint(session: str | None = None, question: str | None = None):
    """Reveal only the next hint and mark this exercise as assisted."""
    typer.echo(service().hint(session, question))


@app.command()
@handled
def solution(session: str | None = None, question: str | None = None):
    """Explicitly reveal a reference solution and mark the exercise as assisted."""
    typer.echo(service().solution(session, question))


def show_effort(console, groups, by):
    def median_cell(value, count):
        return f"{value:g} (n={count})" if value is not None else "N/A (n=0)"

    console.print(Text("Effort to First Independent Pass"))
    headers = [by.title(), "Checks", "Failures", "Sessions", "Help", "Review"]
    table = Table(box=box.ASCII, header_style="bold")
    for header in headers:
        table.add_column(header, overflow="fold")
    active = {identifier: group for identifier, group in groups.items() if group["attempted"]}
    if not active:
        console.print(Text("No checked questions in this scope; effort metrics are N/A."))
        return
    for identifier, group in active.items():
        values = [
            identifier,
            median_cell(group["median_checks_to_solve"], group["solved_sample"]),
            median_cell(group["median_failures_to_solve"], group["solved_sample"]),
            median_cell(group["median_sessions_to_solve"], group["sessions_sample"]),
            f"{group['assistance_questions']}/{group['attempted']}",
            str(group["review_questions"]),
        ]
        if console.width < 100:
            console.print(Text(identifier))
            console.print(
                Text(
                    "; ".join(
                        f"{header}: {value}" for header, value in zip(headers[1:], values[1:])
                    )
                )
            )
        else:
            table.add_row(*(Text(value) for value in values))
    if console.width >= 100:
        console.print(table)
    console.print(
        Text(
            "Checks, failures and sessions are medians to first independent pass; n = solved-question sample (limited evidence below 5)."
        )
    )
    console.print(
        Text(
            "Help = questions with recorded assistance before first independent pass / attempted. Review = solved after failures or help."
        )
    )
    console.print(
        Text(
            "Sessions count distinct checked session IDs, not time; incomplete session histories are excluded from that median."
        )
    )


def show_progress(result, by):
    console = Console(highlight=False, markup=False)
    scope = ", ".join(
        f"{key}={value}" for key, value in result["scope"].items() if value is not None
    )
    console.print(
        Text("Scope: " + (scope or "all engines, all difficulties, all categories and topics"))
    )
    groups = result["categories" if by == "category" else "topic_progress"]
    headers = [by.title(), "Solved", "Assisted", "Needs work", "New", "First try"]
    table = Table(box=box.ASCII, header_style="bold")
    for header in headers:
        table.add_column(header, overflow="fold")
    for identifier, group in groups.items():
        label = group["label"]
        if label != identifier:
            label = f"{label}\n({identifier})"
        first = f"{group['first_try_passes']}/{group['attempted']}" if group["attempted"] else "N/A"
        values = [
            label,
            f"{group['solved']}/{group['available']}",
            str(group["assisted_only"]),
            str(group["needs_work"]),
            str(group["unattempted"]),
            first,
        ]
        if not group["available"]:
            values[0] += "\nNo exercises available"
            values[1] = "N/A"
        if console.width < 72:
            console.print(Text(values[0]))
            console.print(
                Text(
                    "; ".join(
                        f"{header}: {value}" for header, value in zip(headers[1:], values[1:])
                    )
                )
            )
            console.print()
        else:
            table.add_row(*(Text(value) for value in values))
    if console.width >= 72:
        console.print(table)
    overall = result["overall"]
    percent = overall["coverage_percent"]
    coverage = f"{percent:.0f}%" if percent is not None else "N/A"
    console.print(
        Text(
            f"Overall: {overall['solved']}/{overall['available']} independently solved ({coverage})."
        )
    )
    console.print(
        Text(
            f"Checks: {overall['attempts']}; failed: {overall['failed_checks']}; assisted: {overall['assisted_checks']}."
        )
    )
    show_effort(console, groups, by)
    console.print(
        Text(
            f"Ongoing checks: {overall['unsolved_checks']} on questions not independently solved; excluded from solved-only medians."
        )
    )
    console.print(
        Text(
            "Assisted = assisted-only completions. First try = independent first-check passes / distinct attempted questions."
        )
    )
    console.print(
        Text(
            "Limited evidence below 5 distinct attempted questions per row; completion is not mastery."
        )
    )
    console.print(Text(result["basis"]))
    if result["archived_attempts"]:
        console.print(
            Text(f"Archived checks excluded from current coverage: {result['archived_attempts']}.")
        )
    if result["unmapped_tags"]:
        console.print(
            Text(
                "Unmapped tags (still included in topic progress): "
                + ", ".join(result["unmapped_tags"])
            )
        )
    for recommendation in result["recommendations"]:
        console.print(
            Text(
                f"{recommendation['action'].title()} {recommendation['category']}: {recommendation['reason']}."
            )
        )
        if recommendation["exercises"]:
            console.print(Text("Review exercises: " + ", ".join(recommendation["exercises"])))


@app.command()
@handled
def progress(
    by: str = "category",
    engine: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    topic: str | None = None,
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of a table."),
):
    """Show unique-question coverage and practice priorities by category or topic."""
    if by not in ("category", "topic"):
        raise ValueError("Unknown view; --by must be category or topic")
    result = service().progress(
        engine=engine, difficulty=difficulty, category=category, topic=topic
    )
    if json_output:
        emit(result)
    else:
        show_progress(result, by)


@app.command(name="validate-bank")
@handled
def validate_bank(engine: str = "sqlite", all_engines: bool = False):
    """Run every reference on every fixture; compare engines to SQLite."""
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine: {engine}")
    root = project_root()
    local = environment()
    bank = load_bank(root)
    selected = ENGINES if all_engines else (engine,)
    groups = {}
    for item in bank:
        groups.setdefault(item.dataset, []).append(item)
    baseline = {}
    for dataset_name, questions in groups.items():
        for fixture in FIXTURES:
            with local.backend("sqlite").fixture(
                load_dataset(root, fixture, name=dataset_name)
            ) as connection:
                for item in questions:
                    result = connection.query(item.sql("sqlite"))
                    if result.columns != item.columns:
                        raise ValueError(f"Reference column mismatch: {item.id}")
                    if fixture == "base" and not result.rows:
                        raise ValueError(f"Missing positive base case: {item.id}")
                    baseline[(fixture, item.id)] = result
    checked = 0
    for selected_engine in selected:
        for dataset_name, questions in groups.items():
            for fixture in FIXTURES:
                with local.backend(selected_engine).fixture(
                    load_dataset(root, fixture, name=dataset_name)
                ) as connection:
                    for item in questions:
                        result = connection.query(item.sql(selected_engine))
                        comparison = compare_results(
                            baseline[(fixture, item.id)], result, ordered=item.ordered
                        )
                        if not comparison.passed:
                            raise ValueError(
                                f"{selected_engine}/{fixture}/{item.id}: {comparison.message}"
                            )
                        if (
                            fixture == "base"
                            and compare_results(result, QueryResult(result.columns, ())).passed
                        ):
                            raise ValueError(f"Empty wrong answer passed: {item.id}")
                        checked += 1
        typer.echo(f"{selected_engine}: {len(bank)} exercises x {len(FIXTURES)} fixtures passed")
    typer.echo(f"Validated {checked} reference executions; empty wrong-answer checks passed.")
