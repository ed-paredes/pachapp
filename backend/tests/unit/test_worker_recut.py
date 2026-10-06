"""`python -m worker.recut` (U5d, VIS-REQ-032): re-cuts existing garments with the garment-only
rule using fake remover/parser/models. No model or network (VIS-REQ-029)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from ai_fakes import make_models, vector_for
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel
from test_worker_cutout_parse import (
    NAMES,
    SIZE,
    EmptyMatteRemover,
    FakeMatteRemover,
    FakeParser,
    _person_result,
)

from ml.garment_parse import ParseResult
from shared import storage
from shared.db import create_db_engine, create_session_factory
from shared.enums import GarmentCategory, JobStatus
from shared.models import AiCorrection, Garment, Job
from shared.settings import Settings
from worker import recut as recut_module
from worker.ai import LazyModels
from worker.recut import cutout_method_id, main, recut
from worker.steps.cutout import CutoutEngine

OLD_COLOR = (1, 2, 3)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "d", ml_embed_revision="r", thumb_px=32)


@pytest.fixture
def engine_db(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine_db: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine_db)


def _add(factory, settings, **fields) -> str:
    assert settings.images_root is not None
    with factory() as session:
        garment = Garment(img_original="x", **fields)
        garment.img_original = storage.original_path(garment.id)
        garment.img_cutout = storage.cutout_path(garment.id)
        garment.img_thumb = storage.thumb_path(garment.id)
        session.add(garment)
        session.commit()
        garment_id = garment.id
    Image.new("RGB", (SIZE, SIZE), (200, 30, 30)).save(
        _path(settings, storage.original_path(garment_id)), format="JPEG"
    )
    Image.new("RGBA", (5, 5), (*OLD_COLOR, 255)).save(_path(settings, f"cutout/{garment_id}.png"))
    return garment_id


def _path(settings: Settings, rel: str) -> Path:
    assert settings.images_root is not None
    path = settings.images_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get(factory, garment_id: str) -> Garment:
    with factory() as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment


def _run(factory, settings, parser, *, remover=None, models=None, **kwargs):
    remover = remover or FakeMatteRemover()
    models = models or make_models(vector_for(category="top"))
    engine = CutoutEngine(lambda: remover, lambda: parser)
    counts, sheets = recut(settings, factory, engine, LazyModels(lambda: models), **kwargs)
    return counts, sheets, models


def _cutout_bytes(settings, garment_id) -> bytes:
    return _path(settings, f"cutout/{garment_id}.png").read_bytes()


def test_recut_writes_cutout_thumb_colours_embedding_and_marker(factory, settings) -> None:
    garment_id = _add(factory, settings, category=GarmentCategory.top)
    old = _cutout_bytes(settings, garment_id)
    parser = FakeParser(_person_result())

    counts, _, models = _run(factory, settings, parser)

    assert (counts.recut, counts.errors) == (1, 0)
    garment = _get(factory, garment_id)
    assert garment.cutout_method == cutout_method_id(settings)
    assert _cutout_bytes(settings, garment_id) != old
    with Image.open(_path(settings, f"cutout/{garment_id}.png")) as cutout:
        assert cutout.size == (32, 30)  # top only, no arms or legs
    assert _path(settings, f"thumb/{garment_id}.webp").exists()
    assert garment.colors and garment.color_confidence is not None
    assert garment.embedding == models.embedder.vector.astype(np.float32).tobytes()
    assert garment.embedding_model == models.embedder.model_id
    assert garment.category == GarmentCategory.top  # existing value untouched
    assert len(models.embedder.images) == 1


def test_second_run_is_a_noop_and_loads_nothing(factory, settings) -> None:
    garment_id = _add(factory, settings, category=GarmentCategory.top)
    _run(factory, settings, FakeParser(_person_result()))
    first = _get(factory, garment_id).model_dump()
    after = _cutout_bytes(settings, garment_id)

    def forbidden():
        raise AssertionError("nothing must be built when nothing is pending")

    engine = CutoutEngine(forbidden, forbidden)
    counts, _ = recut(settings, factory, engine, LazyModels(forbidden))

    assert (counts.recut, counts.skipped_done) == (0, 1)
    assert _get(factory, garment_id).model_dump() == first
    assert _cutout_bytes(settings, garment_id) == after


def test_dry_run_writes_nothing_and_loads_no_model(factory, settings) -> None:
    garment_id = _add(factory, settings)
    old = _cutout_bytes(settings, garment_id)
    before = _get(factory, garment_id).model_dump()

    def forbidden():
        raise AssertionError("dry run must not build models")

    counts, sheets = recut(
        settings,
        factory,
        CutoutEngine(forbidden, forbidden),
        LazyModels(forbidden),
        dry_run=True,
    )

    assert counts.would_recut == 1 and sheets == []
    assert _get(factory, garment_id).model_dump() == before
    assert _cutout_bytes(settings, garment_id) == old


def test_user_corrected_colours_are_kept_and_owned_attributes_untouched(factory, settings) -> None:
    garment_id = _add(
        factory,
        settings,
        category=GarmentCategory.top,
        colors=[{"name": "rojo", "hex": "#c81e28", "proportion": 1.0}],
        color_confidence=1.0,
        material="lana",  # typed by hand, no ai_confidence entry -> user-owned
    )
    with factory() as session:
        session.add(
            AiCorrection(
                garment_id=garment_id, field="colors", ai_value=[], corrected_value=["rojo"]
            )
        )
        session.commit()

    counts, _, _ = _run(factory, settings, FakeParser(_person_result()))

    garment = _get(factory, garment_id)
    assert counts.recut == 1 and counts.colors_kept == 1
    assert garment.colors == [{"name": "rojo", "hex": "#c81e28", "proportion": 1.0}]
    assert garment.material == "lana"
    assert garment.formality is not None  # empty and not owned -> filled like the backfill


def test_existing_attribute_values_are_not_recomputed(factory, settings) -> None:
    garment_id = _add(factory, settings, category=GarmentCategory.shoes)
    _run(factory, settings, FakeParser(_person_result()), models=make_models(vector_for()))
    assert _get(factory, garment_id).category == GarmentCategory.shoes


def test_no_person_keeps_the_old_cutout(factory, settings) -> None:
    garment_id = _add(factory, settings)
    old = _cutout_bytes(settings, garment_id)
    flat_lay = ParseResult(np.zeros((SIZE, SIZE), dtype=np.uint8), NAMES)

    counts, _, models = _run(factory, settings, FakeParser(flat_lay))

    assert (counts.unchanged, counts.recut) == (1, 0)
    assert _cutout_bytes(settings, garment_id) == old
    assert models.embedder.images == []
    assert _get(factory, garment_id).cutout_method == cutout_method_id(settings)


def test_empty_matte_keeps_the_old_cutout(factory, settings) -> None:
    garment_id = _add(factory, settings)
    old = _cutout_bytes(settings, garment_id)

    counts, _, _ = _run(
        factory, settings, FakeParser(_person_result()), remover=EmptyMatteRemover()
    )

    assert (counts.unchanged, counts.recut) == (1, 0)
    assert _cutout_bytes(settings, garment_id) == old


def test_small_mask_keeps_old_cutout_and_flags_review(factory, settings) -> None:
    garment_id = _add(factory, settings, category=GarmentCategory.top)
    reviewed = _add(factory, settings, category=GarmentCategory.top, user_verified=True)
    old = _cutout_bytes(settings, garment_id)
    grid = np.zeros((SIZE, SIZE), dtype=np.uint8)
    grid[0:1, 14:20] = 2  # tiny top, well under 1 % of the image
    grid[0:6, 24:36] = 1  # a face, so there is a person

    counts, _, _ = _run(factory, settings, FakeParser(ParseResult(grid, NAMES)))

    assert (counts.small_mask, counts.recut) == (2, 0)
    assert _cutout_bytes(settings, garment_id) == old
    assert _get(factory, garment_id).needs_review is True
    assert _get(factory, reviewed).needs_review is False  # reviewed garments stay out


def test_parser_failure_is_an_error_without_marker(factory, settings) -> None:
    garment_id = _add(factory, settings)
    old = _cutout_bytes(settings, garment_id)

    counts, _, _ = _run(factory, settings, FakeParser(error=True))

    assert (counts.errors, counts.recut) == (1, 0)
    assert _cutout_bytes(settings, garment_id) == old
    assert _get(factory, garment_id).cutout_method is None  # retried by the next run


def test_failed_atomic_write_keeps_the_old_cutout(factory, settings, monkeypatch) -> None:
    garment_id = _add(factory, settings, category=GarmentCategory.top)
    old = _cutout_bytes(settings, garment_id)

    def boom(self, data):  # simulate a crash while writing the temp file
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    counts, _, _ = _run(factory, settings, FakeParser(_person_result()))
    monkeypatch.undo()

    assert counts.errors == 1
    assert _cutout_bytes(settings, garment_id) == old
    assert _get(factory, garment_id).cutout_method is None


def test_busy_limit_ids_and_contact_sheet(factory, settings, tmp_path) -> None:
    ids = [_add(factory, settings, category=GarmentCategory.top) for _ in range(4)]
    with factory() as session:
        session.add(Job(garment_id=ids[0], status=JobStatus.running))
        session.commit()

    counts, sheets, _ = _run(
        factory,
        settings,
        FakeParser(_person_result()),
        ids=ids[:3],
        limit=1,
        out_dir=tmp_path / "out",
    )

    assert (counts.recut, counts.skipped_busy) == (1, 1)
    assert _get(factory, ids[1]).cutout_method is not None
    assert (
        _get(factory, ids[0]).cutout_method is None and _get(factory, ids[3]).cutout_method is None
    )
    assert len(sheets) == 1 and sheets[0].exists()


def test_refuses_when_the_parser_setting_is_off(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        recut_module,
        "get_settings",
        lambda: Settings(_env_file=None, ml_embed_revision="r", ml_garment_parse=False),
    )
    assert main([]) == 2
    assert "PACHAPP_ML_GARMENT_PARSE" in capsys.readouterr().err
