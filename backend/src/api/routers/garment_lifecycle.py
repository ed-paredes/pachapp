"""Garment lifecycle actions: archive, reactivate, retry, delete (API-REQ-010..012)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, col, delete, select

from api.deps import get_session, get_settings_dep
from api.errors import (
    GARMENT_HAS_HISTORY,
    GARMENT_PROCESSING,
    JOB_NOT_FAILED,
    AppError,
    ErrorResponse,
)
from api.routers.garments import garment_detail, get_garment_or_404
from api.schemas import GarmentDetail, JobRead
from shared import storage
from shared.enums import GarmentStatus, JobStatus
from shared.models import AiCorrection, Garment, Job, OutfitItem
from shared.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["garments"])


def _set_status(session: Session, garment: Garment, new_status: GarmentStatus) -> GarmentDetail:
    if garment.status != new_status:
        garment.status = new_status
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()
        session.refresh(garment)
    return garment_detail(session, garment)


@router.post(
    "/garments/{garment_id}/archive",
    response_model=GarmentDetail,
    responses={404: {"model": ErrorResponse}},
)
def archive_garment(
    garment_id: str, session: Annotated[Session, Depends(get_session)]
) -> GarmentDetail:
    """API-REQ-010: `status = archived` (idempotent)."""
    return _set_status(session, get_garment_or_404(session, garment_id), GarmentStatus.archived)


@router.post(
    "/garments/{garment_id}/reactivate",
    response_model=GarmentDetail,
    responses={404: {"model": ErrorResponse}},
)
def reactivate_garment(
    garment_id: str, session: Annotated[Session, Depends(get_session)]
) -> GarmentDetail:
    """API-REQ-010: `status = active` (idempotent)."""
    return _set_status(session, get_garment_or_404(session, garment_id), GarmentStatus.active)


def _latest_job(session: Session, garment_id: str) -> Job | None:
    return session.exec(
        select(Job)
        .where(col(Job.garment_id) == garment_id)
        .order_by(col(Job.created_at).desc(), col(Job.id).desc())
        .limit(1)
    ).first()


@router.post(
    "/garments/{garment_id}/retry",
    response_model=JobRead,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def retry_garment(garment_id: str, session: Annotated[Session, Depends(get_session)]) -> JobRead:
    """API-REQ-011: only a `failed` latest job can be retried; it goes back to
    `pending` with a fresh retry budget so the worker re-runs the whole pipeline
    (user-corrected colours are kept by the worker's color step)."""
    garment = get_garment_or_404(session, garment_id)
    job = _latest_job(session, garment.id)
    if job is None or job.status != JobStatus.failed:
        raise AppError(
            JOB_NOT_FAILED,
            "Solo se puede reintentar una prenda cuyo procesamiento falló.",
            409,
            {"garment_id": garment.id},
        )
    job.status = JobStatus.pending
    job.attempts = 0
    job.error = None
    job.step = None
    job.progress = 0
    job.claimed_by = None
    job.claimed_at = None
    job.started_at = None
    job.finished_at = None
    session.add(job)
    session.commit()
    session.refresh(job)
    return JobRead(
        status=job.status,
        step=job.step,
        progress=job.progress,
        error=job.error,
        result=job.result,
    )


def _processing_conflict(garment_id: str) -> AppError:
    return AppError(
        GARMENT_PROCESSING,
        "La prenda se está procesando; espera a que termine para eliminarla.",
        409,
        {"garment_id": garment_id},
    )


def _drop_pending_jobs(session: Session, garment_id: str) -> None:
    """First statement of the delete transaction: as a write it takes SQLite's
    write lock, so from here on the worker cannot claim a job of this garment."""
    session.exec(
        delete(Job).where(  # type: ignore[call-overload]
            col(Job.garment_id) == garment_id, col(Job.status) == JobStatus.pending
        )
    )


def _delete_rows_atomically(session: Session, garment: Garment) -> None:
    """One write transaction: drop pending jobs (taking the write lock), re-check
    that none is claimed/running, then delete the rows. A job the worker claimed
    before the lock, or a busy/locked database, is `GARMENT_PROCESSING` (409) and
    nothing is deleted."""
    garment_id = garment.id
    try:
        _drop_pending_jobs(session, garment_id)
        processing = session.exec(
            select(col(Job.id))
            .where(
                col(Job.garment_id) == garment_id,
                col(Job.status).in_([JobStatus.claimed, JobStatus.running]),
            )
            .limit(1)
        ).first()
        if processing is not None:
            session.rollback()
            raise _processing_conflict(garment_id)
        session.exec(delete(AiCorrection).where(col(AiCorrection.garment_id) == garment_id))  # type: ignore[call-overload]
        session.exec(delete(Job).where(col(Job.garment_id) == garment_id))  # type: ignore[call-overload]
        session.delete(garment)
        session.commit()
    except OperationalError as exc:
        session.rollback()
        logger.warning("delete of garment %s hit a busy database: %s", garment_id, exc)
        raise _processing_conflict(garment_id) from exc


@router.delete(
    "/garments/{garment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def delete_garment(
    garment_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Response:
    """API-REQ-012: permanent delete of an accidental upload. Refused with 409
    when the garment is part of an outfit (`GARMENT_HAS_HISTORY`, archive
    instead) or while the worker is processing it (`GARMENT_PROCESSING`).
    Rows go in one transaction; image files are removed best-effort afterwards."""
    assert settings.images_root is not None
    garment = get_garment_or_404(session, garment_id)
    in_history = session.exec(
        select(col(OutfitItem.id)).where(col(OutfitItem.garment_id) == garment.id).limit(1)
    ).first()
    if in_history is not None:
        raise AppError(
            GARMENT_HAS_HISTORY,
            "La prenda forma parte de tu historial de outfits; archívala en su lugar.",
            409,
            {"garment_id": garment.id},
        )
    files = [garment.img_original, garment.img_cutout, garment.img_thumb]
    _delete_rows_atomically(session, garment)

    for relative in files:
        if not relative:
            continue
        try:
            storage.delete_file(settings.images_root, relative)
        except (OSError, ValueError):
            logger.warning("could not delete image %s of garment %s", relative, garment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
