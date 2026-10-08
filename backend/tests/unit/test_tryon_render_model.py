"""`TryOnRender` model round-trip (09-virtual-tryon.md §6.6)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from shared.db import create_db_engine
from shared.enums import JobStatus
from shared.models import TryOnRender
from shared.settings import Settings


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "pachapp-data", ml_embed_revision="test-revision"
    )
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _render(cache_key: str = "k1") -> TryOnRender:
    return TryOnRender(
        cache_key=cache_key,
        mannequin_id="m12",
        garment_ids=["g1", "g2"],
        skipped_garment_ids=["g3"],
        unsupported_garment_ids=["g4"],
        params={"width": 576, "height": 768, "steps": 20, "guidance": 2.5, "seed": 42},
    )


def test_round_trip_keeps_json_order_and_defaults(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(_render())
        session.commit()

    with Session(engine) as session:
        row = session.exec(select(TryOnRender)).one()
        assert len(row.id) == 36
        assert row.garment_ids == ["g1", "g2"]
        assert row.skipped_garment_ids == ["g3"]
        assert row.unsupported_garment_ids == ["g4"]
        assert row.params["steps"] == 20
        assert row.status is JobStatus.pending
        assert (row.step, row.progress, row.attempts) == (None, 0, 0)
        assert row.outfit_id is None
        assert row.img_path is None
        assert row.created_at is not None
        assert row.last_accessed_at is not None


def test_cache_key_is_unique(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(_render("same"))
        session.commit()
    with Session(engine) as session:
        session.add(_render("same"))
        with pytest.raises(IntegrityError):
            session.commit()
