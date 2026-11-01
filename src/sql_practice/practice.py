"""Practice Facade: orchestration independent of database implementations."""

from collections.abc import Callable

from sql_practice.database import DatabaseBackend
from sql_practice.datasets import FIXTURES
from sql_practice.exercises import (
    Categories,
    Exercise,
    exercise_version,
    select_exercises,
    solved_exercises,
)
from sql_practice.grading import compare_results
from sql_practice.progress import learning_progress


class PracticeService:
    def __init__(
        self,
        bank: list[Exercise],
        version: str,
        store,
        backend_factory: Callable[[str], DatabaseBackend],
        dataset_loader,
        *,
        selection_strategy=None,
        comparison_factory=None,
        categories: Categories | None = None,
        dataset_versions=None,
    ):
        self.bank = bank
        self.version = version
        self.store = store
        self.backend_factory = backend_factory
        self.dataset_loader = dataset_loader
        self.selection_strategy = selection_strategy
        self.comparison_factory = comparison_factory or (lambda _exercise: None)
        self.categories = categories or Categories()
        self.dataset_versions = dataset_versions

    def _dataset(self, fixture, name):
        if self.dataset_versions is None:
            return self.dataset_loader(fixture)
        return self.dataset_loader(fixture, name=name)

    def start(self, *, engine="postgres", seed=None, **filters):
        solved = solved_exercises(self.store.attempts())
        selected = select_exercises(
            self.bank,
            engine=engine,
            seed=seed,
            solved=solved,
            seen=self.store.seen_exercises(),
            strategy=self.selection_strategy,
            categories=self.categories,
            **filters,
        )
        if self.dataset_versions is None:
            self.store.assert_sandbox_version(engine, self.version)
            with self.backend_factory(engine).sandbox(self.dataset_loader("base")):
                pass
            self.store.save_sandbox_version(engine, self.version)
            return self.store.create(selected, engine, self.version, seed)
        datasets = {}
        backend = self.backend_factory(engine)
        for item in selected:
            if item.dataset not in datasets:
                dataset = self._dataset("base", item.dataset)
                with backend.sandbox(dataset):
                    pass
                datasets[item.dataset] = dataset
        bindings = {
            item.id: {
                "exercise_version": exercise_version(item),
                "dataset": item.dataset,
                "dataset_version": self.dataset_versions(item.dataset),
                "as_of": datasets[item.dataset].as_of,
            } for item in selected
        }
        return self.store.create(selected, engine, self.version, seed, bindings=bindings)

    def _context(self, session_id=None, question=None):
        session = self.store.get(session_id)
        if "bindings" not in session and session["version"] != self.version:
            raise ValueError(
                "Dataset or exercise bank changed; start a new session (old answers are preserved)"
            )
        if question is None:
            if len(session["exercises"]) != 1:
                raise ValueError(
                    "This session has multiple exercises; specify --question EXERCISE_ID"
                )
            question = session["exercises"][0]
        if question not in session["exercises"]:
            raise ValueError("Exercise is not in this session")
        exercise = next((item for item in self.bank if item.id == question), None)
        if exercise is None:
            raise ValueError("Exercise was removed; old answers are preserved")
        if "bindings" in session:
            binding = session["bindings"][question]
            if binding["exercise_version"] != exercise_version(exercise):
                raise ValueError(f"Exercise {question} changed; start a new session (old answers are preserved)")
            if self.dataset_versions is None or binding["dataset"] != exercise.dataset or (
                binding["dataset_version"] != self.dataset_versions(exercise.dataset)
            ):
                raise ValueError(f"Dataset {exercise.dataset} changed; start a new session (old answers are preserved)")
        return session, exercise

    def run(self, session_id=None, question=None):
        session, exercise = self._context(session_id, question)
        sql = self.store.answer(session["id"], exercise.id)
        dataset = self._dataset("base", exercise.dataset)
        if "bindings" not in session:
            self.store.assert_sandbox_version(session["engine"], self.version)
            if hasattr(dataset, "identity"):
                dataset.identity = ""
        with self.backend_factory(session["engine"]).sandbox(dataset) as connection:
            return connection.query(sql)

    def check(self, session_id=None, question=None):
        session, exercise = self._context(session_id, question)
        sql = self.store.answer(session["id"], exercise.id)
        backend = self.backend_factory(session["engine"])
        cases = []
        for fixture in FIXTURES:
            try:
                with backend.fixture(self._dataset(fixture, exercise.dataset)) as connection:
                    expected = connection.query(exercise.sql(session["engine"]))
                    actual = connection.query(sql)
                    comparison = compare_results(
                        expected,
                        actual,
                        ordered=exercise.ordered,
                        strategy=self.comparison_factory(exercise),
                    )
                    cases.append(
                        {
                            "fixture": fixture,
                            "passed": comparison.passed,
                            "message": comparison.message,
                        }
                    )
            except ValueError as error:
                cases.append({"fixture": fixture, "passed": False, "message": str(error)})
        result = {
            "session": session["id"],
            "exercise": exercise.id,
            "engine": session["engine"],
            "tags": list(exercise.tags),
            "passed": all(case["passed"] for case in cases),
            "assisted": bool(session["hints"].get(exercise.id))
            or exercise.id in session["solutions"],
            "fixtures": cases,
        }
        self.store.record(result)
        return result

    def hint(self, session_id=None, question=None):
        session, exercise = self._context(session_id, question)
        used = session["hints"].get(exercise.id, 0)
        if used >= len(exercise.hints):
            return "No more hints. Request the solution explicitly."
        session["hints"][exercise.id] = used + 1
        self.store.save(session)
        return exercise.hints[used]

    def solution(self, session_id=None, question=None):
        session, exercise = self._context(session_id, question)
        if exercise.id not in session["solutions"]:
            session["solutions"].append(exercise.id)
        self.store.save(session)
        return exercise.sql(session["engine"])

    def progress(self, *, engine=None, difficulty=None, category=None, topic=None):
        return learning_progress(
            self.bank,
            self.store.attempts(),
            self.categories,
            engine=engine,
            difficulty=difficulty,
            category=category,
            topic=topic,
        )
