"""`preprocess` step (03-garment-ingestion.md, ING-REQ-008/022).

Loads the stored original (EXIF already applied at upload, ING-REQ-003) and puts
an RGB copy in `ctx.data["image"]` for the following steps. A missing or
undecodable original is permanent (no retry can fix it); other I/O errors are
retryable once.
"""

from __future__ import annotations

from shared import storage
from shared.imaging import ImageTooLargeError, InvalidImageError, decode_image, to_rgb
from shared.models import Garment
from worker.runner import PermanentStepError, RetryableStepError, StepContext

MSG_UNREADABLE = "No se pudo leer la foto original. Súbela de nuevo."
MSG_IO = "No se pudo acceder a la foto. Inténtalo de nuevo."


def preprocess_step(ctx: StepContext) -> None:
    assert ctx.settings.images_root is not None
    with ctx.session_factory() as session:
        garment = session.get(Garment, ctx.garment_id)
        relative = garment.img_original if garment is not None else None
    if not relative:
        raise PermanentStepError(
            f"garment {ctx.garment_id} has no original", user_message=MSG_UNREADABLE
        )

    try:
        data = storage.resolve_path(ctx.settings.images_root, relative).read_bytes()
    except (FileNotFoundError, ValueError) as exc:
        raise PermanentStepError(
            f"original {relative} is missing or invalid: {exc}", user_message=MSG_UNREADABLE
        ) from exc
    except OSError as exc:
        raise RetryableStepError(f"could not read {relative}: {exc}", user_message=MSG_IO) from exc

    try:
        image = decode_image(data, max_long_side=ctx.settings.upload_max_px * 2)
    except (InvalidImageError, ImageTooLargeError) as exc:
        raise PermanentStepError(
            f"original {relative} is not decodable: {exc}", user_message=MSG_UNREADABLE
        ) from exc
    ctx.data["image"] = to_rgb(image)
