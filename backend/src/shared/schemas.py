"""Pydantic v2 schemas for the JSON columns of `shared.models` (D16).

docs/specs/02-data-model.md convention: SQLite has no native JSON type, so
JSON columns are stored as plain JSON-compatible values (SQLAlchemy's `JSON`
type, TEXT under the hood) and every read/write MUST go through one of these
Pydantic models — never direct dict access.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel, model_validator

from shared.enums import ConfidenceSource

_PROPORTION_SUM_TOLERANCE = 1e-6

AttributeName = Literal[
    "category",
    "subcategory",
    "pattern",
    "formality",
    "style_tags",
    "seasons",
    "warmth",
    "material",
]


class ColorEntry(BaseModel):
    """One entry of `garment.colors` (docs/specs/02-data-model.md)."""

    name: str  # closest palette name, e.g. "marino"
    hex: str  # "#1a2b4c"
    lab: tuple[float, float, float]
    proportion: float = Field(ge=0, le=1)  # entries sum to <= 1


class Colors(RootModel[list[ColorEntry]]):
    """`garment.colors`: first entry = dominant color, sorted by proportion desc.

    Enforced (docs/specs/02-data-model.md, ING-REQ-011): proportions are
    non-increasing and sum to <= 1 (within float tolerance).
    """

    root: list[ColorEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_order_and_sum(self) -> Colors:
        proportions = [entry.proportion for entry in self.root]
        if any(a < b for a, b in zip(proportions, proportions[1:], strict=False)):
            raise ValueError("colors must be sorted by proportion descending")
        if sum(proportions) > 1 + _PROPORTION_SUM_TOLERANCE:
            raise ValueError("color proportions must sum to <= 1")
        return self


class AttributeConfidence(BaseModel):
    """One value of `garment.ai_confidence` (DAT-REQ-021 / VIS-REQ-019).

    Replaces the plain `float` shape of an earlier spec revision: every
    AI-populated field keeps its value, confidence, and provenance together.
    """

    value: str | int | list[str]
    confidence: float = Field(ge=0, le=1)
    source: ConfidenceSource


class AiConfidence(RootModel[dict[AttributeName, AttributeConfidence]]):
    """`garment.ai_confidence`.

    Keys are a subset of the closed set `AttributeName` (docs/specs/02-data-model.md).
    """

    root: dict[AttributeName, AttributeConfidence] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    """`outfit.score_breakdown` (docs/specs/02-data-model.md)."""

    color: float
    style: float
    novelty: float
    preference: float
    total: float


class DuplicateCandidate(BaseModel):
    """Shape of `job.result` when a near-duplicate garment is detected
    (ING-REQ-023, VIS-REQ-022, docs/specs/03-garment-ingestion.md)."""

    duplicate_candidate_garment_id: str
    similarity: float = Field(ge=0, le=1)
