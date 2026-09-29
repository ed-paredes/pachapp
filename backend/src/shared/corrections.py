"""User-correction markers shared by the API and the worker."""

from __future__ import annotations

from sqlmodel import Session, col, select

from shared.models import AiCorrection

COLORS_FIELD = "colors"


def has_color_correction(session: Session, garment_id: str) -> bool:
    """True once the user corrected this garment's colours (an
    `ai_correction(field="colors")` row exists), i.e. `garment.colors` no longer
    comes from the pipeline. `color_confidence` cannot tell: the pipeline can
    legitimately produce exactly 1.0 for a flat colour."""
    row = session.exec(
        select(col(AiCorrection.id))
        .where(col(AiCorrection.garment_id) == garment_id, col(AiCorrection.field) == COLORS_FIELD)
        .limit(1)
    ).first()
    return row is not None
