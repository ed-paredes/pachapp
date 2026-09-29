"""Garment upload endpoint (ING-REQ-001..003)."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, UploadFile, status
from sqlalchemy import ColumnElement, TextClause, func, text
from sqlmodel import Session, col, select

from api.deps import get_session, get_settings_dep
from api.errors import GARMENT_NOT_FOUND, IMAGE_TOO_LARGE, INVALID_IMAGE, AppError, ErrorResponse
from api.schemas import (
    GarmentCreated,
    GarmentDetail,
    GarmentList,
    GarmentListItem,
    JobSummary,
)
from shared import storage
from shared.enums import GarmentCategory, GarmentStatus, JobStatus, Season
from shared.imaging import ImageTooLargeError, InvalidImageError, decode_image, encode_jpeg
from shared.models import Garment, Job, OutfitItem
from shared.schemas import AiConfidence, ColorEntry, Colors
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


# --- A6: reads (API-REQ-003..005) ---

SortField = Literal["created_at", "last_worn_at", "wear_count"]
SortOrder = Literal["asc", "desc"]


def _json_contains(column: str, key: str | None, param: str, value: str) -> TextClause:
    """`EXISTS` over `json_each(<column>)`: a JSON-array element (or one of its
    keys) equals `value`. Done in SQL so `total` and pagination stay exact."""
    target = f"json_extract(json_each.value, '$.{key}')" if key else "json_each.value"
    return text(
        f"EXISTS (SELECT 1 FROM json_each(garment.{column}) WHERE {target} = :{param})"
    ).bindparams(**{param: value})


def _job_summaries(session: Session, garment_ids: list[str]) -> dict[str, JobSummary]:
    """Latest job per garment (newest `created_at`, id as tie-break)."""
    if not garment_ids:
        return {}
    rows = session.exec(
        select(Job)
        .where(col(Job.garment_id).in_(garment_ids))
        .order_by(col(Job.created_at), col(Job.id))
    ).all()
    latest: dict[str, JobSummary] = {}
    for job in rows:  # ascending, so later rows overwrite earlier ones
        latest[job.garment_id] = JobSummary(
            id=job.id, status=job.status, step=job.step, progress=job.progress, error=job.error
        )
    return latest


def _colors(garment: Garment) -> list[ColorEntry] | None:
    return None if garment.colors is None else Colors.model_validate(garment.colors).root


def _list_item(garment: Garment, job: JobSummary | None) -> GarmentListItem:
    return GarmentListItem(
        id=garment.id,
        category=garment.category,
        subcategory=garment.subcategory,
        colors=_colors(garment),
        is_neutral=garment.is_neutral,
        pattern=garment.pattern,
        status=garment.status,
        needs_review=garment.needs_review,
        user_verified=garment.user_verified,
        img_thumb=garment.img_thumb,
        img_cutout=garment.img_cutout,
        wear_count=garment.wear_count,
        last_worn_at=garment.last_worn_at,
        created_at=garment.created_at,
        job=job,
    )


def garment_detail(session: Session, garment: Garment) -> GarmentDetail:
    """Full garment record (API-REQ-005); shared with the edit endpoints."""
    job = _job_summaries(session, [garment.id]).get(garment.id)
    outfit_count = session.exec(
        select(func.count()).select_from(OutfitItem).where(OutfitItem.garment_id == garment.id)
    ).one()
    ai_confidence = (
        None
        if garment.ai_confidence is None
        else AiConfidence.model_validate(garment.ai_confidence).model_dump(mode="json")
    )
    return GarmentDetail(
        **_list_item(garment, job).model_dump(),
        img_original=garment.img_original,
        color_confidence=garment.color_confidence,
        ai_confidence=ai_confidence,
        formality=garment.formality,
        style_tags=garment.style_tags,
        seasons=garment.seasons,
        warmth=garment.warmth,
        material=garment.material,
        brand=garment.brand,
        notes=garment.notes,
        updated_at=garment.updated_at,
        outfit_count=outfit_count,
    )


def get_garment_or_404(session: Session, garment_id: str) -> Garment:
    garment = session.get(Garment, garment_id)
    if garment is None:
        raise AppError(
            GARMENT_NOT_FOUND,
            f"La prenda {garment_id} no existe.",
            404,
            {"garment_id": garment_id},
        )
    return garment


@router.get("/garments", response_model=GarmentList)
def list_garments(
    session: Annotated[Session, Depends(get_session)],
    category: GarmentCategory | None = None,
    color: str | None = None,
    season: Season | None = None,
    status: Annotated[list[GarmentStatus] | None, Query()] = None,
    needs_review: bool | None = None,
    sort: SortField = "created_at",
    order: SortOrder = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> GarmentList:
    """Filtered, sorted, paginated listing (API-REQ-003/004).

    JSON-array filters (`color`, `season`) use SQLite `json_each` in SQL so the
    `total` and the page window are exact. `status` may repeat (OR); no `status`
    means every status. Rows with a NULL sort key go last in either direction;
    `id` is the stable tie-break."""
    conditions: list[ColumnElement[bool] | TextClause] = []
    if category is not None:
        conditions.append(col(Garment.category) == category)
    if status:
        conditions.append(col(Garment.status).in_(status))
    if needs_review is not None:
        conditions.append(col(Garment.needs_review) == needs_review)
    if color is not None:
        conditions.append(_json_contains("colors", "name", "color", color))
    if season is not None:
        conditions.append(_json_contains("seasons", None, "season", season.value))

    sort_column = col(getattr(Garment, sort))
    ordered = sort_column.asc() if order == "asc" else sort_column.desc()
    total = session.exec(select(func.count()).select_from(Garment).where(*conditions)).one()
    garments = session.exec(
        select(Garment)
        .where(*conditions)
        .order_by(sort_column.is_(None), ordered, col(Garment.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    jobs = _job_summaries(session, [g.id for g in garments])
    return GarmentList(
        items=[_list_item(g, jobs.get(g.id)) for g in garments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/garments/{garment_id}",
    response_model=GarmentDetail,
    responses={404: {"model": ErrorResponse}},
)
def get_garment(
    garment_id: str, session: Annotated[Session, Depends(get_session)]
) -> GarmentDetail:
    return garment_detail(session, get_garment_or_404(session, garment_id))
