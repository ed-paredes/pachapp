"""Closed enums shared by the DB models, API schemas, and the LLM contract.

DAT-REQ-001 (docs/specs/02-data-model.md): each of these enums has exactly
one definition, reused identically across `shared` (DB), the API schemas,
and the LLM contract (docs/specs/03-garment-ingestion.md) — never
redefined per layer.
"""

from __future__ import annotations

from enum import StrEnum

# `enum.StrEnum` (not the spec code block's literal `class X(str, Enum)`,
# equivalent since Python 3.11 and ruff UP042's preferred spelling under
# target-version py312): members are still `str` instances comparing equal
# to their `.value`, so DAT-REQ-001's "one definition, reused identically"
# holds unchanged for the API schemas and the LLM contract.


class GarmentCategory(StrEnum):
    top = "top"
    bottom = "bottom"
    one_piece = "one_piece"
    mid_layer = "mid_layer"  # D17: jersey, sudadera, cárdigan, sobrecamisa
    outerwear = "outerwear"
    shoes = "shoes"
    accessory = "accessory"


class GarmentPattern(StrEnum):
    solid = "solid"
    striped = "striped"
    plaid = "plaid"
    printed = "printed"
    textured = "textured"


class GarmentStatus(StrEnum):
    active = "active"
    laundry = "laundry"
    archived = "archived"


class Season(StrEnum):
    spring = "spring"
    summer = "summer"
    autumn = "autumn"
    winter = "winter"


class StyleTag(StrEnum):
    casual = "casual"
    classic = "classic"
    street = "street"
    minimal = "minimal"
    sport = "sport"
    elegant = "elegant"
    bohemian = "bohemian"
    preppy = "preppy"


class OutfitSlot(StrEnum):
    top = "top"
    bottom = "bottom"
    one_piece = "one_piece"
    mid_layer = "mid_layer"
    outerwear = "outerwear"
    shoes = "shoes"
    accessory = "accessory"


class OutfitSource(StrEnum):
    generated = "generated"
    manual = "manual"


class JobStatus(StrEnum):
    pending = "pending"
    claimed = "claimed"
    running = "running"
    done = "done"
    failed = "failed"


class JobStep(StrEnum):
    preprocess = "preprocess"
    cutout = "cutout"
    color = "color"
    ai_attributes = "ai_attributes"
    embedding = "embedding"
    consolidate = "consolidate"


class ConfidenceSource(StrEnum):
    """`ai_confidence[field].source` (DAT-REQ-021 / VIS-REQ-019)."""

    zero_shot = "zero_shot"
    knn = "knn"
    blend = "blend"
    llm = "llm"
    user = "user"
