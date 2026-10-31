"""Local session files and atomic single-user progress persistence."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def write_json(file_path: Path, document) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = file_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n")
    os.replace(temporary, file_path)


class SessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.directory = root / ".practice"

    def _state(self):
        file_path = self.directory / "progress.json"
        return (
            json.loads(file_path.read_text())
            if file_path.exists()
            else {"current": None, "attempts": []}
        )

    def _folder(self, session_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", session_id):
            raise ValueError("Invalid session ID")
        return self.directory / "sessions" / session_id

    def create(self, exercises, engine, version, seed):
        session = {
            "id": uuid.uuid4().hex[:12],
            "engine": engine,
            "version": version,
            "seed": seed,
            "exercises": [item.id for item in exercises],
            "hints": {},
            "solutions": [],
        }
        folder = self._folder(session["id"])
        for item in exercises:
            directory = folder / item.id
            directory.mkdir(parents=True)
            schema_link = Path(os.path.relpath(self.root / "docs/schema.md", directory)).as_posix()
            (directory / "answer.sql").write_text("-- Write one SELECT or WITH query here.\n")
            (directory / "prompt.md").write_text(
                f"# {item.title}\n\n{item.prompt}\n\n"
                f"Engine: {engine}\n\nColumns: {', '.join(item.columns)}\n\n"
                f"Schema: [Business schema]({schema_link}).\n"
            )
        self.save(session)
        state = self._state()
        state["current"] = session["id"]
        write_json(self.directory / "progress.json", state)
        return session

    def get(self, session_id=None):
        session_id = session_id or self._state()["current"]
        if not session_id:
            raise ValueError("No current session. Run start first")
        file_path = self._folder(session_id) / "session.json"
        if not file_path.exists():
            raise ValueError("Session not found")
        return json.loads(file_path.read_text())

    def save(self, session):
        write_json(self._folder(session["id"]) / "session.json", session)

    def answer(self, session_id, question):
        session = self.get(session_id)
        if question not in session["exercises"]:
            raise ValueError("Question is not part of this session")
        return (self._folder(session_id) / question / "answer.sql").read_text()

    def paths(self, session):
        return {
            question: str(self._folder(session["id"]) / question)
            for question in session["exercises"]
        }

    def files(self, session):
        return {
            question: {
                filename: str(Path(directory) / filename)
                for filename in ("prompt.md", "answer.sql")
            }
            for question, directory in self.paths(session).items()
        }

    def record(self, attempt):
        state = self._state()
        state["attempts"].append({**attempt, "at": datetime.now(timezone.utc).isoformat()})
        write_json(self.directory / "progress.json", state)

    def attempts(self):
        return self._state()["attempts"]

    def seen_exercises(self) -> set[str]:
        seen = {attempt["exercise"] for attempt in self.attempts()}
        for manifest in (self.directory / "sessions").glob("*/session.json"):
            seen.update(json.loads(manifest.read_text())["exercises"])
        return seen

    def assert_sandbox_version(self, engine, version):
        marker = self.directory / f"{engine}.version"
        if marker.exists() and marker.read_text() != version:
            raise ValueError(
                f"Sandbox data/bank changed. Run db reset --engine {engine} before starting"
            )

    def save_sandbox_version(self, engine, version):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{engine}.version").write_text(version)
