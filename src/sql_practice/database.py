"""Database Adapter contract and bounded, read-only execution."""

import hashlib
import secrets
import sqlite3
import time
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

import sqlalchemy as sa
import sqlparse
from sqlalchemy.engine import URL

from sql_practice.datasets import Dataset, seed
from sql_practice.grading import QueryResult


class QueryConnection:
    def __init__(self, connection: sa.Connection, engine: str):
        self.connection = connection
        self.engine = engine

    def query(self, sql: str, *, max_rows: int = 10000, timeout: float = 3) -> QueryResult:
        if self.connection.closed:
            raise ValueError("Query connection is closed")
        if max_rows < 1 or timeout <= 0:
            raise ValueError("Limits must be positive")
        statements = sqlparse.split(sql)
        if len(statements) != 1 or not statements[0].strip():
            raise ValueError("Submit exactly one SQL statement")
        deadline = time.monotonic() + timeout
        try:
            if self.engine == "sqlite":
                native = self.connection.connection.driver_connection
                native.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            elif self.engine == "postgres":
                self.connection.exec_driver_sql(f"SET statement_timeout = {int(timeout * 1000)}")
            else:
                self.connection.exec_driver_sql(
                    f"SET SESSION MAX_EXECUTION_TIME = {int(timeout * 1000)}"
                )
            result = self.connection.exec_driver_sql(
                statements[0], execution_options={"no_parameters": True}
            )
            if not result.returns_rows:
                raise ValueError("A query must return rows")
            columns = tuple(result.keys())
            rows = tuple(tuple(row) for row in result.fetchmany(max_rows + 1))
            result.close()
            if time.monotonic() >= deadline:
                raise ValueError("Query timeout exceeded")
            if len(rows) > max_rows:
                raise ValueError(f"Query exceeded row limit ({max_rows})")
            return QueryResult(columns, rows)
        except sa.exc.SQLAlchemyError as error:
            self.connection.rollback()
            original = getattr(error, "orig", error)
            raise ValueError(f"Query failed: {original}") from None


class DatabaseBackend(Protocol):
    def fixture(self, dataset: Dataset) -> AbstractContextManager[QueryConnection]: ...
    def sandbox(self, dataset: Dataset) -> AbstractContextManager[QueryConnection]: ...


class SQLiteBackend:
    def __init__(self, directory: Path | None = None):
        self.directory = directory

    @contextmanager
    def _open(self, dataset: Dataset, persistent: bool = False):
        filename = f"sandbox_{sandbox_name(dataset)}.sqlite" if dataset.identity else "sandbox.sqlite"
        file_path = self.directory / filename if persistent and self.directory else None
        if file_path:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        existing = file_path is not None and file_path.exists()
        engine = sa.create_engine(
            URL.create("sqlite", database=str(file_path) if file_path else ":memory:")
        )
        try:
            with engine.begin() as writer:
                writer.exec_driver_sql("PRAGMA foreign_keys=ON")
                if not existing:
                    seed(writer, dataset)
            with engine.connect() as reader:
                native = reader.connection.driver_connection
                native.enable_load_extension(False)
                reader.exec_driver_sql("PRAGMA query_only=ON")

                def authorize(action, _first, second, _database, _trigger):
                    allowed = (
                        sqlite3.SQLITE_SELECT,
                        sqlite3.SQLITE_READ,
                        sqlite3.SQLITE_FUNCTION,
                        sqlite3.SQLITE_RECURSIVE,
                    )
                    if action == sqlite3.SQLITE_FUNCTION and second in (
                        "load_extension",
                        "readfile",
                        "writefile",
                    ):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

                native.set_authorizer(authorize)
                try:
                    yield QueryConnection(reader, "sqlite")
                finally:
                    native.set_progress_handler(None, 0)
                    native.set_authorizer(None)
        finally:
            engine.dispose()

    def fixture(self, dataset: Dataset):
        return self._open(dataset)

    def sandbox(self, dataset: Dataset):
        return self._open(dataset, persistent=True)


