"""`ai_attributes` step (08-local-vision.md step 4, VIS-REQ-013..019) with fake
models: attribute + `ai_confidence` writing, the `needs_review` rules, user-owned
fields, idempotency and the shared per-process model holder. Offline."""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from ai_fakes import FakeImageEmbedder, make_models, vector_for
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from shared.db import create_db_engine, create_session_factory
from shared.enums import ConfidenceSource, GarmentCategory, GarmentPattern, JobStatus
from shared.models import AiCorrection, Garment, Job, Setting
from shared.settings import Settings
from worker.ai import AiModels, LazyModels
from worker.claim import claim_next_job
from worker.runner import StepContext, default_steps, run_job
from worker.steps.ai_attributes import make_ai_attributes_step


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        thumb_px=32,
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _add_garment(factory, **fields) -> str:
    with factory() as session:
        garment = Garment(img_original="", **fields)
        garment.img_original = f"original/{garment.id}.jpg"
        session.add(garment)
        session.commit()
        return garment.id


def _get(factory, garment_id: str) -> Garment:
    with factory() as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment


def _run_step(factory, settings, models: AiModels, garment_id: str, **data) -> StepContext:
    ctx = StepContext(
        job_id="j", garment_id=garment_id, settings=settings, session_factory=factory, data=data
    )
    make_ai_attributes_step(LazyModels(lambda: models))(ctx)
    return ctx


def _set_threshold(factory, value: float) -> None:
    with factory() as session:
        session.add(Setting(id=1, needs_review_threshold=value))
        session.commit()


IMG = Image.new("RGB", (8, 8), (10, 20, 30))


def test_writes_attributes_and_confidence_with_zero_shot_source(factory, settings) -> None:
    garment_id = _add_garment(factory)
    vec = vector_for(category="outerwear", pattern="striped", material="lana", formality=4)

    _run_step(factory, settings, make_models(vec), garment_id, image=IMG)

    garment = _get(factory, garment_id)
    assert garment.category == GarmentCategory.outerwear
    assert garment.pattern == GarmentPattern.striped
    assert garment.material == "lana"
    assert garment.formality == 4
    assert garment.subcategory
    assert isinstance(garment.style_tags, list) and len(garment.style_tags) <= 3
    assert set(garment.ai_confidence) == {
        "category",
        "subcategory",
        "pattern",
        "material",
        "formality",
        "style_tags",
    }
    for name, entry in garment.ai_confidence.items():
        assert set(entry) == {"value", "confidence", "source"}, name
        assert entry["source"] == ConfidenceSource.zero_shot.value
        assert 0 <= entry["confidence"] <= 1
    assert garment.ai_confidence["category"]["value"] == "outerwear"
    assert garment.ai_confidence["formality"]["value"] == 4
    assert garment.needs_review is False


def test_embeds_the_cutout_once_and_shares_the_vector(factory, settings) -> None:
    garment_id = _add_garment(factory)
    models = make_models()
    cutout = Image.new("RGBA", (40, 20), (1, 2, 3, 255))

    ctx = _run_step(factory, settings, models, garment_id, image=IMG, cutout=cutout)

    assert models.embedder.images == [cutout]  # type: ignore[attr-defined]
    np.testing.assert_array_equal(ctx.data["embedding"], models.embedder.vector)  # type: ignore[attr-defined]


def test_falls_back_to_the_preprocessed_image_without_a_cutout(factory, settings) -> None:
    garment_id = _add_garment(factory)
    models = make_models()

    _run_step(factory, settings, models, garment_id, image=IMG)

    assert models.embedder.images == [IMG]  # type: ignore[attr-defined]


def test_loads_the_stored_image_when_the_context_has_none(factory, settings) -> None:
    assert settings.images_root is not None
    garment_id = _add_garment(factory)
    path = settings.images_root / f"original/{garment_id}.jpg"
    path.parent.mkdir(parents=True)
    buffer = io.BytesIO()
    Image.new("RGB", (12, 6)).save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())
    models = make_models()

    _run_step(factory, settings, models, garment_id)

    assert models.embedder.images[0].size == (12, 6)  # type: ignore[attr-defined]


# --- needs_review (VIS-REQ-016) -----------------------------------------


def test_low_top1_on_category_sets_needs_review(factory, settings) -> None:
    garment_id = _add_garment(factory)
    _set_threshold(factory, 0.99)  # read from `setting`, not the classifier default

    _run_step(
        factory,
        settings,
        make_models(vector_for(category=("top", "bottom"))),
        garment_id,
        image=IMG,
    )

    assert _get(factory, garment_id).needs_review is True


def test_small_margin_on_category_sets_needs_review_even_with_high_top1(factory, settings) -> None:
    garment_id = _add_garment(factory)
    _set_threshold(factory, 0.5)
    models = make_models(vector_for(category=("top", "bottom")), margin_threshold=0.99)

    _run_step(factory, settings, models, garment_id, image=IMG)

    garment = _get(factory, garment_id)
    assert garment.ai_confidence["category"]["confidence"] >= 0.5  # top-1 alone would pass
    assert garment.needs_review is True


class _FlaggingClassifier:
    """Real classification, but reporting `flagged` as the low-confidence attributes
    (random synthetic vectors cannot be tuned to a precise pattern tie; the rule
    itself is covered in test_ml_zero_shot.py)."""

    def __init__(self, inner, flagged: list[str]) -> None:
        self.inner = inner
        self.flagged = flagged

    def classify(self, img_emb, *, needs_review_threshold=None):
        result = self.inner.classify(img_emb, needs_review_threshold=needs_review_threshold)
        return replace(result, low_confidence=self.flagged)


