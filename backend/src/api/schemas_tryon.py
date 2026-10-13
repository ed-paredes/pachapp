"""Request and response models of the try-on endpoints (09-virtual-tryon.md §6.7)."""

from __future__ import annotations

import datetime as dt
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from shared.enums import JobStatus


class TryOnRequest(BaseModel):
    """`POST /tryon`: exactly one of `garment_ids` (order as given) or `outfit_id`."""

    garment_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)
    outfit_id: UUID | None = None
    mannequin_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        if (self.garment_ids is None) == (self.outfit_id is None):
            raise ValueError("send exactly one of garment_ids or outfit_id")
        return self


class SkinTone(BaseModel):
    id: int
    hex: str


class TryOnCapabilities(BaseModel):
    enabled: bool
    supported_categories: list[str]
    max_passes: int
    genders: list[str]  # genders whose configured base mannequin loads
    skin_tones: list[SkinTone]


class TryOnRead(BaseModel):
    """A render for polling; `img` is relative to the images root (API-REQ-016), set once done."""

    id: str
    status: JobStatus
    step: str | None
    progress: int
    error: str | None
    img: str | None
    # True when `img` is the featureless dummy (RGBA cut-out in the owner's skin tone), False for
    # the raw full-frame render.
    transparent: bool
    garment_ids: list[str]
    skipped_garment_ids: list[str]
    unsupported_garment_ids: list[str]
    created_at: dt.datetime
