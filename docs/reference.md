# Technical Reference

See the [README](../README.md) for a quick introduction, prerequisites, and usage.

A local SQL workbench for analytics, data engineering, and interview practice.
Edit answers in VS Code, grade in the terminal, or ask Copilot to administer exercises.
Includes **26 original exercises: 15 intermediate and 11 advanced**, on PostgreSQL,
MySQL, and SQLite. Terminal practice needs no web server or external AI API.
An optional local Streamlit dashboard visualizes saved statistics.

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.10+
(uv can supply Python), and Docker Desktop/Compose v2 for PostgreSQL and MySQL.
Run from this repository:

```sh
uv sync --locked
uv run sql-practice doctor
uv run sql-practice start
```

The default is PostgreSQL. `start` launches this project's selected Docker service if
needed and prints paths to `prompt.md` and `answer.sql`. Read the prompt and
[schema guide](schema.md), edit the answer file, then:

```sh
uv run sql-practice run
uv run sql-practice check
uv run sql-practice hint       # only when you want a hint
uv run sql-practice solution   # only when you want the answer
uv run sql-practice progress
```

Both `start` and `resume` print a `files` section with explicit `prompt.md` and
`answer.sql` paths for each exercise. They also open both files in the current
VS Code window using `code --reuse-window`. Write your SQL in the answer file.
Use `--no-open` for terminal-only use or scripts; `--open` explicitly enables opening.
If the `code` command is unavailable or fails, the session still succeeds with a
warning and printed paths. Install it through VS Code's Command Palette command
**Shell Command: Install 'code' command in PATH** if needed.
The `paths` section lists the containing folders;
it is not a list of individual files. Use `resume` to redisplay paths without creating
a new session or overwriting answers.

Generated prompts identify the dataset and fixed as-of date, and link its schema
guide using a relative path usable from VS Code or Markdown preview. Existing
exercises default to `business`; six revenue exercises use the independent
[revenue schema](../datasets/revenue/schema.md).

For a no-Docker start:

```sh
uv run sql-practice start --engine sqlite
```

The repository skill is `.github/skills/sql-practice/SKILL.md`. In Copilot Chat invoke
`/sql-practice`, or ask "give me an advanced window-functions exercise in MySQL".
If a new skill does not appear immediately, reload the VS Code window. The skill
uses the same CLI and avoids reading solutions until asked. Plain terminal use
does not require Copilot or any editor extension.

## Selection and Sessions

```sh
uv run sql-practice list
uv run sql-practice start --topic windows --difficulty advanced --engine mysql
uv run sql-practice start --difficulty intermediate --count 3 --seed 42
uv run sql-practice start --exercise latest-order --engine postgres
uv run sql-practice resume
uv run sql-practice check --session SESSION_ID --question EXERCISE_ID
```

Tags include `joins`, `aggregation`, `anti-joins`, `ctes`, `windows`, `ranking`,
`deduplication`, `dates`, `retention`, `gaps-islands`, `data-quality`, `subqueries`,
`statistics`, `relational-division`, `date-arithmetic`, `time-series`,
`conditional-logic`, and `interviews`. Filters are exact and never
silently broadened. Explicit IDs cannot be combined with topic/difficulty/category/count.

Without filters, selection is random across intermediate/advanced exercises and
excludes exercises already passed independently whenever unsolved matches remain.
Within the matching unsolved pool, unseen questions come first, followed by seen
questions with failed checks or assisted-only passes. Each tier is shuffled using
the seed; batches fill from unseen questions before using seen unsolved questions.
Seen means assigned in any saved session, even without a check, or present in saved
grading history. This applies across engines and uses existing manifests/history
without migration. Explicit retries and custom injected selection strategies are
unchanged. Listing status remains based on checks, so an unchecked seen question
still displays as `NEW`.
If `--count` exceeds the remaining unsolved matches, lower it or ask Copilot to
generate new examples; solved exercises never silently fill the batch. When all
matching exercises are solved, repeats are allowed and `start` prints a reminder
to ask Copilot to generate new SQL practice exercises. This reminder respects the
current filters and does not automatically invoke AI or change the exercise bank.
An explicit `--exercise ID` always permits an intentional retry without a reminder.
New material must follow `docs/exercise-authoring.md` and be validated before use.
The stored seed reproduces selection for the same bank, solved history, and seen
history. Engine selection is not random.
`start` always creates new work; `resume` displays existing paths without overwriting
anything. Multi-question sessions require `--question` for each practice action.

Answers, sessions, local credentials, databases, and progress live under gitignored
`.practice/`. Hints and revealed solutions mark subsequent attempts in that session
as assisted. Topic counts are attempts and passes, not claims of mastery. Progress
is single-user/local; do not run concurrent writers against this directory.

