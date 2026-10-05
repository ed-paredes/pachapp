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

Garment-only cutout (U5c, owner decision 2026-10-05). When `ml_garment_parse` is on and
the remover can return the uncropped matte (`MatteRemover`), the FASHN human parser runs
right after the matte, serially on the same job thread (VIS-REQ-025):

- no person in the photo (`person_present`) -> today's BiRefNet cutout, unchanged;
- a person -> `cut_garment_by_rule` with the garment's category read from the database
  (set by a previous run or by the user; a fresh upload has none, because `ai_attributes`
  classifies *after* this step, so the largest clothing region is used);
- garment mask too small, or the parser failing -> the matte is kept and the garment is
  flagged for review (`ctx.data["cutout_review"]`, turned into `needs_review` by
  `consolidate`).

The colour step then samples `ctx.data["color_image"]`, the cutout eroded by
`COLOR_ERODE_PX`, so edge pixels with skin or background tones do not count. The parser is
built lazily on the first job and stays resident like BiRefNet and SigLIP (~130 MB of fp16
weights, ~320 MB torch peak).
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from PIL import Image

from ml.background import (
    BackgroundRemover,
    EmptyCutoutError,
    MatteRemover,
    crop_to_foreground,
)
from ml.garment_parse import (
    GarmentParser,
    cut_garment_by_rule,
    erode_alpha,
    person_present,
)
from shared import storage
from shared.imaging import make_thumbnail
from shared.models import Garment
from shared.settings import Settings
from worker.runner import PermanentStepError, RetryableStepError, Step, StepContext

logger = logging.getLogger(__name__)

RemoverFactory = Callable[[], BackgroundRemover]
ParserFactory = Callable[[], GarmentParser]

REVIEW_MASK_TOO_SMALL = "garment_mask_too_small"
REVIEW_PARSER_FAILED = "garment_parser_failed"
REVIEW_ITEM_KEPT = "garment_item_kept"

MSG_CUTOUT = "No se pudo recortar la prenda. Inténtalo de nuevo."


def production_remover_factory(settings: Settings) -> RemoverFactory:
    """Factory of the real BiRefNet remover; `ml` is imported only when called."""

    def build() -> BackgroundRemover:
        from ml.background import BiRefNetRemover

        return BiRefNetRemover(settings)

    return build


def production_parser_factory(settings: Settings) -> ParserFactory:
    """Factory of the real FASHN parser; torch/transformers are imported only when called."""

    def build() -> GarmentParser:
        from ml.device import resolve_device
        from ml.garment_parse import build_parser

        return build_parser("fashn", settings, resolve_device(settings.ml_device))

    return build


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _garment_category(ctx: StepContext) -> str | None:
    with ctx.session_factory() as session:
        garment = session.get(Garment, ctx.garment_id)
        return str(garment.category) if garment is not None and garment.category else None


def _parse_cutout(
    ctx: StepContext, parser: GarmentParser, image: Image.Image, matte: Image.Image
) -> Image.Image | None:
    """Garment-only cutout from the full-size `matte`, or None to keep the plain matte
    cutout (no person, or the parse could not be used; `cutout_review` says why)."""
    if image.size != matte.size:
        logger.warning(
            "job %s: matte %s != image %s, parse skipped", ctx.job_id, matte.size, image.size
        )
        return None
    result = parser.parse(image.convert("RGB"))
    if not person_present(result):
        logger.info("job %s: no person in the photo, keeping the BiRefNet cutout", ctx.job_id)
        return None
    cut = cut_garment_by_rule(matte, result, _garment_category(ctx))
    if cut.fallback:
        logger.warning(
            "job %s: garment mask too small (%.2f%%), keeping the matte for review",
            ctx.job_id,
            100 * cut.garment_ratio,
        )
        ctx.data["cutout_review"] = REVIEW_MASK_TOO_SMALL
        return None
    if cut.review:
        logger.warning("job %s: an unselected worn/carried item was kept for review", ctx.job_id)
        ctx.data["cutout_review"] = REVIEW_ITEM_KEPT
    return crop_to_foreground(cut.rgba)


def make_cutout_step(
    remover_factory: RemoverFactory, parser_factory: ParserFactory | None = None
) -> Step:
    """Build the step; the remover (and the parser, when given and enabled by
    `ml_garment_parse`) is created on first use and reused."""
    remover: BackgroundRemover | None = None
    parser: GarmentParser | None = None

    def cutout_step(ctx: StepContext) -> None:
        nonlocal remover, parser
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
            if (
                parser_factory is not None
                and ctx.settings.ml_garment_parse
                and isinstance(remover, MatteRemover)
            ):
                matte = remover.matte(image)
                cutout = crop_to_foreground(matte)
                try:
                    if parser is None:
                        parser = parser_factory()
                    parsed = _parse_cutout(ctx, parser, image, matte)
                except Exception as exc:  # noqa: BLE001 - degrade to the plain matte, flagged
                    logger.warning("job %s: garment parsing failed: %s", ctx.job_id, exc)
                    ctx.data["cutout_review"] = REVIEW_PARSER_FAILED
                    parsed = None
                if parsed is not None:
                    cutout = parsed
                    ctx.data["color_image"] = erode_alpha(parsed)
            else:
                cutout = remover.remove(image)
            cutout = cutout.convert("RGBA")
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
