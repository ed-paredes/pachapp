"""FastAPI dependencies: settings and short-lived DB sessions (D4).

The engine is built lazily on first use (under a lock) and cached on `app.state`, so
importing `api.main` has no I/O side effects and tests can inject their own
`Settings` through `create_app(settings)`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from fastapi import FastAPI, Request
from sqlalchemy.engine import Engine
from sqlmodel import Session

from shared.db import create_db_engine, create_session_factory
from shared.settings import Settings

# R3-003: sync routes run in a threadpool, so the first requests can race on
# the lazy engine creation; double-checked locking keeps one engine per app.
_engine_lock = threading.Lock()


def get_engine(app: FastAPI) -> Engine:
    engine = getattr(app.state, "engine", None)
    if engine is None:
        with _engine_lock:
            engine = getattr(app.state, "engine", None)
            if engine is None:
                engine = create_db_engine(app.state.settings)
                app.state.engine = engine
    return engine


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    """One short transaction scope per request; routes commit explicitly."""
    factory = create_session_factory(get_engine(request.app))
    with factory() as session:
        yield session
