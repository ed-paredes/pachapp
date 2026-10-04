"""`python -m worker.backfill` (08-local-vision.md step 4 subset): fills missing
attributes/embeddings of existing garments, never user fields, idempotent. Offline."""

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

from shared.db import create_db_engine, create_session_factory
from shared.enums import GarmentCategory, GarmentPattern, GarmentStatus, JobStatus
from shared.models import AiCorrection, Garment, Job
from shared.settings import Settings
from worker.ai import AiModels, LazyModels
from worker.backfill import backfill

MODEL_ID = "hf-hub:Marqo/marqo-fashionSigLIP@test-revision"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", ml_embed_revision="test-revision")


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _models(vector=None) -> AiModels:
    models = make_models(vector)
    models.embedder.model_id = MODEL_ID  # type: ignore[attr-defined]
    return models


def _add(factory, settings, *, image: bool = True, cutout: bool = False, **fields) -> str:
    assert settings.images_root is not None
    with factory() as session:
        garment = Garment(img_original="", **fields)
        garment.img_original = f"original/{garment.id}.jpg"
        if cutout:
            garment.img_cutout = f"cutout/{garment.id}.png"
        session.add(garment)
        session.commit()
        garment_id = garment.id
    if image:
        for rel, mode in (
            (f"original/{garment_id}.jpg", "RGB"),
            (f"cutout/{garment_id}.png", "RGBA"),
        ):
            if rel.startswith("cutout") and not cutout:
                continue
            path = settings.images_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new(mode, (20, 30)).save(path)
    return garment_id


def _get(factory, garment_id: str) -> Garment:
    with factory() as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment


def _complete(factory, settings, models: AiModels) -> str:
    """A garment already processed by the worker steps."""
    garment_id = _add(factory, settings)
    assert backfill(settings, factory, LazyModels(lambda: models)).processed == 1
    return garment_id


def test_fills_attributes_and_embedding_for_every_status(factory, settings) -> None:
    ids = {status: _add(factory, settings, status=status, cutout=True) for status in GarmentStatus}
    models = _models(vector_for(category="outerwear", formality=4))

    counts = backfill(settings, factory, LazyModels(lambda: models))

    assert (counts.processed, counts.skipped, counts.failed) == (len(ids), 0, 0)
    for status, garment_id in ids.items():
        garment = _get(factory, garment_id)
        assert garment.status == status  # untouched
        assert garment.category == GarmentCategory.outerwear and garment.formality == 4
        assert garment.ai_confidence["category"]["source"] == "zero_shot"
        assert garment.embedding == models.embedder.vector.astype(np.float32).tobytes()  # type: ignore[attr-defined]
        assert garment.embedding_model == MODEL_ID
        assert garment.embedding_dim == models.embedder.dim


def test_embeds_the_cutout_and_falls_back_to_the_original(factory, settings) -> None:
    _add(factory, settings, cutout=True)
    _add(factory, settings, cutout=False)
    models = _models()

    backfill(settings, factory, LazyModels(lambda: models))

    modes = sorted(img.mode for img in models.embedder.images)  # type: ignore[attr-defined]
    assert modes == ["RGB", "RGBA"]


def test_second_run_skips_everything_and_never_loads_the_models(factory, settings) -> None:
    _complete(factory, settings, _models())
    before = [_get(factory, g.id).model_dump() for g in [_first(factory)]]

    def forbidden() -> AiModels:
        raise AssertionError("models must not load when nothing is pending")

    counts = backfill(settings, factory, LazyModels(forbidden))

    assert (counts.processed, counts.skipped, counts.failed) == (0, 1, 0)
    assert [_get(factory, g.id).model_dump() for g in [_first(factory)]] == before


def _first(factory) -> Garment:
    from sqlmodel import select

    with factory() as session:
        return session.exec(select(Garment)).first()  # type: ignore[return-value]


