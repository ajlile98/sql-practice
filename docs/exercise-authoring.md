# Authoring and Extension Contracts

## Portable Data

`datasets/business/schema.yaml` declares ordered tables/columns, version, and fixed
as-of date. A column has `type` (`integer`, `text`, `date`, `timestamp`, `decimal`),
optional `primary_key`, `nullable` (default false), and `references: table.column`.
Decimal columns can specify `precision` and `scale`; use exact finite values, not
binary floats. Text storage is limited to 255 characters on server engines.

Each base table is a UTF-8 CSV with a header exactly matching schema column order.
Use ISO `YYYY-MM-DD` dates. `\N` is NULL; an empty field is an empty string.
For literal backslashes in text, double them (`\\N` represents literal `\N`).
The loader uses safe YAML parsing and bound inserts, validates identifiers, header
shape, types, non-null constraints, duplicate primary keys, and foreign keys before
creating tables. Keep logical schema types within every supported engine's limits.
Do not import sensitive data into reviewed fixture files.

Every exercise is checked against the shared `FIXTURES` policy:

- `base`: stable exploratory data in `tables/`.
- `edge`: files in `fixtures/edge/` **replace whole tables**, not append rows. Other
  tables inherit base data. The effective dataset must satisfy all foreign keys.
- `empty`: all tables retain their schema/header but have no records.
- `no-sales`: customers/products/subscriptions remain; orders/items/payments are empty.

Add a fixture policy only with loader/contract tests and independently reasoned
expected results. Fixtures are deterministic; use fixed dates. Keep bank changes
versioned in Git and never mutate a learner's existing session to hide incompatibility.

## Exercise Records

Add an original record to `exercises/bank.yaml`:

```yaml
- id: unique-kebab-id
  title: A concise title
  difficulty: advanced  # or intermediate
  tags: [windows, dates]
  prompt: State business rules, aliases, edge cases, fixed dates and ordering.
  columns: [customer_id, metric]
  ordered: false
  hints:
    - First conceptual hint.
    - A more concrete hint without the full answer.
  solutions:
    shared: SELECT ...
    # Or provide sqlite, postgres and mysql SQL strings instead.
```

All three engines must have a reference, either shared or explicitly mapped; a
specific engine mapping overrides `shared`. Do not assume date syntax, integer
division, rounding, implicit casts, NULL sort order, or collations are interchangeable.
List all required output aliases in exact order. Unordered comparison preserves
duplicates. Ordered questions must require deterministic tie breakers and state
NULL placement explicitly if relevant. Computed decimals compare exactly after
normalization; make requested rounding explicit. Do not use approximate statistics
without an explicit comparison-policy extension and tests.

Prefer SQL block scalars (`|`) for longer new references. No reference SQL or hints
are copied into learner session files until explicitly requested through the CLI.
The bank is open to inspection, not secured against the learner.

## Validation Checklist

### Category Registry

The root `categories.yaml` groups exercise tags into learning categories:

```yaml
version: 1
context_tags: [interviews]
categories:
  - id: windows
    label: Windows and Sequences
    description: Ranking and calculations over ordered rows.
    tags: [windows, ranking, gaps-islands]
```

IDs and tags are lowercase kebab-case strings. Each category needs a unique ID,
nonempty label/description, and a nonempty list of unique tags. Tags may belong to
multiple categories. Category membership is any matching tag; aggregation counts
each question once per category even when several tags match. `context_tags` declares
non-skill tags such as `interviews`. New tags are permitted without Python changes;
unmapped skill tags produce a warning in progress reports, not a load failure.

Tag the intended learning objective, not every SQL keyword a solution happens to
contain. Do not tag all questions as fundamentals just because they use SELECT.
Use `progress --by topic` to inspect detailed coverage. Empty configured categories
represent bank gaps and remain visible. To add a category, add a YAML record and
map existing tags; adding new exercises is a separate, validated authoring step.

Registry-only edits do not affect the session content hash. Keep this file outside
`exercises/` and `datasets/`; do not weaken content checks to support regrouping.
Reports use current mappings without migrating history, while legacy JSON topic
counters retain their recorded tag snapshots. Missing/invalid registry files fail
with a configuration error rather than silently dropping categories.

### Exercise Checks

1. Add a failing test or independent expected anchor for the business rule first.
2. Add positive and negative fixture cases, including empty inputs, NULLs, duplicates,
   ties, relevant date boundaries, and missing related rows.
3. Add a plausible incorrect query that fails: e.g. wrong join filter, MAX(id) instead
   of latest date, ROW_NUMBER instead of DENSE_RANK, or lost duplicate counts.
4. Run `uv run pytest` and `uv run sql-practice validate-bank --all-engines` with both
   server containers ready. Do not call an unexecuted dialect verified.
5. Update README exercise counts/topics and the bank count assertions when expanding
   beyond the initial 20. Update schema docs when adding/changing tables.

The CLI validates every reference against all fixtures and compares each dialect to
SQLite results. This checks dialect agreement but does not independently prove a
business rule: human-reasoned anchors in tests remain essential.

## Gang of Four Extension Points

**Adapter:** implement `DatabaseBackend.fixture(dataset)` and `sandbox(dataset)` as
context managers yielding the bounded query interface. Fixture resources must be
isolated and cleaned on errors. Sandbox data persists. Add the engine name,
constructor registration, local lifecycle support, and needed SQL variants. Reuse
SQLAlchemy DDL/dialects. Test writes rejected, timeout/cancellation, row limits,
connection closure, cleanup on exceptions, and repeated sandbox access. Do not add
driver conditions to `PracticeService`.

**Strategy:** selection implements `choose(bank, count)` over already-filtered
candidates. Comparison implements `compare(expected_rows, actual_rows)` over
normalized rows. Inject new policies; share normalization and column checks. Test
substitution with a fake and do not duplicate orchestration in the CLI or skill.

**Facade:** `PracticeService` accepts the bank, content version, session store,
backend factory, and dataset loader. Keep selection, query execution, and persistence
behind their owning contracts; thin CLI handlers only translate input/output.

Prefer explicit composition and small structural interfaces to deep inheritance.
Do not introduce Singletons, dynamic plugin discovery, or Command/Observer class
families until an actual requirement justifies them.