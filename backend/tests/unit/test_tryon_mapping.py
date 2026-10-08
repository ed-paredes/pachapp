"""Category -> cloth type and the pass planner (09-virtual-tryon.md §5.2, §5.3)."""

from __future__ import annotations

import pytest

from shared.enums import GarmentCategory as C
from tryon.mapping import ClothType, PlanGarment, cloth_type, plan_passes


def _plan(*items: tuple[str, C | None], max_passes: int = 3):
    return plan_passes([PlanGarment(i, c) for i, c in items], max_passes)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (C.top, ClothType.upper),
        (C.mid_layer, ClothType.upper),
        (C.outerwear, ClothType.upper),
        (C.bottom, ClothType.lower),
        (C.one_piece, ClothType.overall),
        (C.shoes, None),
        (C.accessory, None),
        (None, None),
    ],
)
def test_cloth_type_mapping(category: C | None, expected: ClothType | None) -> None:
    assert cloth_type(category) == expected


def test_every_category_is_mapped() -> None:
    from tryon.mapping import CATEGORY_CLOTH_TYPE

    assert set(CATEGORY_CLOTH_TYPE) == set(C)


def test_lower_then_uppers_inner_to_outer_regardless_of_input_order() -> None:
    plan = _plan(
        ("coat", C.outerwear), ("shirt", C.top), ("jeans", C.bottom), ("knit", C.mid_layer)
    )
    assert [(p.garment_id, p.cloth_type) for p in plan.passes] == [
        ("jeans", ClothType.lower),
        ("shirt", ClothType.upper),
        ("coat", ClothType.upper),
    ]
    assert plan.garment_ids == ("jeans", "shirt", "coat")
    assert plan.skipped_garment_ids == ("knit",)  # max_passes = 3 leaves 2 upper slots


def test_four_garments_with_four_passes_keep_everything() -> None:
    plan = _plan(
        ("shirt", C.top), ("jeans", C.bottom), ("knit", C.mid_layer), ("coat", C.outerwear),
        max_passes=4,
    )  # fmt: skip
    assert plan.garment_ids == ("jeans", "shirt", "knit", "coat")
    assert plan.skipped_garment_ids == ()


def test_intermediate_layer_is_skipped_keeping_innermost_and_outermost() -> None:
    plan = _plan(("shirt", C.top), ("knit", C.mid_layer), ("coat", C.outerwear), max_passes=2)
    assert plan.garment_ids == ("shirt", "coat")
    assert plan.skipped_garment_ids == ("knit",)


def test_single_slot_keeps_the_outermost() -> None:
    plan = _plan(("shirt", C.top), ("coat", C.outerwear), ("jeans", C.bottom), max_passes=2)
    assert plan.garment_ids == ("jeans", "coat")
    assert plan.skipped_garment_ids == ("shirt",)


def test_max_passes_one_with_lower_and_upper_dresses_only_the_lower() -> None:
    plan = _plan(("shirt", C.top), ("jeans", C.bottom), max_passes=1)
    assert plan.garment_ids == ("jeans",)
    assert plan.skipped_garment_ids == ("shirt",)


def test_one_piece_alone_is_overall() -> None:
    plan = _plan(("dress", C.one_piece))
    assert [(p.garment_id, p.cloth_type) for p in plan.passes] == [("dress", ClothType.overall)]


def test_one_piece_plus_outerwear_is_overall_then_upper() -> None:
    plan = _plan(("coat", C.outerwear), ("dress", C.one_piece))
    assert [(p.garment_id, p.cloth_type) for p in plan.passes] == [
        ("dress", ClothType.overall),
        ("coat", ClothType.upper),
    ]


def test_one_piece_skips_bottom_and_top_but_keeps_mid_layer() -> None:
    plan = _plan(
        ("dress", C.one_piece), ("jeans", C.bottom), ("shirt", C.top), ("knit", C.mid_layer)
    )
    assert plan.garment_ids == ("dress", "knit")
    assert plan.skipped_garment_ids == ("jeans", "shirt")


def test_shoes_and_accessories_are_unsupported_not_skipped() -> None:
    plan = _plan(("shirt", C.top), ("shoes", C.shoes), ("belt", C.accessory), ("x", None))
    assert plan.garment_ids == ("shirt",)
    assert plan.unsupported_garment_ids == ("shoes", "belt", "x")
    assert plan.skipped_garment_ids == ()


def test_nothing_compatible_is_an_empty_plan() -> None:
    plan = _plan(("shoes", C.shoes), ("belt", C.accessory))
    assert plan.is_empty
    assert plan.unsupported_garment_ids == ("shoes", "belt")
    assert _plan().is_empty


def test_ambiguous_same_category_keeps_the_first_by_input_order() -> None:
    plan = _plan(
        ("b1", C.bottom),
        ("b2", C.bottom),
        ("t1", C.top),
        ("t2", C.top),
        ("d1", C.one_piece),
        ("d2", C.one_piece),
        max_passes=4,
    )
    assert plan.garment_ids == ("d1",)
    assert plan.skipped_garment_ids == ("b1", "b2", "t1", "t2", "d2")


def test_two_tops_without_one_piece() -> None:
    plan = _plan(("t1", C.top), ("t2", C.top))
    assert plan.garment_ids == ("t1",)
    assert plan.skipped_garment_ids == ("t2",)


def test_repeated_id_counts_once() -> None:
    plan = _plan(("t1", C.top), ("t1", C.top))
    assert plan.garment_ids == ("t1",)
    assert plan.skipped_garment_ids == ()


def test_planning_is_deterministic() -> None:
    items = (("shirt", C.top), ("jeans", C.bottom), ("coat", C.outerwear), ("shoes", C.shoes))
    assert _plan(*items) == _plan(*items)
