"""Pure garment-parsing helpers with synthetic arrays (VIS-REQ-029): no models."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ml.garment_parse import (
    ParseResult,
    cut_garment,
    erode_alpha,
    garment_classes,
    garment_mask,
    intersect_alpha,
    largest_clothing_class,
    normalize_label,
    person_present,
)

ATR = {
    0: "background",
    1: "hair",
    2: "upper_clothes",
    3: "pants",
    4: "dress",
    5: "face",
    6: "left_arm",
    7: "left_shoe",
}
U2 = {0: "background", 1: "upper", 2: "lower", 3: "full"}


def _result(grid: list[list[int]], names: dict[int, str] = ATR) -> ParseResult:
    return ParseResult(np.array(grid, dtype=np.uint8), names)


def test_normalize_label() -> None:
    assert normalize_label("Upper-clothes") == "upper_clothes"
    assert normalize_label(" Left-shoe ") == "left_shoe"


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("top", {"upper_clothes"}),
        ("outerwear", {"upper_clothes"}),
        ("mid_layer", {"upper_clothes"}),
        ("bottom", {"pants"}),
        ("one_piece", {"dress"}),
        ("shoes", {"left_shoe"}),
    ],
)
def test_category_class_sets_atr(category: str, expected: set[str]) -> None:
    result = _result([[0, 2, 3, 4, 7]])
    assert garment_classes(result, category) == expected


def test_category_class_sets_u2net_vocabulary() -> None:
    result = _result([[0, 1, 2, 3]], U2)
    assert garment_classes(result, "top") == {"upper"}
    assert garment_classes(result, "bottom") == {"lower"}
    assert garment_classes(result, "one_piece") == {"full"}


def test_unknown_category_uses_largest_clothing_region() -> None:
    result = _result([[2, 2, 2, 3, 5, 0]])
    assert garment_classes(result, None) == {"upper_clothes"}
    assert largest_clothing_class(_result([[0, 5, 1]])) == frozenset()


def test_category_without_class_in_vocabulary_falls_back_to_largest() -> None:
    # u2net has no shoe class: shoes -> largest clothing region
    assert garment_classes(_result([[1, 1, 2]], U2), "shoes") == {"upper"}


def test_person_present_needs_enough_person_pixels() -> None:
    worn = _result([[5, 6, 2, 0]])  # face + arm = 50 %
    flat_lay = _result([[2, 2, 2, 0]])
    assert person_present(worn)
    assert not person_present(flat_lay)


def test_person_present_u2net_falls_back_to_clothing() -> None:
    assert person_present(_result([[1, 0, 0, 0]], U2), min_ratio=0.2)
    assert not person_present(_result([[0, 0, 0, 0]], U2))


def test_garment_mask_selects_category_pixels() -> None:
    mask = garment_mask(_result([[2, 3], [0, 2]]), "top")
    assert mask.tolist() == [[True, False], [False, True]]


def _rgba(w: int, h: int, opaque: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = opaque
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = 120
    arr[top:bottom, left:right, 3] = 255
    return Image.fromarray(arr, mode="RGBA")


def test_intersect_alpha_keeps_only_masked_opaque_pixels() -> None:
    rgba = _rgba(4, 4, (0, 0, 4, 4))
    mask = np.zeros((4, 4), dtype=bool)
    mask[:2, :2] = True
    alpha = np.asarray(intersect_alpha(rgba, mask).getchannel("A"))
    assert alpha[:2, :2].min() == 255
    assert alpha.sum() == 4 * 255
    with pytest.raises(ValueError):
        intersect_alpha(rgba, np.zeros((2, 2), dtype=bool))


def test_cut_garment_removes_arms_and_trousers() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:5, 2:8] = 2  # top
    grid[5:10, 2:8] = 3  # trousers
    grid[0:5, 0:2] = 6  # arm
    cut = cut_garment(_rgba(10, 10, (0, 0, 8, 10)), ParseResult(grid, ATR), "top")
    alpha = np.asarray(cut.rgba.getchannel("A"))
    assert not cut.fallback
    assert (alpha > 0).sum() == 5 * 6
    assert cut.classes == {"upper_clothes"}


def test_cut_garment_small_mask_falls_back_to_matte() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0, 0] = 2  # 1 % of the image, and outside the matte
    matte = _rgba(10, 10, (5, 5, 10, 10))
    cut = cut_garment(matte, ParseResult(grid, ATR), "top", min_ratio=0.02)
    assert cut.fallback
    assert np.array_equal(np.asarray(cut.rgba), np.asarray(matte))


def test_erode_alpha_shrinks_opaque_region() -> None:
    rgba = _rgba(20, 20, (5, 5, 15, 15))
    eroded = np.asarray(erode_alpha(rgba, 2).getchannel("A")) > 0
    assert eroded.sum() == 6 * 6
    assert np.asarray(erode_alpha(rgba, 0).getchannel("A")).sum() == 10 * 10 * 255