def test_user_set_fields_are_preserved_and_need_no_review(factory, settings) -> None:
    user = {"value": "denim", "confidence": 1.0, "source": "user"}
    garment_id = _add(
        factory,
        settings,
        category=GarmentCategory.bottom,
        material="denim",
        ai_confidence={"material": user},
        formality=5,
    )
    with factory() as session:
        session.add(
            AiCorrection(garment_id=garment_id, field="formality", ai_value=2, corrected_value=5)
        )
        session.commit()

    counts = backfill(settings, factory, LazyModels(lambda: _models(vector_for(category="top"))))

    garment = _get(factory, garment_id)
    assert counts.processed == 1
    assert garment.category == GarmentCategory.bottom and garment.subcategory is None
    assert garment.material == "denim" and garment.ai_confidence["material"] == user
    assert garment.formality == 5
    assert garment.pattern == GarmentPattern.solid  # the missing one is still filled
    assert garment.embedding is not None


def test_needs_review_is_raised_only_from_the_fields_it_wrote(factory, settings) -> None:
    ambiguous = vector_for(category=("top", "bottom"))
    with_user_category = _add(factory, settings, category=GarmentCategory.top)
    without = _add(factory, settings)

    models = make_models(ambiguous, margin_threshold=0.99)
    models.embedder.model_id = MODEL_ID  # type: ignore[attr-defined]

    backfill(settings, factory, LazyModels(lambda: models))

    assert _get(factory, with_user_category).needs_review is False  # category not written
    assert _get(factory, without).needs_review is True


def test_never_clears_needs_review(factory, settings) -> None:
    garment_id = _add(factory, settings, needs_review=True)

    backfill(settings, factory, LazyModels(lambda: _models()))

    assert _get(factory, garment_id).needs_review is True


def test_new_embedding_model_reembeds_without_rewriting_attributes(factory, settings) -> None:
    garment_id = _complete(factory, settings, _models(vector_for(category="shoes")))
    old = _get(factory, garment_id)
    assert old.category == GarmentCategory.shoes
    newer = _models(vector_for(category="top"))  # the new model would say "top"
    with factory() as session:
        row = session.get(Garment, garment_id)
        assert row is not None
        row.embedding_model = "other/model@old"
        session.add(row)
        session.commit()

    counts = backfill(settings, factory, LazyModels(lambda: newer))

    garment = _get(factory, garment_id)
    assert counts.processed == 1
    assert garment.embedding_model == MODEL_ID
    assert garment.embedding == newer.embedder.vector.astype(np.float32).tobytes()  # type: ignore[attr-defined]
    assert garment.category == GarmentCategory.shoes  # attributes are step 6's job
    assert garment.ai_confidence == old.ai_confidence


@pytest.mark.parametrize("state", [JobStatus.pending, JobStatus.claimed, JobStatus.running])
def test_skips_garments_with_an_open_job(factory, settings, state) -> None:
    garment_id = _add(factory, settings)
    with factory() as session:
        session.add(Job(garment_id=garment_id, status=state))
        session.commit()

    counts = backfill(settings, factory, LazyModels(lambda: _models()))

    assert (counts.processed, counts.skipped) == (0, 1)
    assert _get(factory, garment_id).embedding is None


def test_a_failing_garment_is_counted_and_the_rest_continue(factory, settings) -> None:
    bad = _add(factory, settings, image=False)
    good = _add(factory, settings)

    counts = backfill(settings, factory, LazyModels(lambda: _models()))

    assert (counts.processed, counts.failed) == (1, 1)
    assert counts.failures[0].startswith(bad)
    assert _get(factory, bad).embedding is None
    assert _get(factory, good).embedding is not None


def test_embedder_pinned_to_another_model_aborts(factory, settings) -> None:
    _add(factory, settings)

    with pytest.raises(RuntimeError, match="settings pin"):
        backfill(settings, factory, LazyModels(lambda: make_models()))  # fake id != settings
