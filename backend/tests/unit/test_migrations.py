"""Migration tests for docs/specs/02-data-model.md: run the real Alembic
migration (never `SQLModel.metadata.create_all`) against a fresh tmp-path
SQLite DB, then assert on the resulting schema.

DAT-REQ-013/014: schema changes go through Alembic, one linear history.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from shared.settings import get_settings

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point `Settings` at a fresh tmp-path data dir, run `alembic upgrade
    head` against it, and hand back the resulting SQLite file's path."""
    monkeypatch.setenv("PACHAPP_DATA_DIR", str(tmp_path / "pachapp-data"))
    monkeypatch.setenv("PACHAPP_LLM_PROVIDER", "test-provider")
    monkeypatch.setenv("PACHAPP_LLM_MODEL_ID", "test-model-1")
    monkeypatch.setenv("PACHAPP_LLM_API_KEY", "test-key")
    monkeypatch.setenv("PACHAPP_ML_EMBED_REVISION", "test-revision")
    get_settings.cache_clear()

    try:
        command.upgrade(_alembic_config(), "head")

        db_path = get_settings().db_path
        assert db_path is not None
        assert db_path.exists()
        yield db_path
    finally:
        get_settings.cache_clear()


def _connect_with_fk_enforcement(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    return {row[1] for row in rows}


def test_upgrade_head_creates_all_tables(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        tables = _table_names(conn)
    finally:
        conn.close()

    for table in (
        "garment",
        "outfit",
        "outfit_item",
        "wear_log",
        "job",
        "setting",
        "ai_correction",
        "tryon_renders",
    ):
        assert table in tables


def test_tryon_renders_indexes_and_unique_cache_key(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        indexes = _index_names(conn, "tryon_renders")
        unique_cols = [
            [col[2] for col in conn.execute(f"PRAGMA index_info({row[1]})")]
            for row in conn.execute("PRAGMA index_list(tryon_renders)")
            if row[2]
        ]
        columns = _column_names(conn, "tryon_renders")
    finally:
        conn.close()

    assert "idx_tryon_renders_status" in indexes
    assert ["cache_key"] in unique_cols
    assert {"cache_key", "garment_ids", "skipped_garment_ids", "unsupported_garment_ids"} <= columns


def test_garment_columns_match_spec(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        columns = _column_names(conn, "garment")
    finally:
        conn.close()

    assert columns == {
        "id",
        "created_at",
        "updated_at",
        "img_original",
        "img_cutout",
        "cutout_method",
        "img_thumb",
        "category",
        "subcategory",
        "colors",
        "is_neutral",
        "pattern",
        "formality",
        "style_tags",
        "seasons",
        "warmth",
        "material",
        "brand",
        "notes",
        "status",
        "embedding",
        "embedding_model",
        "embedding_dim",
        "ai_confidence",
        "color_confidence",
        "needs_review",
        "user_verified",
        "wear_count",
        "last_worn_at",
    }


def test_expected_indexes_exist(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        assert {"idx_garment_status", "idx_garment_category", "idx_garment_needs_review"} <= (
            _index_names(conn, "garment")
        )
        assert {"idx_outfit_item_outfit", "idx_outfit_item_garment"} <= _index_names(
            conn, "outfit_item"
        )
        assert "idx_job_status" in _index_names(conn, "job")
        assert "idx_ai_correction_field" in _index_names(conn, "ai_correction")
    finally:
        conn.close()


def test_setting_singleton_row_seeded_with_spec_defaults(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        rows = conn.execute("SELECT * FROM setting").fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM setting").description]
    finally:
        conn.close()

    assert len(rows) == 1
    row = dict(zip(columns, rows[0], strict=True))
    assert row["id"] == 1
    assert row["weight_color"] == 0.35
    assert row["weight_style"] == 0.25
    assert row["weight_novelty"] == 0.25
    assert row["weight_preference"] == 0.15
    assert row["no_repeat_days"] == 14
    assert row["max_accessories"] == 2
    assert row["duplicate_warning_threshold"] == 0.92
    assert row["needs_review_threshold"] == 0.7
    assert row["color_review_threshold"] == 0.7
    assert row["updated_at"] is not None


def _insert_garment(conn: sqlite3.Connection, garment_id: str) -> None:
    conn.execute(
        "INSERT INTO garment (id, created_at, updated_at, img_original, status, "
        "needs_review, user_verified, wear_count) VALUES (?, ?, ?, ?, ?, 0, 0, 0)",
        (garment_id, "2026-01-01T00:00:00", "2026-01-01T00:00:00", "g.jpg", "active"),
    )


def _insert_outfit(conn: sqlite3.Connection, outfit_id: str, rating: int = 0) -> None:
    conn.execute(
        "INSERT INTO outfit (id, created_at, source, is_favorite, rating) "
        "VALUES (?, ?, 'manual', 0, ?)",
        (outfit_id, "2026-01-01T00:00:00", rating),
    )


def test_job_rejects_foreign_key_to_missing_garment(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                "INSERT INTO job (id, garment_id, status, progress, attempts, created_at) "
                "VALUES ('job-1', 'missing-garment', 'pending', 0, 0, '2026-01-01T00:00:00')"
            )
    finally:
        conn.close()


def test_outfit_item_unique_constraint_rejects_duplicate_pair(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        _insert_garment(conn, "g-1")
        _insert_outfit(conn, "o-1")
        conn.execute(
            "INSERT INTO outfit_item (id, outfit_id, garment_id, slot, layer) "
            "VALUES ('oi-1', 'o-1', 'g-1', 'top', 2)"
        )

        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conn.execute(
                "INSERT INTO outfit_item (id, outfit_id, garment_id, slot, layer) "
                "VALUES ('oi-2', 'o-1', 'g-1', 'top', 2)"
            )
    finally:
        conn.close()


def test_wear_log_unique_date_constraint_rejects_second_row_same_day(migrated_db: Path) -> None:
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        _insert_outfit(conn, "o-1")
        _insert_outfit(conn, "o-2")
        conn.execute(
            "INSERT INTO wear_log (id, date, outfit_id, created_at) "
            "VALUES ('wl-1', '2026-01-01', 'o-1', '2026-01-01T00:00:00')"
        )

        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conn.execute(
                "INSERT INTO wear_log (id, date, outfit_id, created_at) "
                "VALUES ('wl-2', '2026-01-01', 'o-2', '2026-01-01T00:00:00')"
            )
    finally:
        conn.close()


def test_outfit_rating_check_constraint_rejects_out_of_range(migrated_db: Path) -> None:
    """DAT-REQ-005: `rating` restricted to {-1, 0, 1}."""
    conn = _connect_with_fk_enforcement(migrated_db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_outfit(conn, "o-bad", rating=2)
    finally:
        conn.close()


def test_downgrade_then_upgrade_round_trip(migrated_db: Path) -> None:
    cfg = _alembic_config()

    command.downgrade(cfg, "base")
    conn = sqlite3.connect(migrated_db)
    try:
        remaining = _table_names(conn) - {"alembic_version"}
    finally:
        conn.close()
    assert remaining == set()

    command.upgrade(cfg, "head")
    conn = sqlite3.connect(migrated_db)
    try:
        tables_after = _table_names(conn)
    finally:
        conn.close()
    assert "garment" in tables_after
    assert "setting" in tables_after


def test_alembic_check_reports_no_drift(migrated_db: Path) -> None:
    """No difference between `shared.models`' metadata and the migration
    history — guards against a model change that forgot a migration."""
    command.check(_alembic_config())
