"""`cutout` step (03-garment-ingestion.md, ING-REQ-008/009/022, ING-SCN-005).

Removes the background with an injected `BackgroundRemover`, writes
`cutout/{id}.png` (RGBA) and `thumb/{id}.webp` (long side `thumb_px`, made from
the cutout) atomically, then stores both relative paths in one short transaction.

Soft failure (ING-SCN-005): when the remover raises `EmptyCutoutError`, the full
preprocessed image becomes the cutout (opaque PNG), the thumbnail is still made,
`ctx.data["cutout_soft_failure"]` is set and the pipeline continues; `consolidate`
turns that into `needs_review`. Any other remover error is retryable (ING-REQ-022).

The remover comes from a factory so tests inject a fake and production builds
`ml.background.BiRefNetRemover` lazily, on the first job, never at import.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from PIL import Image

from ml.background import BackgroundRemover, EmptyCutoutError
from shared import storage
from shared.imaging import make_thumbnail
from shared.models import Garment
from shared.settings import Settings
from worker.runner import PermanentStepError, RetryableStepError, Step, StepContext

logger = logging.getLogger(__name__)

RemoverFactory = Callable[[], BackgroundRemover]

MSG_CUTOUT = "No se pudo recortar la prenda. Inténtalo de nuevo."


def production_remover_factory(settings: Settings) -> RemoverFactory:
    """Factory of the real BiRefNet remover; `ml` is imported only when called."""

    def build() -> BackgroundRemover:
        from ml.background import BiRefNetRemover

        return BiRefNetRemover(settings)

    return build


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_cutout_step(remover_factory: RemoverFactory) -> Step:
    """Build the step; the remover is created on first use and reused."""
    remover: BackgroundRemover | None = None

    def cutout_step(ctx: StepContext) -> None:
        nonlocal remover
        assert ctx.settings.images_root is not None
        image = ctx.data.get("image")
        if image is None:
            raise PermanentStepError(
                "cutout ran without a preprocessed image", user_message=MSG_CUTOUT
            )

        soft_failure = False
        try:
            if remover is None:
                remover = remover_factory()
            cutout = remover.remove(image).convert("RGBA")
        except EmptyCutoutError as exc:
            logger.warning("job %s: empty cutout mask, using the full image: %s", ctx.job_id, exc)
            cutout = image.convert("RGBA")  # fully opaque
            soft_failure = True
        except Exception as exc:  # noqa: BLE001 - model errors are transient (ING-REQ-022)
            raise RetryableStepError(
                f"background removal failed: {exc}", user_message=MSG_CUTOUT
            ) from exc

        cutout_rel = storage.cutout_path(ctx.garment_id)
        thumb_rel = storage.thumb_path(ctx.garment_id)
        try:
            storage.write_atomic(ctx.settings.images_root, cutout_rel, _png_bytes(cutout))
            storage.write_atomic(
                ctx.settings.images_root, thumb_rel, make_thumbnail(cutout, ctx.settings.thumb_px)
            )
        except OSError as exc:
            raise RetryableStepError(
                f"could not write cutout files: {exc}", user_message=MSG_CUTOUT
            ) from exc

        with ctx.session_factory() as session:
            garment = session.get(Garment, ctx.garment_id)
            if garment is None:
                raise PermanentStepError(
                    f"garment {ctx.garment_id} disappeared", user_message=MSG_CUTOUT
                )
            garment.img_cutout = cutout_rel
            garment.img_thumb = thumb_rel
            garment.updated_at = datetime.now(UTC)
            session.add(garment)
            session.commit()

        ctx.data["cutout"] = cutout
        ctx.data["cutout_soft_failure"] = soft_failure

    return cutout_step
