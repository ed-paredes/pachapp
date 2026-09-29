"""Pydantic v2 schemas for the JSON columns of `shared.models` (D16).

docs/specs/02-data-model.md convention: SQLite has no native JSON type, so
JSON columns are stored as plain JSON-compatible values (SQLAlchemy's `JSON`
type, TEXT under the hood) and every read/write MUST go through one of these
Pydantic models — never direct dict access.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, RootModel

from shared.enums import ConfidenceSource


class ColorEntry(BaseModel):
    """One entry of `garment.colors` (docs/specs/02-data-model.md)."""

    name: str  # closest palette name, e.g. "marino"
    hex: str  # "#1a2b4c"
    lab: tuple[float, float, float]
    proportion: float = Field(ge=0, le=1)  # entries sum to <= 1


class Colors(RootModel[list[ColorEntry]]):
    """`garment.colors`: first entry = dominant color, sorted by proportion desc."""

    root: list[ColorEntry] = Field(default_factory=list)


class AttributeConfidence(BaseModel):
    """One value of `garment.ai_confidence` (DAT-REQ-021 / VIS-REQ-019).

    Replaces the plain `float` shape of an earlier spec revision: every
    AI-populated field keeps its value, confidence, and provenance together.
    """

    value: str | int | list[str]
    confidence: float = Field(ge=0, le=1)
    source: ConfidenceSource


class AiConfidence(RootModel[dict[str, AttributeConfidence]]):
    """`garment.ai_confidence`.

    Keys are a subset of {"category", "subcategory", "pattern", "formality",
    "style_tags", "seasons", "warmth", "material"}.
    """

    root: dict[str, AttributeConfidence] = Field(default_factory=dict)


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
