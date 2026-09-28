"""SQLite engine and session factory for pachapp (docs/specs/02-data-model.md, D4).

No engine is created at import time: callers (api, worker, tests, Alembic's
`env.py`) build one explicitly from `Settings`, so importing this module has
no I/O side effects.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

from shared.settings import Settings, get_settings


def _set_sqlite_pragmas(dbapi_connection: sqlite3.Connection, busy_timeout_ms: int) -> None:
    """Applied on every new DBAPI connection (D4): WAL journal mode, foreign
    key enforcement (SQLite has it off by default, per-connection), and a
    `busy_timeout` so concurrent API/worker writers retry instead of
    immediately raising `database is locked`."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    finally:
        cursor.close()


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Build a SQLite engine for `settings.db_path` with D4's pragmas wired
    to the `connect` event.

    Does not run at import time and does not cache its result — call it
    explicitly from app/worker/test/Alembic startup code, once per process
    (or once per test), with the `Settings` in effect there.
    """
    settings = settings or get_settings()
    assert settings.db_path is not None  # derived by Settings' model validator
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{settings.db_path}")
    busy_timeout_ms = settings.db_busy_timeout_ms

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
        _set_sqlite_pragmas(dbapi_connection, busy_timeout_ms)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A `sessionmaker` bound to `engine`, producing SQLModel `Session`s."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
