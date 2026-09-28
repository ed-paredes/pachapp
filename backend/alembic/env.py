"""Alembic environment for pachapp.

Uses `shared.settings.get_settings().db_path` to build the SQLite
URL (rather than `alembic.ini`'s `sqlalchemy.url`), and `SQLModel.metadata`
as the migration target. `render_as_batch=True` is required for SQLite,
which cannot ALTER most column properties in place.

Phase 1 (docs/specs/02-data-model.md) adds the initial tables.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from shared import models  # noqa: F401  (registers tables on SQLModel.metadata)
from shared.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import model modules here as they are added in later phases, so their
# tables register on SQLModel.metadata before autogenerate runs.
target_metadata = SQLModel.metadata


def _sqlite_url() -> str:
    settings = get_settings()
    db_path = settings.db_path
    assert db_path is not None  # derived by Settings' model validator
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no DB connection)."""
    context.configure(
        url=_sqlite_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode, against a live DB connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _sqlite_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
