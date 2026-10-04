"""Wear log: what was worn each day, with derived garment counters
(FBH-REQ-007..010, DAT-REQ-008, D7)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api import clock
from api.deps import get_session
from api.errors import (
    INVALID_WEAR_DATE,
    OUTFIT_NOT_FOUND,
    WEAR_LOG_CONFLICT,
    WEAR_LOG_NOT_FOUND,
    WEAR_LOG_WRITE_FAILED,
    AppError,
    ErrorResponse,
)
from api.schemas_outfits import WearLogCreate, WearLogEntry, WearLogReplace
from shared.models import Garment, Outfit, OutfitItem, WearLog

router = APIRouter(tags=["wear-log"])


def _entry(log: WearLog) -> WearLogEntry:
    return WearLogEntry(
        id=log.id, date=log.date, outfit_id=log.outfit_id, created_at=log.created_at
    )


def _require_outfit(session: Session, outfit_id: str) -> None:
    if session.get(Outfit, outfit_id) is None:
        raise AppError(OUTFIT_NOT_FOUND, "El outfit no existe.", 404, {"outfit_id": outfit_id})


def _require_not_future(day: dt.date) -> None:
    if day > clock.local_today():
        raise AppError(
            INVALID_WEAR_DATE,
            "No puedes registrar un outfit en una fecha futura.",
            400,
            {"date": day.isoformat()},
        )


def _log_for(session: Session, day: dt.date) -> WearLog | None:
    return session.exec(select(WearLog).where(WearLog.date == day)).first()


def _require_log(session: Session, day: dt.date) -> WearLog:
    log = _log_for(session, day)
    if log is None:
        raise AppError(
            WEAR_LOG_NOT_FOUND,
            "No hay ningún outfit registrado para este día.",
            404,
            {"date": day.isoformat()},
        )
    return log


def _conflict(log: WearLog) -> AppError:
    return AppError(
        WEAR_LOG_CONFLICT,
        "Ya registraste un outfit para este día.",
        409,
        {"date": log.date.isoformat(), "outfit_id": log.outfit_id, "wear_log_id": log.id},
    )


def _garment_ids(session: Session, *outfit_ids: str) -> set[str]:
    return set(
        session.exec(
            select(OutfitItem.garment_id).where(col(OutfitItem.outfit_id).in_(outfit_ids))
        ).all()
    )


def recompute_wear_stats(session: Session, garment_ids: set[str]) -> None:
    """FBH-REQ-010: `wear_count` is the number of wear-log rows whose outfit
    holds the garment, `last_worn_at` the latest such date. Derived from the
    table (never edited directly); runs in the caller's transaction."""
    if not garment_ids:
        return
    rows = session.exec(
        select(OutfitItem.garment_id, func.count(col(WearLog.id)), func.max(col(WearLog.date)))
        .join(WearLog, col(WearLog.outfit_id) == col(OutfitItem.outfit_id))
        .where(col(OutfitItem.garment_id).in_(garment_ids))
        .group_by(col(OutfitItem.garment_id))
    ).all()
    stats = {garment_id: (count, last) for garment_id, count, last in rows}
    for garment in session.exec(select(Garment).where(col(Garment.id).in_(garment_ids))):
        garment.wear_count, garment.last_worn_at = stats.get(garment.id, (0, None))
        session.add(garment)


@router.post(
    "/wear-log",
    response_model=WearLogEntry,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_wear_log(
    body: WearLogCreate, session: Annotated[Session, Depends(get_session)]
) -> WearLogEntry:
    """Log the outfit worn on `date` (default: today). `409` when that day is
    already logged: the client may then offer `PUT /wear-log/{date}`. `503
    WEAR_LOG_WRITE_FAILED` when the insert failed for another reason (nothing was
    logged, retrying is safe): it carries no `outfit_id`, so it is never a conflict."""
    outfit_id = str(body.outfit_id)
    day = body.date or clock.local_today()
    _require_not_future(day)
    _require_outfit(session, outfit_id)
    existing = _log_for(session, day)
    if existing is not None:
        raise _conflict(existing)
    log = WearLog(date=day, outfit_id=outfit_id)
    session.add(log)
    try:
        session.flush()
    except IntegrityError:  # lost a race with another request for the same day
        session.rollback()
        raced = _log_for(session, day)
        if raced is not None:
            raise _conflict(raced) from None
        # Not the day: another constraint failed (e.g. the outfit was deleted meanwhile).
        _require_outfit(session, outfit_id)
        raise AppError(
            WEAR_LOG_WRITE_FAILED,
            "No se pudo registrar el outfit. Inténtalo de nuevo.",
            503,
            {"date": day.isoformat()},
        ) from None
    recompute_wear_stats(session, _garment_ids(session, outfit_id))
    session.commit()
    return _entry(log)


@router.put(
    "/wear-log/{date}",
    response_model=WearLogEntry,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def replace_wear_log(
    date: dt.date, body: WearLogReplace, session: Annotated[Session, Depends(get_session)]
) -> WearLogEntry:
    """Replace the outfit of an already logged day; the counters of both the
    old and the new outfit's garments are recomputed in the same transaction."""
    _require_not_future(date)
    log = _require_log(session, date)
    new_id = str(body.outfit_id)
    _require_outfit(session, new_id)
    old_id = log.outfit_id
    log.outfit_id = new_id
    session.add(log)
    session.flush()
    recompute_wear_stats(session, _garment_ids(session, old_id, new_id))
    session.commit()
    return _entry(log)


@router.delete(
    "/wear-log/{date}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_wear_log(date: dt.date, session: Annotated[Session, Depends(get_session)]) -> Response:
    log = _require_log(session, date)
    affected = _garment_ids(session, log.outfit_id)
    session.delete(log)
    session.flush()
    recompute_wear_stats(session, affected)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
