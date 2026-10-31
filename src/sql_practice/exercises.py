"""Exercise contracts, validation, and selection strategies."""

import hashlib
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

ENGINES = ("sqlite", "postgres", "mysql")


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Categories:
    entries: tuple[Category, ...] = ()
    context_tags: tuple[str, ...] = ()

    def tags_for(self, identifier: str) -> tuple[str, ...]:
        for category in self.entries:
            if category.id == identifier:
                return category.tags
        raise ValueError(f"Unknown category: {identifier}")

    def labels_for(self, exercise: "Exercise") -> list[str]:
        return [item.label for item in self.entries if set(item.tags).intersection(exercise.tags)]


def parse_categories(document) -> Categories:
    def token(value):
        return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value)

    def tags(value):
        if not isinstance(value, list) or not all(token(item) for item in value):
            raise ValueError("Category tags must be lists of kebab-case strings")
        if len(set(value)) != len(value):
            raise ValueError("Category tags contain duplicates")
        return tuple(value)

    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Unsupported category registry version")
    records = document.get("categories")
    if not isinstance(records, list) or not records:
        raise ValueError("Category registry needs a nonempty categories list")
    entries = []
    identifiers = set()
    for record in records:
        if not isinstance(record, dict) or not token(record.get("id")):
            raise ValueError("Invalid category ID")
        identifier = record["id"]
        if identifier in identifiers:
            raise ValueError(f"Invalid duplicate category ID: {identifier}")
        identifiers.add(identifier)
        for field in ("label", "description"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Category {identifier} needs a {field}")
        category_tags = tags(record.get("tags"))
        if not category_tags:
            raise ValueError(f"Category {identifier} needs tags")
        entries.append(Category(identifier, record["label"], record["description"], category_tags))
    return Categories(tuple(entries), tags(document.get("context_tags", [])))


def load_categories(root: Path) -> Categories:
    try:
        document = yaml.safe_load((root / "categories.yaml").read_text())
    except yaml.YAMLError as error:
        raise ValueError("Invalid YAML in categories.yaml") from error
    return parse_categories(document)


def exercise_statuses(attempts: list[dict]) -> dict[str, str]:
    priorities = {"NEW": 0, "ATTEMPTED": 1, "ASSISTED": 2, "SOLVED": 3}
    statuses = {}
    for attempt in attempts:
        state = "ATTEMPTED"
        if attempt["passed"]:
            state = "ASSISTED" if attempt["assisted"] else "SOLVED"
        exercise_id = attempt["exercise"]
        if priorities[state] > priorities[statuses.get(exercise_id, "NEW")]:
            statuses[exercise_id] = state
    return statuses


def solved_exercises(attempts: list[dict]) -> set[str]:
    return {
        exercise_id
        for exercise_id, state in exercise_statuses(attempts).items()
        if state == "SOLVED"
    }


@dataclass(frozen=True)
class Exercise:
    id: str
    title: str
    difficulty: str
    tags: tuple[str, ...]
    prompt: str
    hints: tuple[str, ...]
    solutions: dict[str, str]
    columns: tuple[str, ...]
    ordered: bool

    def sql(self, engine: str) -> str:
        return self.solutions.get(engine, self.solutions.get("shared", ""))


class SelectionStrategy(Protocol):
    def choose(self, bank: list[Exercise], count: int) -> list[Exercise]: ...


@dataclass
class UnsolvedRandom:
    seed: int | None
    solved: set[str]
    seen: set[str] | None = None

    def choose(self, bank: list[Exercise], count: int) -> list[Exercise]:
        generator = random.Random(self.seed)
        fresh = [item for item in bank if item.id not in self.solved]
        unseen = [item for item in fresh if item.id not in (self.seen or set())]
        seen_unsolved = [item for item in fresh if item.id in (self.seen or set())]
        repeated = [item for item in bank if item.id in self.solved]
        generator.shuffle(unseen)
        generator.shuffle(seen_unsolved)
        generator.shuffle(repeated)
        return (unseen + seen_unsolved + repeated)[:count]


@dataclass
class ExplicitSelection:
    identifier: str

    def choose(self, bank: list[Exercise], count: int) -> list[Exercise]:
        return [item for item in bank if item.id == self.identifier][:count]


def matching_exercises(
    bank: list[Exercise],
    *,
    topic=None,
    difficulty=None,
    category=None,
    categories: Categories | None = None,
    engine=None,
) -> list[Exercise]:
    if engine is not None and engine not in ENGINES:
        raise ValueError(f"Unknown engine: {engine}")
    if difficulty is not None and difficulty not in ("intermediate", "advanced"):
        raise ValueError(f"Unknown difficulty: {difficulty}")
    category_tags = (
        (categories or Categories()).tags_for(category) if category is not None else None
    )
    return [
        item
        for item in bank
        if (not topic or topic in item.tags)
        and (not difficulty or item.difficulty == difficulty)
        and (category_tags is None or set(category_tags).intersection(item.tags))
        and (engine is None or item.sql(engine) or not item.solutions)
    ]


def select_exercises(
    bank: list[Exercise],
    *,
    topic: str | None = None,
    difficulty: str | None = None,
    identifier: str | None = None,
    engine: str = "postgres",
    count: int = 1,
    seed: int | None = None,
    solved: set[str] | None = None,
    seen: set[str] | None = None,
    strategy: SelectionStrategy | None = None,
    category: str | None = None,
    categories: Categories | None = None,
) -> list[Exercise]:
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine: {engine}")
    if identifier and (topic or difficulty or category or count != 1):
        raise ValueError(
            "An explicit exercise cannot be combined with topic, difficulty, category, or count"
        )
    candidates = [
        item
        for item in matching_exercises(
            bank,
            topic=topic,
            difficulty=difficulty,
            category=category,
            categories=categories,
            engine=engine,
        )
        if not identifier or identifier == item.id
    ]
    if not candidates:
        raise ValueError("No exercises match these filters")
    if count < 1 or count > len(candidates):
        raise ValueError(f"count must be between 1 and {len(candidates)}")
    if not identifier:
        unsolved = [item for item in candidates if item.id not in (solved or set())]
        if unsolved:
            if count > len(unsolved):
                raise ValueError(
                    f"Only {len(unsolved)} unsolved exercises match these filters; "
                    f"lower --count to {len(unsolved)} or ask Copilot to generate new examples"
                )
            candidates = unsolved
    policy = strategy or (
        ExplicitSelection(identifier) if identifier else UnsolvedRandom(seed, solved or set(), seen)
    )
    return policy.choose(candidates, count)


def load_bank(root: Path) -> list[Exercise]:
    document = yaml.safe_load((root / "exercises/bank.yaml").read_text())
    if document.get("version") != 1:
        raise ValueError("Unsupported exercise bank version")
    result = []
    identifiers = set()
    for record in document["exercises"]:
        item = Exercise(
            record["id"],
            record["title"],
            record["difficulty"],
            tuple(record["tags"]),
            record["prompt"],
            tuple(record["hints"]),
            record["solutions"],
            tuple(record["columns"]),
            record.get("ordered", False),
        )
        if item.id in identifiers or not item.id.replace("-", "").isalnum():
            raise ValueError(f"Invalid or duplicate exercise ID: {item.id}")
        if item.difficulty not in ("intermediate", "advanced") or not item.tags or not item.hints:
            raise ValueError(f"Invalid metadata: {item.id}")
        if not item.columns or len(set(item.columns)) != len(item.columns):
            raise ValueError(f"Invalid columns: {item.id}")
        if any(not item.sql(engine).strip() for engine in ENGINES):
            raise ValueError(f"Missing engine solution: {item.id}")
        identifiers.add(item.id)
        result.append(item)
    if not result:
        raise ValueError("Exercise bank is empty")
    return result


def content_version(root: Path) -> str:
    digest = hashlib.sha256()
    for directory in ("datasets", "exercises"):
        for file_path in sorted((root / directory).rglob("*")):
            if file_path.is_file():
                digest.update(str(file_path.relative_to(root)).encode())
                digest.update(file_path.read_bytes())
    return digest.hexdigest()
