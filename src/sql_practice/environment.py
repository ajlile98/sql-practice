"""Project-owned local Docker services and explicit backend construction."""

import hashlib
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from sql_practice.database import MySQLBackend, PostgresBackend, SQLiteBackend
from sql_practice.exercises import ENGINES
from sql_practice.sessions import write_json


def project_root() -> Path:
    configured = os.environ.get("SQL_PRACTICE_ROOT")
    candidates = [Path(configured)] if configured else [Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        if (candidate / "exercises/bank.yaml").is_file():
            return candidate.resolve()
    raise ValueError("Run from the practice repository or set SQL_PRACTICE_ROOT")


class LocalEnvironment:
    def __init__(self, root: Path):
        self.root = root
        self.directory = root / ".practice"
        self.project = "sql-practice-" + hashlib.sha256(str(root).encode()).hexdigest()[:10]

    def configuration(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        file_path = self.directory / "local.json"
        if not file_path.exists():
            ports = {
                "postgres": int(os.environ.get("SQL_PRACTICE_PG_PORT", "55432")),
                "mysql": int(os.environ.get("SQL_PRACTICE_MYSQL_PORT", "53306")),
            }
            if (
                any(not 1024 <= value <= 65535 for value in ports.values())
                or len(set(ports.values())) != 2
            ):
                raise ValueError("Database ports must be different and between 1024 and 65535")
            write_json(file_path, {"password": secrets.token_hex(24), "ports": ports})
            file_path.chmod(0o600)
        return json.loads(file_path.read_text())

    def compose(self, *arguments):
        if not shutil.which("docker"):
            raise ValueError("Docker is not installed; use SQLite or install Docker Desktop")
        configuration = self.configuration()
        env_file = self.directory / "db.env"
        env_file.write_text(
            f"POSTGRES_PASSWORD={configuration['password']}\nMYSQL_ROOT_PASSWORD={configuration['password']}\n"
            f"PG_PORT={configuration['ports']['postgres']}\nMYSQL_PORT={configuration['ports']['mysql']}\n"
        )
        env_file.chmod(0o600)
        command = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(env_file),
            "--file",
            str(self.root / "compose.yaml"),
            "--profile",
            "postgres",
            "--profile",
            "mysql",
            *arguments,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        if result.returncode:
            raise ValueError(
                "Local Docker command failed. Start Docker Desktop and check port availability.\n"
                + result.stderr[-2000:]
            )
        return result.stdout.strip()

    def up(self, engine):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        if engine != "sqlite":
            return self.compose("up", "--detach", "--wait", engine)
        return "SQLite is ready (no server required)"

    def backend(self, engine):
        if engine == "sqlite":
            return SQLiteBackend(self.directory)
        factories = {"postgres": PostgresBackend, "mysql": MySQLBackend}
        if engine not in factories:
            raise ValueError(f"Unknown engine: {engine}")
        configuration = self.configuration()
        return factories[engine](configuration["password"], configuration["ports"][engine])

    def down(self, engine):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        return (
            self.compose("stop", engine) if engine != "sqlite" else "SQLite has no server to stop"
        )

    def reset(self, engine):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        if engine == "sqlite":
            for file_path in self.directory.glob("sandbox*.sqlite"):
                file_path.unlink(missing_ok=True)
        else:
            self.compose("rm", "--stop", "--force", "--volumes", engine)
            volume = f"{self.project}_{engine}_data"
            result = subprocess.run(
                ["docker", "volume", "rm", volume],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode and "no such volume" not in result.stderr.lower():
                raise ValueError(result.stderr.strip())
        (self.directory / f"{engine}.version").unlink(missing_ok=True)

    def doctor(self):
        result = {"root": str(self.root), "sqlite": "available", "docker": "not installed"}
        if shutil.which("docker"):
            try:
                check = subprocess.run(
                    ["docker", "info", "--format", "{{.ServerVersion}}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                result["docker"] = (
                    check.stdout.strip()
                    if check.returncode == 0
                    else "daemon stopped; open Docker Desktop"
                )
            except subprocess.TimeoutExpired:
                result["docker"] = "daemon did not respond"
        return result