Git excludes the entire `.practice/` directory, local `.env` files, private-key
files, and SQLite/database files. Keep those exclusions when sharing this project;
never force-add local credentials, learner sessions, answers, or progress.

`list` shows the best recorded status for each exercise across all engines:

- `NEW`: no graded attempts recorded.
- `ATTEMPTED`: checked, but no passing attempt yet.
- `ASSISTED`: passed after using hints or revealing the solution.
- `SOLVED`: passed all tests without assistance in that session.

Only `check` records attempts; `run` does not mark exercises solved. Later failed or
assisted retries do not erase an independent solved result. Status is also what
random selection uses to prefer exercises not yet solved independently. Listing is
read-only and works with topic/difficulty/category filters.

## Categories and Learning Progress

### Statistics Dashboard

```sh
uv run sql-practice dashboard
# If port 8501 is already occupied:
uv run sql-practice dashboard --port 8502
```

Open http://127.0.0.1:8501. The dashboard binds only to localhost and reads the
same progress report as the CLI: completion charts, first-check success, effort
medians with sample sizes, and historical review priorities. Filter by engine,
difficulty, category, or topic, and switch between category and topic breakdowns.
Refresh reloads saved checks; no practice database or Docker service is needed.
It does not grade answers, modify history, change sessions, or reveal solutions.
Stop the server with Ctrl+C. Streamlit usage telemetry is disabled by the launcher.
Category counts overlap; small samples and historical review are not mastery scores.

### Terminal Reports

```sh
uv run sql-practice progress
uv run sql-practice progress --by topic
uv run sql-practice progress --category windows --engine postgres --difficulty advanced
uv run sql-practice progress --topic ranking --json
uv run sql-practice list --category aggregation
uv run sql-practice start --category query-composition --topic subqueries
```

Category definitions live in [categories.yaml](../categories.yaml). Categories group
existing detailed tags; a question may belong to several categories. Add or regroup
categories by editing YAML, without changing Python or invalidating active sessions.
The initial categories are:

| ID | Skill Family |
| --- | --- |
| `fundamentals` | Filtering, NULLs, strings and expressions |
| `joins` | Joins, anti-joins and relational division |
| `aggregation` | Aggregates and statistics |
| `query-composition` | CTEs, subqueries, set operations and recursion |
| `windows` | Ranking, running calculations, gaps and islands |
| `dates` | Dates and time-series queries |
| `analytics` | Retention, cohorts, funnels and segmentation |
| `data-quality` | Deduplication, reconciliation and validation |

These are learning areas, not claims that the current bank covers every listed
technique. Categories with no matching exercises show **No exercises available**:
that is a content gap, not a weakness. `interviews` remains a context/topic tag,
not a technical skill. Unknown tags remain visible in topic reports and are flagged
as unmapped until added to the registry. Category/topic/difficulty filters intersect;
they never bypass the strict unsolved preference or silently broaden selection.

`progress` defaults to a table, with a compact layout in narrow terminals. Metrics
use distinct current-bank questions and the best saved result:

- **Solved:** independent passes / available questions; repeats do not inflate it.
- **Assisted:** assisted-only completions, with no independent pass yet.
- **Needs work:** checked, but never passed. **New:** no checks recorded.
- **First try:** independent first-check passes / distinct attempted questions.
  Saved chronological attempt order defines the first check; retries do not rewrite it.
- Overall coverage is independently solved / available; zero denominators show N/A.
  JSON also includes percentages, failed checks, assisted checks and assisted passes.

The four status counts partition available questions. Category totals overlap and
must not be summed; overall coverage deduplicates independently. Progress combines
engines by default; `--engine` filters history before computing status and first try.
An engine-specific report does not change global solved status or exercise selection.
Fewer than five distinct attempted questions is marked as limited evidence in JSON
and explained below the table. Coverage and first-try results are not mastery scores.

Up to three deterministic practice priorities favor attempted/assisted-only work,
then historical review signals on independently solved questions, then unattempted
questions. Within those priorities, larger question counts come first with category
ID as a stable tie breaker. Finished categories without review signals or content
gaps suggest new material; the CLI neither generates questions nor starts another
session automatically. Review suggestions list exercise IDs for intentional retries
with `start --exercise ID`; solved status and unsolved-only random selection do not change.

### Effort and Review Signals

The **Effort to First Independent Pass** section appears in category and topic views.
It uses saved checks, so existing history contributes immediately without migration:

| Metric | Meaning |
| --- | --- |
| Checks | Median number of checks up to and including the first independent pass |
| Failures | Median failed checks before that independent pass |
| Sessions | Median distinct checked sessions through that pass, not elapsed time |
| Help | Distinct questions with recorded assistance / distinct attempted questions |
| Review | Independently solved questions that previously had failed or assisted checks |

