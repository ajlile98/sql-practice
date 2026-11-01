---
name: sql-practice
description: 'Set up and administer local SQL practice exercises. Use when the user asks to practice SQL, start a SQL test, work on joins, window functions, analytics or interview SQL, check an answer, resume practice, get a hint, or review SQL practice progress, skill categories, strengths or improvement areas. Supports PostgreSQL, MySQL and SQLite through the repository CLI.'
argument-hint: '[topic] [intermediate|advanced] [postgres|mysql|sqlite] [count]'
---

# SQL Practice

## Boundaries

Use the repository CLI as the source of truth for selection, grading, and history.
Run commands from the repository root, or set `SQL_PRACTICE_ROOT` to it.
Never connect to production or accept arbitrary external database URLs.
Do not install this skill outside the repository unless explicitly requested.

Do not read `exercises/bank.yaml` during routine tutoring: it contains all reference solutions and hints.
Do not read the grader's private fixture files during routine tutoring.
Do not write or replace the learner's answer unless explicitly asked for a worked solution.
Hints and solutions require an explicit learner request. A failed check is not permission
to reveal a hint or inspect a reference. Skill instructions are not a security barrier:
this is an open, personal practice repository.

## Start a New Exercise

1. Run `uv run sql-practice doctor` if setup is uncertain. If `uv` is missing,
   explain the README prerequisites rather than claiming setup succeeded.
2. Run `uv run sql-practice list` to see current exercise IDs, status, tags and categories.
   Read `categories.yaml` for category IDs and definitions; it contains no solutions.
3. Translate requested categories, topics, difficulty, engine, and count into CLI filters.
   Examples:
   - No request: `uv run sql-practice start`
   - Advanced windows in MySQL: `uv run sql-practice start --engine mysql --difficulty advanced --topic windows`
   - Three intermediate questions: `uv run sql-practice start --difficulty intermediate --count 3`
   - Specific exercise: `uv run sql-practice start --exercise latest-order`
   - Query composition: `uv run sql-practice start --category query-composition`
4. With no arguments, use PostgreSQL and random unsolved-first intermediate/advanced
   selection. Do not randomize the engine. An explicit `SQL_PRACTICE_ENGINE` environment
   default takes precedence over PostgreSQL. `--seed` permits reproducible selection.
5. If a request cannot be mapped confidently to tags, ask one focused question.
   Never silently relax category, topic, difficulty, or engine filters. `--exercise`
   cannot be combined with category, topic, difficulty, or count filters.
   Solved questions are excluded while unsolved matches remain. If a requested batch
   is too large, offer a smaller count or ask whether to generate new material. When
   all matches are solved, surface the CLI reminder and ask before authoring anything.
6. `start` provisions only the selected local service and creates a session. Explain
   the local action before executing. If Docker is stopped, ask the learner to start
   Docker Desktop or explicitly select SQLite; do not silently switch engines.
7. Read ONLY the generated `prompt.md` and the schema guide it links. `business`
   uses `docs/schema.md`; other datasets use `datasets/<dataset-id>/schema.md`.
   Surface the prompt, engine, dataset/as-of, required columns/order, and generated
   `answer.sql` path. Then wait for work.

## Resume and Administer

- `uv run sql-practice resume` shows the current session without changing answers.
  `--session SESSION_ID` selects another existing session for every practice command.
  Starting again creates a NEW session, so use `resume` when continuing.
- For multi-question sessions, specify `--question EXERCISE_ID` on run/check/hint/solution.
   Questions may use different datasets; the CLI routes each question to its own data.
- Preview: `uv run sql-practice run`; results use the stable exploratory sandbox.
- Grade on request: `uv run sql-practice check`. Exit 1 means incorrect or failed SQL;
  summarize actual fixture feedback, not a guessed assessment. Do not edit the answer.
- Hint on request: `uv run sql-practice hint` reveals exactly the next hint.
- Solution on request: `uv run sql-practice solution`; discuss the returned SQL,
  dialect choices, edge cases, and alternative approaches. This marks assistance.
- Progress: `uv run sql-practice progress --json` provides category and topic statistics.

## Learning Progress

Use the CLI report, not an independently calculated score. `categories` and
`topic_progress` count distinct questions; `topics` contains legacy attempt counters
and must not be presented as unique completions. `--by topic` offers a readable
detailed view; `--engine`, `--difficulty`, `--category` and `--topic` scope the report.
Report independently solved/available, assisted-only, needs-work and first-try
passes/attempted with sample sizes. Categories overlap; use `overall` for totals.
Below five distinct attempted questions, explicitly note limited evidence. Never
equate coverage or first-try success with mastery or diagnose weakness from no data.
Use the effort metrics for grounded review suggestions: median checks/failures to
first independent pass with `solved_sample`, checked-session median with its own
`sessions_sample`, and `assistance_questions` / `attempted`. Note limited evidence
below five solved samples, even if attempted-question count is larger. Solved-only
medians exclude ongoing questions; include `unsolved_checks` and assisted-only work
when discussing difficulty. Sessions are checked session IDs, not time or sittings.
Do not infer unrecorded/external assistance or penalize `run` previews. Metrics stop
at first independent success; later checks do not change initial solve effort.
`review_exercises` are historical retry/help signals, not proof of current weakness.
Prioritize unfinished/assisted-only work before optional review, then new coverage.
An intentional solved retry uses `start --exercise ID`; never bypass selection rules
or change solved status to force a review question into random practice.
Explain no-exercise categories as content gaps. Present the report's practice
priorities, and ask before starting a session or generating new material. Reporting
must not grade the current answer or reveal hints/solutions. Taxonomy-only edits
preserve active sessions; actual exercise changes follow the authoring workflow.

After failures, explain the observed mismatch and ask the learner to revise. Do not
fabricate CLI results or report a pass when a check was not run. If data/bank changes
make a session stale, preserve its files and explain the error. New sessions check
only the selected question's exercise/dataset versions. Unrelated additions do not
invalidate it. Start a new session for changed content; dataset versions have separate
sandboxes and do not require volume resets. Legacy manifests retain conservative
bank-wide checks; do not silently migrate or promise compatibility for them. A destructive
`db reset --engine ENGINE` requires explicit approval; do not bypass confirmation
with `--yes` on the learner's behalf. Reset preserves answers/history but deletes
the selected project's database volume. `db down --engine ENGINE` stops without deleting.

## Creating New Material

Normal requests select from the reviewed bank; do not improvise unvalidated exercises.
If the learner explicitly asks to add new exercises, follow `docs/exercise-authoring.md`,
author original questions, add independently checked anchors and known-wrong queries,
and run `uv run sql-practice validate-bank --all-engines`. Report untested engines.
Declare each exercise's dataset, defaulting to `business` only when its data fits.
Create a new independent dataset when different data is needed; do not extend another
exercise set's shared fixtures to fit it. With explicit authoring permission, inspect
only the bank format and fixtures needed for authoring/validation, never to reveal
unrequested solutions. Define date intervals precisely; completed-day windows
exclude the fixed as-of day. Do not rewrite existing session files or learner answers.
Do not require an external model API or credentials for ordinary practice.