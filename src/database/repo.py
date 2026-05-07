"""Thin SQLite repository wrapper used by the API and tests.

We deliberately avoid an ORM: this is a read-mostly analytical workload
on a small synthetic dataset, and direct SQL keeps the generated query
plans transparent in the UI.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from ..config import get_settings
from ..data import SyntheticDataset, generate_dataset
from .schema import SCHEMA_STATEMENTS


class Database:
    """Lightweight SQLite handle with helpers for analytical reads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # -- schema / seeding -------------------------------------------------

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            for stmt in SCHEMA_STATEMENTS:
                cur.execute(stmt)
            conn.commit()

    def is_seeded(self) -> bool:
        with self.connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM patients")
                row = cur.fetchone()
                return bool(row and row[0] > 0)
            except sqlite3.OperationalError:
                return False

    def load_dataset(self, dataset: SyntheticDataset) -> None:
        """Write a SyntheticDataset into the database, replacing existing rows."""
        with self.connect() as conn:
            for table, df in dataset.as_dict().items():
                # diagnosis_date may be a date object — sqlite3 stores it as text.
                if "diagnosis_date" in df.columns:
                    df = df.copy()
                    df["diagnosis_date"] = df["diagnosis_date"].astype(str)
                df.to_sql(table, conn, if_exists="replace", index=False)
            conn.commit()
        # Re-create indexes after to_sql replace.
        self.initialize_schema()

    # -- read helpers -----------------------------------------------------

    def read_sql(self, sql: str, params: tuple | dict | None = None) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(sql, conn, params=params or ())

    def table(self, name: str) -> pd.DataFrame:
        return self.read_sql(f"SELECT * FROM {name}")


def ensure_database(force_reseed: bool = False) -> Database:
    """Return a Database, seeding it from synthetic data if necessary."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.initialize_schema()
    if force_reseed or not db.is_seeded():
        dataset = generate_dataset(
            num_patients=settings.num_patients,
            seed=settings.random_seed,
        )
        db.load_dataset(dataset)
    return db


def get_database() -> Database:
    """FastAPI-friendly accessor (no implicit seeding)."""
    settings = get_settings()
    return Database(settings.db_path)