Each median displays its solved-question sample size `n`; JSON exposes
`solved_sample`, `sessions_sample`, `median_checks_to_solve`,
`median_failures_to_solve` and `median_sessions_to_solve`. Fewer than five solved
samples is limited evidence. Missing samples show N/A, never a zero-effort solve.
If any check through a question's first solve lacks a session ID, exclude that
question from the sessions median; checks/failures still contribute normally.
Repeated checks in one session count as one session. Session counts describe where
graded work occurred, not how many sittings, hours or preview runs were needed.

All effort calculations stop at the first independent pass. An assisted pass counts
as a check but not a failure or independent solve. Later rechecks, failures or help
do not inflate original solve effort. Help includes failed assisted checks and
assisted passes up to that cutoff, or all checks if not independently solved yet.
JSON includes `assistance_questions` and `assistance_percent`; neither is inflated
by checking the same question repeatedly. Only assistance recorded on checks is
observable: external help, or a revealed hint without a subsequent check, is not
inferred by these metrics.

Unsolved and assisted-only questions are excluded from solved-only medians, but
their checks are shown separately as **Ongoing checks** (`unsolved_checks`). Read
these alongside completion and assistance: a low median among solved questions
does not imply the remaining questions are easy. Archived questions stay excluded;
engine/category/difficulty/topic filters apply before computing effort.

`review_exercises` provides the IDs behind each historical review signal, and
`review_questions` is their distinct count. These signals do not expire or downgrade
solved status; they suggest optional review, not a diagnosis of present ability.
Compare similar difficulty/engine scopes and consider sample sizes rather than
using effort as a single skill score. No timing, editor activity monitoring, or
`run` preview logging is added, and frequent previews are not penalized.

Use `progress --json` for machine-readable output. Original `total_attempts` and
`topics` counters retain their meanings, including repeated checks and historical
tag snapshots; explicit filters scope those counters. New `overall`, `categories`,
`topic_progress`, `recommendations` and `scope` fields provide the learning report.
Coverage uses current exercise tags and category mappings, so regrouping changes
the dashboard retroactively without rewriting history. Checks for removed exercises
are excluded from coverage and reported as `archived_attempts` (within engine scope).
Actual exercise/bank changes still invalidate sessions as described below.

## Databases and Configuration

```sh
uv run sql-practice db up --engine postgres
uv run sql-practice db up --engine mysql
uv run sql-practice db status
uv run sql-practice db down --engine mysql
uv run sql-practice db reset --engine sqlite
```

PostgreSQL 17 and MySQL 8.4 run in project-scoped Compose containers with named
volumes. Ports bind only to `127.0.0.1`. SQLite is a local file with no daemon.
Stopping preserves data. Reset requires confirmation and deletes ONLY the selected
engine's project data, not answers/history or other projects. `--yes` is available
for explicitly authorized automation. Resetting a server engine removes its volume;
start again to recreate and reseed it.

| Environment Variable | Default | Purpose |
| --- | --- | --- |
| `SQL_PRACTICE_ENGINE` | `postgres` | Default engine for `start` |
| `SQL_PRACTICE_ROOT` | Discover from current directory | Locate repository elsewhere |
| `SQL_PRACTICE_PG_PORT` | `55432` | PostgreSQL port on first configuration |
| `SQL_PRACTICE_MYSQL_PORT` | `53306` | MySQL port on first configuration |
| `SQL_PRACTICE_TEST_SERVERS` | unset | `1` enables live server tests |

Ports and random local credentials are initialized once in `.practice/local.json`,
with owner-only permissions; `.practice/db.env` is generated for Compose. Do not
publish either file. To change ports after setup, stop both services, edit the local
JSON port values, and start again. Do not change credentials on initialized volumes:
database passwords persist in the volume. There are no production connection options.

## Grading and Dialects

`run` queries the persistent base sandbox and prints a readable terminal table with
column headers and a row count. NULL values display as `NULL`; empty results retain
their headers. It displays at most 30 rows, explicitly notes preview truncation, and
rejects results over 10,000 rows. Use `uv run sql-practice run --json` for the original
machine-readable output (`columns`, `rows`, and total `row_count`).
`check` creates isolated fixtures and does not change the
exploratory sandbox. Every check uses base, edge, empty, and no-sales datasets.
It prints one line per test with a green `PASS` or red `FAIL`, its name, and feedback,
followed by an overall passed-test count. Assisted attempts are labeled in the summary.
Status labels remain readable when terminal colors are unavailable. Use
`uv run sql-practice check --json` for the original machine-readable result.
Exit status is zero for a passing check and one for a failed check in either format.
Checks enforce column aliases/order and compare either row sequences or duplicate-
preserving multisets. Monetary data uses integer cents; computed numbers compare
exactly after driver normalization. There is no implicit float tolerance.

