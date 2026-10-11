"""Virtual try-on endpoints (09-virtual-tryon.md §6.7).

`POST /tryon` only enqueues (or finds) a render; the worker produces the image. Reads of an
existing render work even when `tryon_enabled` is off, so renders already made stay viewable.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import update
from sqlmodel import Session, col

from api.deps import get_session, get_settings_dep
from api.errors import (
    TRYON_DISABLED,
    TRYON_NOT_FOUND,
    AppError,
    ErrorResponse,
)
from api.schemas_tryon import TryOnCapabilities, TryOnRead, TryOnRequest
from shared.enums import JobStatus
from shared.models import TryOnRender
from shared.settings import Settings
from tryon.mapping import CATEGORY_CLOTH_TYPE
from tryon.requests import find_or_create_render

router = APIRouter(tags=["tryon"])


def _read(render: TryOnRender) -> TryOnRead:
    done = render.status == JobStatus.done
    return TryOnRead(
        id=render.id,
        status=render.status,
        step=render.step,
        progress=render.progress,
        error=render.error,
        img=render.img_path if done else None,
        garment_ids=render.garment_ids,
        skipped_garment_ids=render.skipped_garment_ids,
        unsupported_garment_ids=render.unsupported_garment_ids,
        created_at=render.created_at,
    )


@router.get("/tryon/capabilities", response_model=TryOnCapabilities)
def get_capabilities(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> TryOnCapabilities:
    return TryOnCapabilities(
        enabled=settings.tryon_enabled,
        supported_categories=[c.value for c, t in CATEGORY_CLOTH_TYPE.items() if t is not None],
        max_passes=settings.tryon_max_passes,
    )


@router.post(
    "/tryon",
    response_model=TryOnRead,
    responses={
        202: {"model": TryOnRead, "description": "Render queued or still in progress"},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_tryon(
    body: TryOnRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> TryOnRead:
    """200 when the render is final (cached `done`, a permanent failure, or a failure that spent
    its `MAX_RENDER_ATTEMPTS` tries less than `RETRY_COOLDOWN` ago); 202 when queued, in
    progress, or re-queued after a failure (resubmitting a failed render retries it under the
    same id; see `tryon.requests._reuse`)."""
    if not settings.tryon_enabled:
        raise AppError(TRYON_DISABLED, "La prueba virtual está desactivada.", 503)
    outcome = find_or_create_render(
        session,
        settings,
        garment_ids=[str(g) for g in body.garment_ids] if body.garment_ids else None,
        outfit_id=str(body.outfit_id) if body.outfit_id else None,
        mannequin_id=body.mannequin_id,
    )
    in_flight = (JobStatus.pending, JobStatus.claimed, JobStatus.running)
    response.status_code = 202 if outcome.render.status in in_flight else 200
    return _read(outcome.render)


def _not_found(render_id: str) -> AppError:
    return AppError(
        TRYON_NOT_FOUND,
        f"La prueba virtual {render_id} no existe.",
        404,
        {"render_id": render_id},
    )


@router.get(
    "/tryon/{render_id}",
    response_model=TryOnRead,
    responses={404: {"model": ErrorResponse}},
)
def get_tryon(render_id: str, session: Annotated[Session, Depends(get_session)]) -> TryOnRead:
    render = session.get(TryOnRender, render_id)
    if render is None:
        raise _not_found(render_id)
    if render.status == JobStatus.done:
        # A look the user keeps opening is not stale (`tryon.cleanup`).
        touched = session.connection().execute(
            update(TryOnRender)
            .where(col(TryOnRender.id) == render_id)
            .values(last_accessed_at=dt.datetime.now(dt.UTC))
            .execution_options(synchronize_session=False)
        )
        session.commit()
        if touched.rowcount != 1:
            # The cleanup purged the render between the load and the update.
            raise _not_found(render_id)
        session.refresh(render)
    return _read(render)
