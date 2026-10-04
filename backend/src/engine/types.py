"""Plain data the engine consumes and produces (no I/O, no ORM objects).

The API builds these from the database rows; the engine never sees a session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from shared.enums import GarmentCategory, GarmentPattern, GarmentStatus


class InvalidRequest(ValueError):
    """The request cannot be honoured (ENG-REQ-026); the message is Spanish."""


@dataclass(frozen=True)
class EngineColor:
    name: str
    hex: str
    lab: tuple[float, float, float]
    proportion: float


@dataclass(frozen=True)
class EngineGarment:
    id: str
    category: GarmentCategory | None
    subcategory: str | None = None
    colors: tuple[EngineColor, ...] = ()
    is_neutral: bool | None = None
    pattern: GarmentPattern | None = None
    formality: int | None = None
    style_tags: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    last_worn_at: date | None = None
    status: GarmentStatus = GarmentStatus.active


@dataclass(frozen=True)
class WornOutfit:
    """One `wear_log` row: the day and the garment ids of the outfit worn."""

    day: date
    garment_ids: frozenset[str]


@dataclass(frozen=True)
class PreferencePair:
    """How many times two garments shared a liked / disliked outfit."""

    garment_a: str
    garment_b: str
    liked: int = 0
    disliked: int = 0


@dataclass(frozen=True)
class EngineSettings:
    weight_color: float = 0.35
    weight_style: float = 0.25
    weight_novelty: float = 0.25
    weight_preference: float = 0.15
    no_repeat_days: int = 14
    max_accessories: int = 2


@dataclass(frozen=True)
class GenerationRequest:
    garments: tuple[EngineGarment, ...]
    today: date
    settings: EngineSettings = field(default_factory=EngineSettings)
    history: tuple[WornOutfit, ...] = ()
    preferences: tuple[PreferencePair, ...] = ()
    fixed_garment_ids: tuple[str, ...] = ()
    replace_garment_id: str | None = None
    seed: int = 0
    # Garment-id sets already shown to the user (order-insensitive): never proposed again.
    exclude_sets: tuple[frozenset[str], ...] = ()


@dataclass(frozen=True)
class ProposalItem:
    garment_id: str
    slot: str  # an `OutfitSlot` value
    layer: int | None


@dataclass(frozen=True)
class ScoreBreakdown:
    color: float
    style: float
    novelty: float
    preference: float
    total: float


@dataclass(frozen=True)
class Proposal:
    items: tuple[ProposalItem, ...]
    score: float
    breakdown: ScoreBreakdown
    explanation: str
