"""API response models (docs/specs/04-wardrobe-api.md, API-REQ-017)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from shared.enums import (
    ConfidenceSource,
    GarmentCategory,
    GarmentPattern,
    GarmentStatus,
    JobStatus,
    JobStep,
    Season,
    StyleTag,
)
from shared.schemas import ColorEntry, Colors


class GarmentCreated(BaseModel):
    """`202` body of `POST /garments` (ING-REQ-001)."""

    garment_id: str
    job_id: str


class JobRead(BaseModel):
    """`GET /jobs/{id}` body (ING-REQ-026, API-REQ-013)."""

    status: JobStatus
    step: JobStep | None
    progress: int
    error: str | None
    result: dict[str, Any] | None


# --- A6: garment reads (API-REQ-003..005, API-REQ-017) ---


class JobSummary(BaseModel):
    """Latest job of a garment, so the grid can render a processing placeholder."""

    id: str
    status: JobStatus
    step: JobStep | None
    progress: int
    error: str | None


class AttributeConfidenceRead(BaseModel):
    """One `ai_confidence` entry (DAT-REQ-021)."""

    value: str | int | list[str]
    confidence: float
    source: ConfidenceSource


class GarmentListItem(BaseModel):
    """Card-sized garment for `GET /garments`; image paths are relative (API-REQ-016)."""

    id: str
    category: GarmentCategory | None
    subcategory: str | None
    colors: list[ColorEntry] | None
    is_neutral: bool | None
    pattern: GarmentPattern | None
    status: GarmentStatus
    needs_review: bool
    user_verified: bool
    img_thumb: str | None
    img_cutout: str | None
    wear_count: int
    last_worn_at: date | None
    created_at: datetime
    job: JobSummary | None


class GarmentList(BaseModel):
    """Paginated listing envelope (API-REQ-003)."""

    items: list[GarmentListItem]
    total: int
    page: int
    page_size: int


class GarmentDetail(GarmentListItem):
    """Full record for `GET /garments/{id}` (API-REQ-005)."""

    img_original: str
    color_confidence: float | None
    ai_confidence: dict[str, AttributeConfidenceRead] | None
    formality: int | None
    style_tags: list[str] | None
    seasons: list[str] | None
    warmth: int | None
    material: str | None
    brand: str | None
    notes: str | None
    updated_at: datetime
    outfit_count: int  # computed from outfit_item, not stored


# --- A7a: garment edits (API-REQ-006/007/019) ---


class GarmentPatch(BaseModel):
    """Editable fields only (API-REQ-006). Unknown or forbidden fields
    (`wear_count`, `needs_review`, `ai_confidence`, `img_*`, ...) are rejected
    with FastAPI's standard 422 (`extra="forbid"`, API-REQ-002). Only `brand`
    and `notes` may be cleared with `null`; every other field must carry a value.
    """

    model_config = ConfigDict(extra="forbid")

    category: GarmentCategory | None = None
    subcategory: str | None = None
    colors: Colors | None = None
    pattern: GarmentPattern | None = None
    formality: int | None = Field(default=None, ge=1, le=5)
    style_tags: list[StyleTag] | None = None
    seasons: list[Season] | None = None
    warmth: int | None = Field(default=None, ge=1, le=5)
    material: str | None = None
    brand: str | None = None
    notes: str | None = None
    status: GarmentStatus | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _reject_null_on_required(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None and info.field_name not in {"brand", "notes"}:
            raise ValueError("null is not allowed for this field")
        return value
