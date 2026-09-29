"""API response models (docs/specs/04-wardrobe-api.md, API-REQ-017)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from shared.enums import (
    ConfidenceSource,
    GarmentCategory,
    GarmentPattern,
    GarmentStatus,
    JobStatus,
    JobStep,
)
from shared.schemas import ColorEntry


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
