"""Backfill of AI attributes and embeddings for existing garments
(08-local-vision.md step 4; the minimal subset of step 6's `reembed`).

    make backfill-ai            # uv run python -m worker.backfill

For every garment (active, laundry or archived) that has no embedding, an
embedding from another model (`embedding_model` != the pinned `id@revision`) or
missing auto attributes, it embeds the stored cutout (the original when there is
none) and fills what is missing with the same logic as the worker steps
(`worker.ai`): only attributes that are empty and not user-owned, `needs_review`
raised only from the fields it wrote (category/pattern, VIS-REQ-016), `status`,
user fields and existing values untouched. Re-running it is a no-op once
everything is filled. A model change re-embeds, but never rewrites attributes
(that is step 6's `reembed`).

Run it with the worker STOPPED: both would share the GPU (VIS-REQ-025). As a
cheap guard, garments with a pending/claimed/running job are skipped (the job
fills them), and each garment is re-read right before writing.

Images are decoded on a thread pool while the GPU embeds the previous one
(`ml.pipeline`); inference itself stays strictly serial.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, col, select

from ml.cache import configure_model_cache
from ml.pipeline import run_pipeline
from ml.zero_shot import ZeroShotResult
from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStatus
from shared.models import Garment, Job
from shared.settings import Settings, get_settings
from worker.ai import (
    AI_FIELDS,
    LazyModels,
    apply_classification,
    apply_embedding,
    load_garment_image,
    needs_review_threshold,
    production_models_factory,
    user_owned_fields,
)

logger = logging.getLogger(__name__)

_BUSY = (JobStatus.pending, JobStatus.claimed, JobStatus.running)


@dataclass
class Counts:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)


def _todo(session: Session, garment: Garment, model_id: str) -> tuple[set[str], bool]:
    """(attributes to fill, whether the embedding must be written)."""
    owned = user_owned_fields(session, garment)
    missing = {name for name in AI_FIELDS if getattr(garment, name) is None} - owned
    stale = garment.embedding is None or garment.embedding_model != model_id
    return missing, stale


def _pending_ids(session: Session, model_id: str, counts: Counts) -> list[str]:
    busy = set(session.exec(select(col(Job.garment_id)).where(col(Job.status).in_(_BUSY))).all())
    ids: list[str] = []
    for garment in session.exec(select(Garment).order_by(col(Garment.created_at))).all():
        missing, stale = _todo(session, garment, model_id)
        if not missing and not stale:
            counts.skipped += 1
        elif garment.id in busy:
            logger.info("garment %s has an open job, skipping", garment.id)
            counts.skipped += 1
        else:
            ids.append(garment.id)
    return ids


def backfill(settings: Settings, factory: sessionmaker[Session], models: LazyModels) -> Counts:
    counts = Counts()
    model_id = f"{settings.ml_embed_model}@{settings.ml_embed_revision}"
    with factory() as session:
        ids = _pending_ids(session, model_id, counts)
        threshold = needs_review_threshold(session)
        garments = {
            g.id: g for g in session.exec(select(Garment).where(col(Garment.id).in_(ids))).all()
        }
    if not ids:
        return counts
    loaded = models.get()
    if loaded.embedder.model_id != model_id:  # same `id@revision` string the registry builds
        raise RuntimeError(
            f"loaded embedder is {loaded.embedder.model_id!r}, settings pin {model_id!r}"
        )

    def prepare(garment_id: str) -> tuple[str, Image.Image]:
        return garment_id, load_garment_image(settings, garments[garment_id])

    def execute(item: tuple[str, Image.Image]) -> np.ndarray:
        return loaded.embedder.embed_image(item[1])

    def finish(
        item: tuple[str, Image.Image], vector: np.ndarray
    ) -> tuple[np.ndarray, ZeroShotResult]:
        return vector, loaded.classifier.classify(vector, needs_review_threshold=threshold)

    results: Iterator = run_pipeline(ids, prepare, execute, finish)
    for garment_id, outcome in zip(ids, results, strict=True):
        try:
            if isinstance(outcome, Exception):
                raise outcome
            vector, result = outcome
            _store(factory, garment_id, vector, result, loaded.embedder, model_id)
        except Exception as exc:  # noqa: BLE001 - one bad garment must not stop the run
            logger.error("garment %s failed: %s", garment_id, exc)
            counts.failed += 1
            counts.failures.append(f"{garment_id}: {exc}")
        else:
            counts.processed += 1
    return counts


def _store(factory, garment_id, vector, result, embedder, model_id) -> None:
    with factory() as session:
        garment = session.get(Garment, garment_id)
        if garment is None:  # deleted while the backfill ran
            return
        # Re-evaluated now: the user may have edited the garment meanwhile.
        missing, stale = _todo(session, garment, model_id)
        apply_classification(garment, result, missing)
        if stale:
            apply_embedding(garment, vector, embedder)
        session.add(garment)
        session.commit()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    assert settings.ml_cache_dir is not None
    configure_model_cache(settings.ml_cache_dir)
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    counts = backfill(settings, factory, LazyModels(production_models_factory(settings)))
    print(f"processed={counts.processed} skipped={counts.skipped} failed={counts.failed}")
    for line in counts.failures:
        print(f"  failed {line}", file=sys.stderr)
    return 1 if counts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