Fixtures cover missing relationships, duplicate attempts, tied rankings, same-day
orders, NULL regions/end dates, leap dates, and zero/absent revenue. Date questions
use fixed dates, not the current clock. References have explicit dialect variants
where necessary. Same data does not mean every SQL expression is portable.
New session manifests bind each question to its own semantic exercise fingerprint
and dataset fingerprint. Adding or changing an unrelated exercise/dataset does not
invalidate that question. Editing the selected exercise or its dataset reports a
targeted stale-session error; old files remain for manual migration to a new session.
Mixed-dataset batches route each question to the right base sandbox and fixtures.

Persistent sandboxes are keyed by dataset ID and dataset content fingerprint,
separately per engine. Exercises with the same dataset/version share a sandbox;
new dataset versions create separate sandboxes without a volume reset. Reference
or prompt edits never require reseeding a sandbox. Schema documentation changes
do not change dataset fingerprints; fixture data changes do. Old versions may
accumulate until an explicitly approved engine reset; automatic cleanup is not added.

Legacy manifests without per-question bindings remain readable and retain their
original bank-wide compatibility checks. They are not silently migrated or
declared compatible after bank changes. Legacy answers/history and databases are
preserved; newly started sessions do not depend on the legacy sandbox marker.

Each query is one statement, with read-only roles/SQLite authorization, a 3-second
query deadline, and a 10,000-row cap. PostgreSQL uses statement timeout; SQLite uses
a progress handler; MySQL uses MAX_EXECUTION_TIME, a 5-second transport timeout,
and rejection of late/interrupted results. MySQL's server timeout does not cover
every possible blocking operation. These controls are defense in depth for trusted
personal practice, **not hardened hosting for hostile SQL**. Do not expose the
databases publicly or run untrusted files. Solutions are inspectable in the repo;
the tutor's reveal rules are not an anti-cheating boundary. DML/DDL exercises are
intentionally out of scope.

## Architecture and Extension

Uses SQLAlchemy Core, Typer, PyYAML, and small explicit contracts:

- **Adapter:** `DatabaseBackend` isolates SQLite/PostgreSQL/MySQL fixture and sandbox behavior.
- **Strategy:** interchangeable seeded/explicit selection and ordered/multiset comparison.
- **Facade:** `PracticeService` coordinates sessions, checks, assistance, and progress.
- **Composition:** the CLI constructs dependencies; no singleton state or plugin framework.

`Exercise.dataset` selects a safe repository-owned dataset ID, defaulting to
`business`. `load_dataset` validates that dataset's schema and fixtures; the
backend uses its identity to choose the persistent file/database. `validate-bank`
groups references by dataset and fixture, compares each engine to the corresponding
SQLite baseline, and retains independently reasoned anchors in tests.

Add an engine by implementing the backend contract, registering its constructor and
engine name, extending local setup, and testing dialect references. Add a comparison
strategy through the comparator's strategy interface. Ordinary exercises are data,
not subclasses. Prefer composition over inheritance and reuse SQLAlchemy's dialect
support. See [exercise authoring](exercise-authoring.md) for seed formats,
contracts, and extension tests.

## Tests and CI

```sh
uv run pytest -m 'not integration' -q
uv run pytest -q
uv run sql-practice validate-bank --engine sqlite

# Full local gate (project containers must be running):
uv run sql-practice db up --engine postgres
uv run sql-practice db up --engine mysql
SQL_PRACTICE_TEST_SERVERS=1 uv run pytest --cov=sql_practice --cov-fail-under=80
uv run sql-practice validate-bank --all-engines
uv run ruff check .
```

Pure unit tests use injected fakes. Integration tests use temporary directories,
in-memory SQLite, or the explicitly enabled local containers. Without the server
flag, live server tests skip. CI runs coverage, all engines, and the complete bank.
It also checks an 80% floor for each production module. Development follows
failing-first tests; the bank includes independent anchors and intentionally wrong
queries, not just self-comparison of reference SQL.

## Troubleshooting

- **Docker daemon stopped:** open Docker Desktop, wait until ready, then run `doctor`.
- **Port occupied:** choose unused ports before the first server setup; use `db status`
  to inspect owned containers. Do not stop or delete unrelated containers.
- **No current session:** run `start`; use `resume --session ID` for old sessions.
- **No matching exercise:** run `list` and use exact tags/difficulty; nothing is auto-relaxed.
- **Changed sandbox/bank:** confirm `db reset --engine ENGINE`, then create a new session.
- **Query error:** check aliases and your engine's date functions. Failed checks exit 1.
- **Editor import warnings:** select this repository's `.venv` Python interpreter.

## Release Notes

0.1.0: three-engine local setup, portable business seeds, 20 curated exercises,
isolated multi-fixture grading, resumable answers, assistance-aware progress,
Copilot practice skill, and VS Code terminal tasks.