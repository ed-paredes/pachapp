"""Settings endpoints (API-REQ-014/015, DAT-REQ-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from api.deps import get_session
from api.errors import INVALID_WEIGHTS, AppError, ErrorResponse
from shared.models import Setting

router = APIRouter(tags=["settings"])

WEIGHT_FIELDS = ("weight_color", "weight_style", "weight_novelty", "weight_preference")
WEIGHT_SUM_TOLERANCE = 0.01

_Weight = Annotated[float, Field(ge=0, le=1)]
_Threshold = Annotated[float, Field(ge=0, le=1)]
_NonNegative = Annotated[int, Field(ge=0)]


class SettingsRead(BaseModel):
    """The singleton `setting` row (API-REQ-014)."""

    weight_color: float
    weight_style: float
    weight_novelty: float
    weight_preference: float
    no_repeat_days: int
    max_accessories: int
    duplicate_warning_threshold: float
    needs_review_threshold: float
    color_review_threshold: float


class SettingsPatch(BaseModel):
    """Partial update (API-REQ-015). Unknown fields are a 422 (`extra="forbid"`);
    an explicit `null` is rejected too, since no setting is nullable."""

    model_config = ConfigDict(extra="forbid")

    weight_color: _Weight | None = None
    weight_style: _Weight | None = None
    weight_novelty: _Weight | None = None
    weight_preference: _Weight | None = None
    no_repeat_days: _NonNegative | None = None
    max_accessories: _NonNegative | None = None
    duplicate_warning_threshold: _Threshold | None = None
    needs_review_threshold: _Threshold | None = None
    color_review_threshold: _Threshold | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _reject_null(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            raise ValueError("null is not allowed for this field")
        return value


def _get_or_create(session: Session) -> Setting:
    """The row is seeded by a migration; tolerate a missing one with defaults.
    Idempotent under races: `INSERT ... ON CONFLICT DO NOTHING`, then read."""
    row = session.get(Setting, 1)
    if row is None:
        session.connection().execute(sqlite_insert(Setting).values(id=1).on_conflict_do_nothing())
        session.commit()
        row = session.get(Setting, 1)
        assert row is not None
    return row


def _read(row: Setting) -> SettingsRead:
    return SettingsRead.model_validate(row, from_attributes=True)


@router.get("/settings", response_model=SettingsRead)
def get_settings(session: Annotated[Session, Depends(get_session)]) -> SettingsRead:
    return _read(_get_or_create(session))


@router.patch(
    "/settings",
    response_model=SettingsRead,
    responses={400: {"model": ErrorResponse}},
)
def patch_settings(
    body: SettingsPatch, session: Annotated[Session, Depends(get_session)]
) -> SettingsRead:
    """Partial update. If any `weight_*` is present, the four resulting weights
    must sum to 1.0 +- 0.01 or nothing is written (`INVALID_WEIGHTS`, DAT-REQ-011)."""
    row = _get_or_create(session)
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    if changes.keys() & set(WEIGHT_FIELDS):
        total = sum(changes.get(name, getattr(row, name)) for name in WEIGHT_FIELDS)
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE + 1e-9:
            raise AppError(
                INVALID_WEIGHTS,
                f"Los cuatro pesos deben sumar 1,0 (±0,01); ahora suman {total:.2f}.",
                400,
                {"sum": round(total, 6)},
            )
    if changes:
        for name, value in changes.items():
            setattr(row, name, value)
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
    return _read(row)
