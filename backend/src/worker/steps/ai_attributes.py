"""`ai_attributes` step (08-local-vision.md step 4, VIS-REQ-013..019, 03 worker steps).

Embeds the cutout (the preprocessed image when there is none) once, keeps the
vector in `ctx.data["embedding"]` for the `embedding` step (no second inference)
and runs the zero-shot classifier (alpha = 1, `source="zero_shot"`). Writes
category, subcategory, pattern, material, formality and style_tags with their
`ai_confidence` entries, skipping every user-owned field (`worker.ai`), and
raises `needs_review` only from low-confidence `category`/`pattern`
(VIS-REQ-016). The step is idempotent: re-running it rewrites the same values.

Models come from a `LazyModels` holder, built on the first job and shared with
the `embedding` step; tests inject fakes.
"""

from __future__ import annotations

import logging

import numpy as np

from shared.models import Garment
from worker.ai import (
    AI_FIELDS,
    AiModels,
    LazyModels,
    apply_classification,
    load_garment_image,
    needs_review_threshold,
    user_owned_fields,
)
from worker.runner import PermanentStepError, RetryableStepError, Step, StepContext

logger = logging.getLogger(__name__)

MSG_AI = "No se pudo analizar la prenda. Inténtalo de nuevo."


def load_models(models: LazyModels) -> AiModels:
    """The process models, built on first use; a failed build (download, CUDA
    init, out of memory) is a transient step error with the user message."""
    try:
        return models.get()
    except Exception as exc:  # noqa: BLE001 - model load errors are transient
        raise RetryableStepError(f"model load failed: {exc}", user_message=MSG_AI) from exc


def image_embedding(ctx: StepContext, models: AiModels) -> np.ndarray:
    """The job's image embedding: computed once, then reused from `ctx.data`.
    Source image: cutout, else the preprocessed image, else the stored files
    (a job resumed without the in-memory images)."""
    cached = ctx.data.get("embedding")
    if cached is not None:
        return cached
    image = ctx.data.get("cutout") or ctx.data.get("image")
    try:
        if image is None:
            with ctx.session_factory() as session:
                garment = session.get(Garment, ctx.garment_id)
                if garment is None:
                    raise PermanentStepError(
                        f"garment {ctx.garment_id} disappeared", user_message=MSG_AI
                    )
                image = load_garment_image(ctx.settings, garment)
        vector = models.embedder.embed_image(image)
    except PermanentStepError:
        raise
    except Exception as exc:  # noqa: BLE001 - model and I/O errors are transient
        raise RetryableStepError(f"image embedding failed: {exc}", user_message=MSG_AI) from exc
    ctx.data["embedding"] = vector
    return vector


def make_ai_attributes_step(models: LazyModels) -> Step:
    def ai_attributes_step(ctx: StepContext) -> None:
        loaded = load_models(models)
        vector = image_embedding(ctx, loaded)
        with ctx.session_factory() as session:
            threshold = needs_review_threshold(session)
        try:
            result = loaded.classifier.classify(vector, needs_review_threshold=threshold)
        except Exception as exc:  # noqa: BLE001
            raise RetryableStepError(f"classification failed: {exc}", user_message=MSG_AI) from exc

        with ctx.session_factory() as session:
            garment = session.get(Garment, ctx.garment_id)
            if garment is None:
                raise PermanentStepError(
                    f"garment {ctx.garment_id} disappeared", user_message=MSG_AI
                )
            owned = user_owned_fields(session, garment)
            written = apply_classification(garment, result, set(AI_FIELDS) - owned)
            if written:
                session.add(garment)
                session.commit()
            logger.info(
                "job %s: ai_attributes wrote %s (user-owned: %s)",
                ctx.job_id,
                written,
                sorted(owned),
            )

    return ai_attributes_step
