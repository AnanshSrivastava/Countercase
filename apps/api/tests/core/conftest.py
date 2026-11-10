"""Core tests run against real Postgres (pgvector image).

The schema is built with `alembic upgrade head`, so the migration itself is tested.
TEST_DATABASE_URL defaults to the compose db on localhost:5432; set it if DB_PORT differs.
The database named in the URL is dropped and recreated per test session.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from app.core import db
from app.settings import settings

API_DIR = Path(__file__).resolve().parents[2]
TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://recoup:recoup@localhost:5432/recoup_test"
)


def _recreate_database(url: str) -> None:
    target = make_url(db.sqlalchemy_url(url))
    admin = create_engine(
        target.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        admin.connect().close()
    except OperationalError:
        admin.dispose()
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres not reachable at {target.host}:{target.port}; run `make up`")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def database():
    _recreate_database(TEST_URL)
    original = settings.database_url
    settings.database_url = TEST_URL
    db.reset_engine()
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "app" / "core" / "migrations"))
    command.upgrade(cfg, "head")
    yield TEST_URL
    db.reset_engine()
    settings.database_url = original


@pytest.fixture
def session(database):
    with db.get_engine().begin() as conn:
        tables = (
            "stripe_events, paypal_events, submissions, drafts, evidence_items, disputes, sellers"
        )
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    with db.session_factory()() as s:
        yield s


from .p4_helpers import env  # noqa: E402, F401  (shared fixture for Phase 4 tests)
