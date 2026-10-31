"""Portable YAML schema and CSV records, validated before database IO."""

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

import sqlalchemy as sa
import yaml

FIXTURES = ("base", "edge", "empty", "no-sales")


@dataclass
class Dataset:
    metadata: sa.MetaData
    rows: dict[str, list[dict]]


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ValueError(f"Invalid schema identifier: {value}")
    return value


def parse_value(raw: str, column: dict):
    if raw == r"\N":
        if not column.get("nullable", False):
            raise ValueError("NULL in non-nullable column")
        return None
    kind = column["type"]
    converters = {
        "integer": int,
        "text": lambda value: value.replace(r"\\", "\\"),
        "date": date.fromisoformat,
        "timestamp": datetime.fromisoformat,
        "decimal": Decimal,
    }
    value = converters[kind](raw)
    if kind == "decimal" and not value.is_finite():
        raise ValueError("Non-finite decimal")
    return value


def parse_dataset(schema: dict, tables: dict[str, str]) -> Dataset:
    if schema.get("version") != 1 or not schema.get("tables"):
        raise ValueError("Unsupported or empty dataset schema")
    metadata = sa.MetaData()
    rows = {}
    for table_name, table_spec in schema["tables"].items():
        identifier(table_name)
        columns = []
        for column_name, specification in table_spec["columns"].items():
            identifier(column_name)
            types = {
                "integer": sa.Integer(),
                "text": sa.String(255),
                "date": sa.Date(),
                "timestamp": sa.DateTime(),
                "decimal": sa.Numeric(
                    specification.get("precision", 18), specification.get("scale", 2)
                ),
            }
            if specification["type"] not in types:
                raise ValueError(f"Unknown type: {specification['type']}")
            constraints = []
            if "references" in specification:
                reference_table, reference_column = specification["references"].split(".")
                identifier(reference_table)
                identifier(reference_column)
                constraints.append(sa.ForeignKey(specification["references"]))
            columns.append(
                sa.Column(
                    column_name,
                    types[specification["type"]],
                    *constraints,
                    primary_key=specification.get("primary_key", False),
                    nullable=specification.get("nullable", False),
                )
            )
        if not columns:
            raise ValueError(f"No columns: {table_name}")
        sa.Table(table_name, metadata, *columns)
        reader = csv.DictReader(StringIO(tables[table_name]))
        if reader.fieldnames != list(table_spec["columns"]):
            raise ValueError(f"CSV columns/order differ from schema: {table_name}")
        records = []
        for record in reader:
            if None in record or any(value is None for value in record.values()):
                raise ValueError(f"Malformed CSV record: {table_name}")
            records.append(
                {
                    name: parse_value(record[name], specification)
                    for name, specification in table_spec["columns"].items()
                }
            )
        keys = [name for name, spec in table_spec["columns"].items() if spec.get("primary_key")]
        primary_values = [tuple(record[name] for name in keys) for record in records]
        if keys and len(set(primary_values)) != len(primary_values):
            raise ValueError(f"duplicate primary key: {table_name}")
        rows[table_name] = records
    for table in metadata.sorted_tables:
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                target = foreign_key.column
                allowed = {record[target.name] for record in rows[target.table.name]}
                if any(
                    record[column.name] is not None and record[column.name] not in allowed
                    for record in rows[table.name]
                ):
                    raise ValueError(f"Broken foreign key: {table.name}.{column.name}")
    return Dataset(metadata, rows)


def load_dataset(root: Path, fixture: str = "base") -> Dataset:
    if fixture not in FIXTURES:
        raise ValueError(f"Unknown fixture: {fixture}")
    directory = root / "datasets/business"
    schema = yaml.safe_load((directory / "schema.yaml").read_text())
    tables = {}
    for name in schema["tables"]:
        source = directory / "tables" / f"{name}.csv"
        override = directory / "fixtures" / fixture / f"{name}.csv"
        text = (override if override.is_file() else source).read_text()
        omit = fixture == "empty" or (
            fixture == "no-sales" and name in ("orders", "order_items", "payments")
        )
        tables[name] = text.splitlines()[0] + "\n" if omit else text
    return parse_dataset(schema, tables)


def seed(connection: sa.Connection, dataset: Dataset) -> None:
    dataset.metadata.create_all(connection)
    for table in dataset.metadata.sorted_tables:
        if dataset.rows[table.name]:
            connection.execute(table.insert(), dataset.rows[table.name])
