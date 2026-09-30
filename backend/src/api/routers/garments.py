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


@router.post(
    "/garments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GarmentCreated,
    responses={400: {"model": ErrorResponse}},
)
async def upload_garment(
    file: UploadFile,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> GarmentCreated:
    """Persist the EXIF-corrected original, then create garment + job in one
    transaction (ING-REQ-001/003). Heavy processing is left to the worker."""
    assert settings.images_root is not None
    data = await file.read()
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
