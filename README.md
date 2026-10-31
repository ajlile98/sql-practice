# SQL Practice

Practice analytics and interview SQL locally with 20 intermediate and advanced
exercises for PostgreSQL, MySQL, and SQLite. Write SQL in VS Code, get automatic
feedback in the terminal, and track progress in a local Streamlit dashboard.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.10+
  (uv can install Python).
- Docker Desktop with Compose v2 for PostgreSQL or MySQL. SQLite needs no Docker.
- VS Code recommended; GitHub Copilot is optional.

## How to Use

Clone the repository and install dependencies:

```sh
git clone https://github.com/ajlile98/sql-practice.git
cd sql-practice
uv sync --locked
uv run sql-practice doctor
```

Start an exercise (PostgreSQL by default; have Docker Desktop running):

```sh
uv run sql-practice start
# Or practice without Docker:
uv run sql-practice start --engine sqlite
```

Read the generated prompt and [schema guide](docs/schema.md), then edit the
printed `answer.sql` file. The prompt opens in VS Code when `code` is available.

```sh
uv run sql-practice run        # Preview results
uv run sql-practice check      # Grade and save the attempt
uv run sql-practice hint       # Request a hint
uv run sql-practice solution   # Reveal the answer
uv run sql-practice progress   # View statistics
uv run sql-practice dashboard  # Open http://127.0.0.1:8501
```

Choose a topic or continue an existing session:

```sh
uv run sql-practice list
uv run sql-practice start --category windows --difficulty advanced
uv run sql-practice resume
uv run sql-practice run --session SESSION_ID
```

Random practice prefers unseen questions before seen-but-unsolved ones, including
assisted passes. Previously opened questions count as seen even without a check.

Commands use the most recently started session, not the file open in your editor.
Use `--session ID` for older sessions. Hints and solutions mark subsequent checks
in that session as assisted. Personal sessions and credentials stay local under
gitignored `.practice/`.

With Copilot, invoke `/sql-practice` or ask for an exercise in chat.

## More Details

- [Technical reference](docs/reference.md): session behavior, statistics,
  configuration, grading, architecture, tests, and troubleshooting.
- [Business schema](docs/schema.md)
- [Exercise authoring](docs/exercise-authoring.md)