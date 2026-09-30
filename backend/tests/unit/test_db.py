"""shared.db: engine creation has no import-time side effects, and every new
connection gets D4's pragmas (WAL, foreign_keys, busy_timeout)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from shared.db import create_db_engine, create_session_factory
from shared.settings import Settings


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    kwargs = {
        "_env_file": None,
        "data_dir": tmp_path / "pachapp-data",
        "llm_provider": "anthropic",
        "llm_model_id": "claude-sonnet-5-20260101",
        "llm_api_key": "test-secret-key",
        "ml_embed_revision": "test-revision",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def test_create_db_engine_creates_db_file_and_parent_dirs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert not settings.db_path.exists()

    engine = create_db_engine(settings)
    with engine.connect():
        pass

    assert settings.db_path.parent.is_dir()
    assert settings.db_path.exists()


def test_create_db_engine_rejects_unset_db_path(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.db_path = None

    with pytest.raises(ValueError, match="db_path"):
        create_db_engine(settings)


def test_pragmas_applied_on_connect(tmp_path: Path) -> None:
    settings = _settings(tmp_path, db_busy_timeout_ms=1234)
    engine = create_db_engine(settings)

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 1234


def test_pragmas_applied_on_every_new_connection(tmp_path: Path) -> None:
    """The pragmas are per-connection state in SQLite (except WAL, which is
    persisted to the file) — the `connect` event must fire again for a
    second connection, not just the first."""
    settings = _settings(tmp_path)
    engine = create_db_engine(settings)

    with engine.connect() as first:
        first.execute(text("SELECT 1"))
    with engine.connect() as second:
        assert second.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_session_factory_produces_working_sessions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1


def test_orm_rows_and_relationships_can_be_created(tmp_path: Path) -> None:
    """Regression: with `from __future__ import annotations`, sqlmodel could not
    map the `Relationship` annotations, so creating any ORM row raised a mapper
    error. Existing tests only used raw SQL, which hid it."""
    from sqlmodel import SQLModel, select

    from shared.models import Garment, Job

    settings = _settings(tmp_path)
    engine = create_db_engine(settings)
    SQLModel.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        garment = Garment(img_original="original/g1.jpg")
        session.add(garment)
        session.flush()
        session.add(Job(garment_id=garment.id))
        session.commit()

    with session_factory() as session:
        stored = session.exec(select(Garment)).one()
        assert [job.garment_id for job in stored.jobs] == [stored.id]
