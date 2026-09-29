"""`color` step (03-garment-ingestion.md, ING-REQ-010..014).

Extracts the palette from the opaque pixels of the cutout (`worker.colors`) and
stores `colors`, `is_neutral` and `color_confidence` in one short transaction.
`needs_review` is decided later, in `consolidate`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from PIL import Image

from shared import storage
from shared.models import Garment
from worker.colors import extract_colors
from worker.runner import PermanentStepError, RetryableStepError, StepContext

MSG_COLOR = "No se pudo analizar el color de la prenda. Inténtalo de nuevo."


def _load_cutout(ctx: StepContext) -> Image.Image:
    cutout = ctx.data.get("cutout")
    if cutout is not None:
        return cutout
    assert ctx.settings.images_root is not None
    with ctx.session_factory() as session:
        garment = session.get(Garment, ctx.garment_id)
        relative = garment.img_cutout if garment is not None else None
    if not relative:
        raise PermanentStepError("color ran before cutout", user_message=MSG_COLOR)
    try:
        with Image.open(storage.resolve_path(ctx.settings.images_root, relative)) as opened:
            return opened.convert("RGBA")
    except OSError as exc:
        raise RetryableStepError(
            f"could not read cutout {relative}: {exc}", user_message=MSG_COLOR
        ) from exc


def color_step(ctx: StepContext) -> None:
    result = extract_colors(_load_cutout(ctx))
    with ctx.session_factory() as session:
        garment = session.get(Garment, ctx.garment_id)
        if garment is None:
            raise PermanentStepError(
                f"garment {ctx.garment_id} disappeared", user_message=MSG_COLOR
            )
        garment.colors = result.colors.model_dump(mode="json")
        garment.is_neutral = result.is_neutral
        garment.color_confidence = result.confidence
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()
