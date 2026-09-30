"""Garment edits: PATCH and "Revisión terminada" (API-REQ-006/007/019, D19)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.deps import get_session
from api.errors import ErrorResponse
from api.routers.garments import garment_detail, get_garment_or_404
from api.schemas import GarmentDetail, GarmentPatch
from shared.colors_palette import is_neutral
from shared.corrections import has_color_correction
from shared.models import AiCorrection
from shared.schemas import AiConfidence, AttributeConfidence, Colors

router = APIRouter(tags=["garments"])

USER_CONFIDENCE = 1.0
_ENUM_FIELDS = {"category", "pattern", "status"}


def _plain(value: Any) -> Any:
    """JSON-compatible form used to compare and to store values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Colors):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


@router.patch(
    "/garments/{garment_id}",
    response_model=GarmentDetail,
    responses={404: {"model": ErrorResponse}},
)
def patch_garment(
    garment_id: str,
    body: GarmentPatch,
    session: Annotated[Session, Depends(get_session)],
) -> GarmentDetail:
    """Partial update. Corrections of AI-attributed fields are recorded as
    `ai_correction` rows and stamped `source="user"` in the same transaction
    (API-REQ-007, DAT-REQ-012/016). Never touches `needs_review` or
    `user_verified` (DAT-REQ-018/019)."""
    garment = get_garment_or_404(session, garment_id)
    ai_confidence = (
        {}
        if garment.ai_confidence is None
        else AiConfidence.model_validate(garment.ai_confidence).model_dump(mode="json")
    )
    confidence_changed = False
    changed = False

    for field in body.model_fields_set:
        new = _plain(getattr(body, field))
        old = _plain(getattr(garment, field))
        if new == old:
            continue
        changed = True
        if field == "colors":
            # The first correction leaves the durable "user-owned" marker that the
            # worker's color step honours on retry. `ai_value` is the pipeline's
            # colours, or JSON null when there were none (the column is NOT NULL
            # but a JSON null satisfies it). Later edits add no further row.
            if not has_color_correction(session, garment.id):
                session.add(
                    AiCorrection(
                        garment_id=garment.id,
                        field=field,
                        ai_value=old,  # type: ignore[arg-type]  # None -> JSON null
                        corrected_value=new,
                    )
                )
            garment.color_confidence = USER_CONFIDENCE
            garment.is_neutral = is_neutral(Colors.model_validate(new))
        elif field in ai_confidence:
            previous = old if old is not None else ai_confidence[field]["value"]
            session.add(
                AiCorrection(
                    garment_id=garment.id, field=field, ai_value=previous, corrected_value=new
                )
            )
            ai_confidence[field] = AttributeConfidence(
                value=new,
                confidence=USER_CONFIDENCE,
                source="user",  # type: ignore[arg-type]
            ).model_dump(mode="json")
            confidence_changed = True
        # Enum-typed columns take the enum member; JSON columns take plain values.
        setattr(garment, field, getattr(body, field) if field in _ENUM_FIELDS else new)

    if changed:
        if confidence_changed:
            garment.ai_confidence = ai_confidence
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()
        session.refresh(garment)
    return garment_detail(session, garment)


@router.post(
    "/garments/{garment_id}/review/complete",
    response_model=GarmentDetail,
    responses={404: {"model": ErrorResponse}},
)
def complete_review(
    garment_id: str, session: Annotated[Session, Depends(get_session)]
) -> GarmentDetail:
    """The only action that clears `needs_review` and sets `user_verified`
    (API-REQ-019, D19). Idempotent; changes no other field."""
    garment = get_garment_or_404(session, garment_id)
    if garment.needs_review or not garment.user_verified:
        garment.needs_review = False
        garment.user_verified = True
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()
        session.refresh(garment)
    return garment_detail(session, garment)