def sandbox_name(dataset: Dataset) -> str:
    return (
        "practice_" + hashlib.sha256(dataset.identity.encode()).hexdigest()[:20]
        if dataset.identity else "practice_sandbox"
    )


class ServerBackend:
    def __init__(self, engine: str, password: str, port: int):
        self.kind = engine
        self.password = password
        self.port = port

    def _engine(self, database: str, user: str, password: str, *, autocommit=False):
        driver = "postgresql+psycopg" if self.kind == "postgres" else "mysql+pymysql"
        arguments = {"connect_timeout": 5}
        if self.kind == "mysql":
            arguments.update(read_timeout=5, write_timeout=5)
        return sa.create_engine(
            URL.create(
                driver,
                username=user,
                password=password,
                host="127.0.0.1",
                port=self.port,
                database=database,
            ),
            connect_args=arguments,
            isolation_level="AUTOCOMMIT" if autocommit else None,
            execution_options={"no_parameters": True},
        )

    @contextmanager
    def _open(self, dataset: Dataset, persistent: bool = False):
        postgres = self.kind == "postgres"
        name = sandbox_name(dataset) if persistent else "practice_" + secrets.token_hex(8)
        user = name + "_r"
        password = self.password if persistent else secrets.token_hex(24)
        admin = self._engine(
            "postgres" if postgres else "mysql",
            "postgres" if postgres else "root",
            self.password,
            autocommit=True,
        )
        writer_engine = reader_engine = None
        created = False
        try:
            with admin.connect() as connection:
                exists = connection.execute(
                    sa.text(
                        "SELECT 1 FROM pg_database WHERE datname=:name"
                        if postgres
                        else "SELECT 1 FROM information_schema.schemata WHERE schema_name=:name"
                    ),
                    {"name": name},
                ).scalar()
                if not exists:
                    connection.exec_driver_sql(
                        f'CREATE DATABASE "{name}"' if postgres else f"CREATE DATABASE `{name}`"
                    )
                    created = True
                    connection.exec_driver_sql(
                        f"CREATE ROLE {user} LOGIN PASSWORD '{password}'"
                        if postgres
                        else f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'"
                    )
                    if postgres:
                        connection.exec_driver_sql(f'REVOKE ALL ON DATABASE "{name}" FROM PUBLIC')
                        connection.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{name}" TO {user}')
                        connection.exec_driver_sql(
                            f"ALTER ROLE {user} SET default_transaction_read_only = on"
                        )
                    else:
                        connection.exec_driver_sql(f"GRANT SELECT ON `{name}`.* TO '{user}'@'%'")
            writer_engine = self._engine(name, "postgres" if postgres else "root", self.password)
            if created:
                with writer_engine.begin() as writer:
                    seed(writer, dataset)
                    if postgres:
                        writer.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                        writer.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {user}")
                        writer.exec_driver_sql(
                            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {user}"
                        )
            reader_engine = self._engine(name, user, password)
            with reader_engine.connect() as reader:
                yield QueryConnection(reader, self.kind)
        finally:
            for engine in (reader_engine, writer_engine):
                if engine is not None:
                    engine.dispose()
            if not persistent or (created and reader_engine is None):
                with admin.connect() as connection:
                    connection.exec_driver_sql(
                        f'DROP DATABASE IF EXISTS "{name}"'
                        if postgres
                        else f"DROP DATABASE IF EXISTS `{name}`"
                    )
                    connection.exec_driver_sql(
                        f"DROP ROLE IF EXISTS {user}"
                        if postgres
                        else f"DROP USER IF EXISTS '{user}'@'%'"
                    )
            admin.dispose()

    def fixture(self, dataset: Dataset):
        return self._open(dataset)

    def sandbox(self, dataset: Dataset):
        return self._open(dataset, persistent=True)


class PostgresBackend(ServerBackend):
    def __init__(self, password: str, port: int = 55432):
        super().__init__("postgres", password, port)


class MySQLBackend(ServerBackend):
    def __init__(self, password: str, port: int = 53306):
        super().__init__("mysql", password, port)
