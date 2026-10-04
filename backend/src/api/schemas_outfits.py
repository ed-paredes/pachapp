"""Request and response models of the outfit endpoints
(docs/specs/05-outfit-engine.md ENG-REQ-020, docs/specs/06-feedback-history.md FBH-REQ-017)."""

from __future__ import annotations

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from engine.constants import SEED_MAX
from shared.enums import OutfitSlot, OutfitSource
from shared.schemas import ScoreBreakdown


class GenerateOutfitsRequest(BaseModel):
    """`POST /outfits/generate` (ENG-REQ-020)."""

    fixed_garment_ids: list[UUID] | None = None  # slot inferred from the category
    replace_garment_id: UUID | None = None  # left out of every proposal
    seed: int | None = Field(
        default=None, ge=0, le=SEED_MAX
    )  # tie-break only (ENG-REQ-019); `null` = 0


class OutfitItemProposal(BaseModel):
    garment_id: str
    slot: OutfitSlot
    layer: int | None


class OutfitProposal(BaseModel):
    items: list[OutfitItemProposal]
    score: float
    score_breakdown: ScoreBreakdown
    explanation: str


class GenerateOutfitsResponse(BaseModel):
    proposals: list[OutfitProposal]  # up to 5, possibly none (ENG-REQ-022)
    generated_at: dt.datetime


class OutfitItemInput(BaseModel):
    garment_id: UUID
    slot: OutfitSlot
    layer: int | None = None  # ignored: stored as the canonical layer of the slot (DAT-REQ-006)


class CreateOutfitRequest(BaseModel):
    """`POST /outfits` (FBH-REQ-017)."""

    source: OutfitSource
    items: list[OutfitItemInput] = Field(min_length=1)
    score: float | None = None
    score_breakdown: ScoreBreakdown | None = None
    explanation: str | None = None
    rating: Literal[-1, 0, 1] = 0
    is_favorite: bool = False

    @field_validator("items")
    @classmethod
    def _unique_garments(cls, items: list[OutfitItemInput]) -> list[OutfitItemInput]:
        if len({item.garment_id for item in items}) != len(items):
            raise ValueError("a garment can appear only once in an outfit")
        return items


class OutfitItemResponse(BaseModel):
    garment_id: str
    slot: OutfitSlot
    layer: int | None


class OutfitResponse(BaseModel):
    id: str
    created_at: dt.datetime
    source: OutfitSource
    items: list[OutfitItemResponse]
    score: float | None
    score_breakdown: ScoreBreakdown | None
    explanation: str | None
    is_favorite: bool
    rating: int
    name: str | None


class WearLogCreate(BaseModel):
    """`POST /wear-log` (FBH-REQ-007); `date` defaults to the server's local today."""

    outfit_id: UUID
    date: dt.date | None = None


class WearLogReplace(BaseModel):
    """`PUT /wear-log/{date}` (FBH-REQ-008)."""

    outfit_id: UUID


class WearLogEntry(BaseModel):
    id: str
    date: dt.date
    outfit_id: str
    created_at: dt.datetime