def test_low_pattern_sets_needs_review(factory, settings) -> None:
    garment_id = _add_garment(factory)
    models = make_models()
    models.classifier = _FlaggingClassifier(models.classifier, ["pattern"])

    _run_step(factory, settings, models, garment_id, image=IMG)

    assert _get(factory, garment_id).needs_review is True


def test_low_material_or_formality_alone_does_not_set_needs_review(factory, settings) -> None:
    garment_id = _add_garment(factory)
    _set_threshold(factory, 0.97)
    vec = vector_for(material=("lana", "denim"), weights={"category": 4, "pattern": 4})
    models = make_models(vec)
    low = models.classifier.classify(vec, needs_review_threshold=0.97).low_confidence
    assert "material" in low and "formality" in low  # the fixture really is uncertain there

    _run_step(factory, settings, models, garment_id, image=IMG)

    assert _get(factory, garment_id).needs_review is False


def test_never_clears_needs_review_set_by_another_step(factory, settings) -> None:
    garment_id = _add_garment(factory, needs_review=True)

    _run_step(factory, settings, make_models(), garment_id, image=IMG)  # confident result

    assert _get(factory, garment_id).needs_review is True


# --- user-owned fields ---------------------------------------------------


def test_user_set_fields_survive_in_every_ownership_form(factory, settings) -> None:
    user = {"value": "denim", "confidence": 1.0, "source": "user"}
    garment_id = _add_garment(
        factory,
        category=GarmentCategory.bottom,  # typed by hand: column set, no ai_confidence entry
        material="denim",
        ai_confidence={"material": user},
        formality=5,  # corrected: ai_correction row, entry gone from ai_confidence
    )
    with factory() as session:
        session.add(
            AiCorrection(garment_id=garment_id, field="formality", ai_value=2, corrected_value=5)
        )
        session.commit()

    _run_step(
        factory,
        settings,
        make_models(vector_for(category="top", formality=2)),
        garment_id,
        image=IMG,
    )

    garment = _get(factory, garment_id)
    assert garment.category == GarmentCategory.bottom
    assert garment.material == "denim" and garment.ai_confidence["material"] == user
    assert garment.formality == 5 and "formality" not in garment.ai_confidence
    assert "category" not in garment.ai_confidence
    # Subcategory is not attached to a category this run did not write.
    assert garment.subcategory is None
    assert garment.pattern == GarmentPattern.solid  # untouched fields still filled
    assert garment.ai_confidence["pattern"]["source"] == "zero_shot"


def test_user_owned_low_confidence_field_does_not_raise_needs_review(factory, settings) -> None:
    garment_id = _add_garment(factory, category=GarmentCategory.bottom)
    _set_threshold(factory, 0.99)
    vec = vector_for(category=("top", "bottom"), weights={"pattern": 100})

    _run_step(factory, settings, make_models(vec), garment_id, image=IMG)

    assert _get(factory, garment_id).needs_review is False


# --- idempotency, retries, model loading ---------------------------------


def _snapshot(garment: Garment) -> dict:
    data = garment.model_dump()
    data.pop("updated_at")
    return data


def test_rerunning_the_step_gives_the_same_result(factory, settings) -> None:
    garment_id = _add_garment(factory)
    models = make_models(vector_for(category="shoes", pattern="textured"))

    _run_step(factory, settings, models, garment_id, image=IMG)
    first = _snapshot(_get(factory, garment_id))
    _run_step(factory, settings, models, garment_id, image=IMG)

    assert _snapshot(_get(factory, garment_id)) == first


def _queue_job(factory, settings, garment_id: str) -> None:
    assert settings.images_root is not None
    path = settings.images_root / f"original/{garment_id}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    Image.new("RGB", (30, 40), (120, 120, 120)).save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())
    with factory() as session:
        session.add(Job(garment_id=garment_id))
        session.commit()


class _FakeRemover:
    def remove(self, img: Image.Image) -> Image.Image:
        return Image.new("RGBA", (40, 20), (20, 30, 80, 255))


def _run_job(factory, settings, steps) -> JobStatus:
    with factory() as session:
        claimed = claim_next_job(session, "w-test")
    assert claimed is not None
    return run_job(claimed, steps, settings, factory)


def _steps(settings, models_factory):
    return default_steps(settings, remover_factory=_FakeRemover, models_factory=models_factory)


def test_pipeline_fills_attributes_and_builds_the_models_once(factory, settings) -> None:
    ids = [_add_garment(factory), _add_garment(factory)]
    for garment_id in ids:
        _queue_job(factory, settings, garment_id)
    builds: list[int] = []

    def build() -> AiModels:
        builds.append(1)
        return make_models(vector_for(category="one_piece"))

    steps = _steps(settings, build)  # one worker process: one step registry
    assert _run_job(factory, settings, steps) == JobStatus.done
    assert _run_job(factory, settings, steps) == JobStatus.done

    assert len(builds) == 1
    for garment_id in ids:
        assert _get(factory, garment_id).category == GarmentCategory.one_piece


def test_model_error_is_retried_once_then_fails_the_job(factory, settings) -> None:
    garment_id = _add_garment(factory)
    _queue_job(factory, settings, garment_id)
    models = make_models()
    assert isinstance(models.embedder, FakeImageEmbedder)
    models.embedder.error = RuntimeError("cuda out of memory")

    assert _run_job(factory, settings, _steps(settings, lambda: models)) == JobStatus.failed

    assert len(models.embedder.images) == 2  # first attempt + one retry
    assert _get(factory, garment_id).category is None
