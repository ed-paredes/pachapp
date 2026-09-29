"""DAT-REQ-001: enum values must match docs/specs/02-data-model.md exactly."""

from __future__ import annotations

from shared.enums import (
    ConfidenceSource,
    GarmentCategory,
    GarmentPattern,
    GarmentStatus,
    JobStatus,
    JobStep,
    OutfitSlot,
    OutfitSource,
    Season,
    StyleTag,
)


def test_garment_category_values() -> None:
    assert [member.value for member in GarmentCategory] == [
        "top",
        "bottom",
        "one_piece",
        "mid_layer",
        "outerwear",
        "shoes",
        "accessory",
    ]


def test_garment_pattern_values() -> None:
    assert [member.value for member in GarmentPattern] == [
        "solid",
        "striped",
        "plaid",
        "printed",
        "textured",
    ]


def test_garment_status_values() -> None:
    assert [member.value for member in GarmentStatus] == ["active", "laundry", "archived"]


def test_season_values() -> None:
    assert [member.value for member in Season] == ["spring", "summer", "autumn", "winter"]


def test_style_tag_values() -> None:
    assert [member.value for member in StyleTag] == [
        "casual",
        "classic",
        "street",
        "minimal",
        "sport",
        "elegant",
        "bohemian",
        "preppy",
    ]


def test_outfit_slot_values() -> None:
    # D17: same closed set as GarmentCategory minus nothing — OutfitSlot
    # mirrors GarmentCategory exactly (docs/specs/02-data-model.md).
    assert [member.value for member in OutfitSlot] == [member.value for member in GarmentCategory]


def test_outfit_source_values() -> None:
    assert [member.value for member in OutfitSource] == ["generated", "manual"]


def test_job_status_values() -> None:
    assert [member.value for member in JobStatus] == [
        "pending",
        "claimed",
        "running",
        "done",
        "failed",
    ]


def test_job_step_values() -> None:
    assert [member.value for member in JobStep] == [
        "preprocess",
        "cutout",
        "color",
        "ai_attributes",
        "embedding",
        "consolidate",
    ]


def test_confidence_source_values() -> None:
    # DAT-REQ-021 / VIS-REQ-019: `ai_confidence[field].source` domain.
    assert [member.value for member in ConfidenceSource] == [
        "zero_shot",
        "knn",
        "blend",
        "llm",
        "user",
    ]


def test_all_enum_members_are_str_instances() -> None:
    """Every enum here must behave as a plain `str` (DAT-REQ-001's "one
    definition, reused identically" depends on `Enum.value ==
    str(Enum member)` holding for API schemas / the LLM contract)."""
    for enum_cls in (
        GarmentCategory,
        GarmentPattern,
        GarmentStatus,
        Season,
        StyleTag,
        OutfitSlot,
        OutfitSource,
        JobStatus,
        JobStep,
        ConfidenceSource,
    ):
        for member in enum_cls:
            assert isinstance(member, str)
            assert member == member.value
