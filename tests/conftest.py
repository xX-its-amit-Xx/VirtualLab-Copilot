"""Shared test fixtures."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Make sure tests use a temp db that doesn't pollute the dev one.
@pytest.fixture(scope="session", autouse=True)
def _isolate_settings(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("vlc_db")
    db_path = db_dir / "test.db"
    os.environ["VLC_DB_PATH"] = str(db_path)
    os.environ["VLC_NUM_PATIENTS"] = "120"
    os.environ["VLC_RANDOM_SEED"] = "7"
    # Force a fresh Settings instance.
    from src import config

    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    yield


@pytest.fixture(scope="session")
def db():
    from src.database import ensure_database

    return ensure_database()


@pytest.fixture()
def cohort_service(db):
    from src.analysis import CohortService

    return CohortService(db)
