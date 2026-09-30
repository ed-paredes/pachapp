"""Garment upload endpoint (ING-REQ-001..003)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status
from sqlmodel import Session

from api.deps import get_session, get_settings_dep
from api.errors import IMAGE_TOO_LARGE, INVALID_IMAGE, AppError, ErrorResponse
from api.schemas import GarmentCreated
from shared import storage
from shared.enums import GarmentStatus, JobStatus
from shared.imaging import ImageTooLargeError, InvalidImageError, decode_image, encode_jpeg
from shared.models import Garment, Job
from shared.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["garments"])

# R3-002: hard byte cap on an upload (default 25 MiB, tunable constant; not a
# setting). The client already resizes to `upload_max_px`, so real uploads are
# far below this; it only bounds memory for hostile or broken clients.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024


def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in chunks, stopping as soon as `max_bytes` is exceeded."""
    chunks: list[bytes] = []
    total = 0
    while chunk := file.file.read(_READ_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                IMAGE_TOO_LARGE,
                f"El archivo es demasiado grande (máximo {max_bytes // (1024 * 1024)} MiB).",
                400,
                {"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/garments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GarmentCreated,
    responses={400: {"model": ErrorResponse}},
)
def upload_garment(
    file: UploadFile,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> GarmentCreated:
    """Persist the EXIF-corrected original, then create garment + job in one
    transaction (ING-REQ-001/003). Heavy processing is left to the worker.

    A plain `def`: FastAPI runs it in the threadpool, so the blocking Pillow,
    file and SQLAlchemy work never stalls the event loop (R3-001)."""
    assert settings.images_root is not None
    data = _read_capped(file, MAX_UPLOAD_BYTES)
    max_long_side = settings.upload_max_px * 2
    try:
        image = decode_image(data, max_long_side=max_long_side)
    except ImageTooLargeError as exc:
        raise AppError(
            IMAGE_TOO_LARGE,
            f"La imagen es demasiado grande (máximo {max_long_side}px en el lado largo).",
            400,
            {"max_long_side": max_long_side},
        ) from exc
    except InvalidImageError as exc:
        raise AppError(INVALID_IMAGE, "El archivo no es una imagen válida.", 400) from exc

    garment = Garment(img_original="", status=GarmentStatus.active)
    garment.img_original = storage.original_path(garment.id)
    job = Job(garment_id=garment.id, status=JobStatus.pending)

    storage.write_atomic(settings.images_root, garment.img_original, encode_jpeg(image))
    try:
        session.add(garment)
        session.add(job)
        session.commit()
    except BaseException:
        session.rollback()
        try:
            storage.delete_file(settings.images_root, garment.img_original)
        except OSError:
            logger.exception("could not remove orphan original %s", garment.img_original)
        raise
    return GarmentCreated(garment_id=garment.id, job_id=job.id)
