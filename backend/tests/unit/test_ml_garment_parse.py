"""Pure garment-parsing helpers with synthetic arrays (VIS-REQ-029): no models."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ml.garment_parse import (
    FASHN_ALIASES,
    ParseResult,
    cut_garment,
    cut_garment_by_rule,
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


def test_person_present_needs_real_body_evidence() -> None:
    worn = _result([[5, 6, 2, 0]])  # face + arm = 50 %
    flat_lay = _result([[2, 2, 2, 0]])
    assert person_present(worn)
    assert not person_present(flat_lay)


def test_person_present_rejects_skin_like_flat_lay_false_positives() -> None:
    # Sandals / insoles: a few limb pixels (4 %) or hair-labelled shadows, no face.
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0, 0:4] = 6  # 4 % arm-labelled
    grid[5:8, 0:10] = 1  # 30 % hair-labelled
    assert not person_present(ParseResult(grid, ATR))


def test_person_present_accepts_headless_photo_with_enough_limbs() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:2, 0:10] = 6  # 20 % arm, no face (cropped at the neck)
    assert person_present(ParseResult(grid, ATR))


def test_person_present_accepts_a_small_face() -> None:
    grid = np.zeros((20, 20), dtype=np.uint8)
    grid[0:2, 0:4] = 5  # 2 % face
    assert person_present(ParseResult(grid, ATR))


def test_person_present_accepts_a_photo_cropped_below_the_neck() -> None:
    # Trousers worn, only hands visible: 2 % limbs next to 40 % pants.
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0, 0:2] = 6
    grid[2:6, 0:10] = 3
    assert person_present(ParseResult(grid, ATR))


def test_person_present_needs_non_footwear_clothing_next_to_few_limbs() -> None:
    # Flat-lay shoes with a few skin-like pixels: footwear does not count as worn clothing.
    shoes = np.zeros((10, 10), dtype=np.uint8)
    shoes[0, 0:2] = 6
    shoes[2:6, 0:10] = 7
    assert not person_present(ParseResult(shoes, ATR))
    # A flat-lay garment with a stray limb pixel below the limb threshold.
    flat = np.zeros((20, 20), dtype=np.uint8)
    flat[0, 0:3] = 6  # 0.75 % limbs
    flat[5:15, 0:20] = 3
    assert not person_present(ParseResult(flat, ATR))


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


# --- shared vocabulary of the FASHN / SCHP parsers ------------------------------------

FASHN_RAW = [
    "background", "face", "hair", "top", "dress", "skirt", "pants", "belt", "bag", "hat",
    "scarf", "glasses", "arms", "hands", "legs", "feet", "torso", "jewelry",
]  # fmt: skip


def _fashn_names() -> dict[int, str]:
    return {i: normalize_label(n, FASHN_ALIASES) for i, n in enumerate(FASHN_RAW)}


def test_fashn_labels_map_to_shared_vocabulary() -> None:
    names = _fashn_names()
    assert names[3] == "upper_clothes" and names[11] == "sunglasses"
    assert names[12] == "arms" and names[16] == "torso" and names[15] == "feet"
    grid = np.zeros((4, 4), dtype=np.uint8)
    grid[:2] = 3
    grid[2:] = 12
    result = ParseResult(grid, names)
    assert garment_classes(result, "top") == {"upper_clothes"}
    assert person_present(result)  # arms count as a person
    assert garment_classes(result, "shoes") == {"feet"}


def test_schp_label_sets_normalise_like_atr() -> None:
    from ml.schp import SCHP_VARIANTS

    atr = [normalize_label(n) for n in SCHP_VARIANTS["atr"]["labels"]]
    lip = [normalize_label(n) for n in SCHP_VARIANTS["lip"]["labels"]]
    assert len(atr) == 18 and atr[4] == "upper_clothes" and atr[9] == "left_shoe"
    assert len(lip) == 20 and lip[5] == "upper_clothes" and lip[7] == "coat"
    assert garment_classes(_result([[7]], dict(enumerate(lip))), "outerwear") >= {"coat"}
    assert garment_classes(_result([[10]], dict(enumerate(lip))), "one_piece") >= {"jumpsuits"}


# --- subtract mode ---------------------------------------------------------------------


def _alpha(cut: object) -> np.ndarray:
    return np.asarray(cut.rgba.getchannel("A"))  # type: ignore[attr-defined]


def test_subtract_removes_body_and_keeps_mislabelled_garment() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:10, 0:2] = 6  # arm
    grid[0:3, 2:8] = 5  # face
    grid[3:6, 2:8] = 2  # upper clothes
    grid[6:10, 2:8] = 4  # same garment partly labelled as "dress"
    matte = _rgba(10, 10, (0, 0, 8, 10))
    cut = cut_garment(matte, ParseResult(grid, ATR), "top", mode="subtract")
    alpha = _alpha(cut)
    assert not cut.fallback and cut.mode == "subtract"
    assert (alpha > 0).sum() == 7 * 6  # rows 3-9 x cols 2-7, dress part kept
    assert alpha[:, :2].sum() == 0 and alpha[:3].sum() == 0
    # intersect would have lost the dress-labelled part
    inter = cut_garment(matte, ParseResult(grid, ATR), "top", mode="intersect")
    assert (_alpha(inter) > 0).sum() == 3 * 6


def test_subtract_fills_holes_enclosed_by_the_garment() -> None:
    grid = np.zeros((12, 12), dtype=np.uint8)
    matte_arr = np.zeros((12, 12, 4), dtype=np.uint8)
    matte_arr[2:10, 2:10, 3] = 255
    matte_arr[5:7, 5:7, 3] = 0  # matte gap inside the garment
    matte = Image.fromarray(matte_arr, mode="RGBA")
    cut = cut_garment(matte, ParseResult(grid, ATR), None, mode="subtract")
    alpha = _alpha(cut)
    assert alpha[5:7, 5:7].min() == 255 and (alpha > 0).sum() == 8 * 8


def test_subtract_does_not_refill_body_pixels_enclosed_by_the_garment() -> None:
    grid = np.zeros((12, 12), dtype=np.uint8)
    grid[5:7, 5:7] = 6  # a hand through the middle of the garment
    matte = _rgba(12, 12, (2, 2, 10, 10))
    alpha = _alpha(cut_garment(matte, ParseResult(grid, ATR), None, mode="subtract"))
    assert alpha[5:7, 5:7].sum() == 0 and (alpha > 0).sum() == 8 * 8 - 4


def test_subtract_with_category_removes_other_garment_groups() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:5] = 2  # upper clothes
    grid[5:8] = 3  # trousers
    grid[8:10] = 7  # shoes
    matte = _rgba(10, 10, (0, 0, 10, 10))
    result = ParseResult(grid, ATR)
    top = _alpha(cut_garment(matte, result, "top", mode="subtract"))
    assert (top > 0).sum() == 5 * 10  # trousers and shoes gone
    bottom = _alpha(cut_garment(matte, result, "bottom", mode="subtract"))
    assert (bottom > 0).sum() == 3 * 10  # upper clothes and shoes gone
    unknown = _alpha(cut_garment(matte, result, None, mode="subtract"))
    assert (unknown > 0).sum() == 100  # no category: only body is removed
    shoes = _alpha(cut_garment(matte, result, "shoes", mode="subtract"))
    assert (shoes > 0).sum() == 2 * 10 and shoes[8:].min() == 255


def test_subtract_small_mask_falls_back_to_matte() -> None:
    grid = np.full((10, 10), 5, dtype=np.uint8)  # everything is face
    matte = _rgba(10, 10, (0, 0, 10, 10))
    cut = cut_garment(matte, ParseResult(grid, ATR), None, mode="subtract")
    assert cut.fallback
    assert np.array_equal(np.asarray(cut.rgba), np.asarray(matte))


def test_u2net_subtract_has_no_body_classes() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[5:] = 2  # lower
    matte = _rgba(10, 10, (0, 0, 10, 10))
    alpha = _alpha(cut_garment(matte, ParseResult(grid, U2), "top", mode="subtract"))
    assert (alpha > 0).sum() == 50  # lower removed for an upper garment
    assert (_alpha(cut_garment(matte, ParseResult(grid, U2), None, mode="subtract")) > 0).all()


def test_unknown_mask_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="mask mode"):
        cut_garment(_rgba(4, 4, (0, 0, 4, 4)), _result([[0]]), None, mode="magic")


# --- worker rule (U5c) ------------------------------------------------------------------

FASHN = {
    0: "background",
    1: "face",
    2: "upper_clothes",
    3: "pants",
    4: "skirt",
    5: "arms",
    6: "legs",
    7: "feet",
}


def _fashn(grid: np.ndarray) -> ParseResult:
    return ParseResult(grid, FASHN)


def test_rule_clothing_intersects_with_the_whole_class_group() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:5, 0:10] = 2  # top (not a bottom: must go)
    grid[5:8, 0:5] = 3  # pants
    grid[5:8, 5:10] = 4  # skirt labelled next to pants: same group
    grid[8:10, 0:10] = 6  # legs
    cut = cut_garment_by_rule(_rgba(10, 10, (0, 0, 10, 10)), _fashn(grid), "bottom")
    alpha = np.asarray(cut.rgba.getchannel("A"))
    assert not cut.fallback and cut.mode == "intersect"
    assert cut.classes == {"pants", "skirt"}
    assert (alpha > 0).sum() == 3 * 10


def test_rule_clothing_fills_holes_with_sibling_labels_but_not_body() -> None:
    grid = np.zeros((12, 12), dtype=np.uint8)
    grid[1:11, 1:11] = 2
    grid[4:6, 4:6] = 3  # pocket labelled as pants: enclosed hole, refilled
    grid[7:9, 7:9] = 5  # a hand through the garment: body, stays removed
    cut = cut_garment_by_rule(_rgba(12, 12, (0, 0, 12, 12)), _fashn(grid), "top")
    alpha = np.asarray(cut.rgba.getchannel("A"))
    assert (alpha[4:6, 4:6] == 255).all()
    assert (alpha[7:9, 7:9] == 0).all()


def test_rule_unknown_category_uses_largest_clothing_region_with_hole_fill() -> None:
    grid = np.zeros((12, 12), dtype=np.uint8)
    grid[0:9, 0:12] = 2  # largest clothing region
    grid[3:5, 3:5] = 3
    grid[9:12, 0:12] = 3  # smaller pants region
    cut = cut_garment_by_rule(_rgba(12, 12, (0, 0, 12, 12)), _fashn(grid), None)
    alpha = np.asarray(cut.rgba.getchannel("A"))
    assert cut.classes == {"upper_clothes"}
    assert (alpha[3:5, 3:5] == 255).all()  # hole refilled
    assert (alpha[9:12] == 0).all()


@pytest.mark.parametrize("category", ["shoes", "accessory"])
def test_rule_footwear_and_accessories_subtract_body_only(category: str) -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0:3, :] = 6  # legs: removed
    grid[3:6, :] = 1  # face: removed
    grid[6:8, :] = 3  # pants: NOT removed in body-only mode
    cut = cut_garment_by_rule(_rgba(10, 10, (0, 0, 10, 10)), _fashn(grid), category)
    alpha = np.asarray(cut.rgba.getchannel("A"))
    assert not cut.fallback and cut.mode == "subtract"
    assert (alpha[0:6] == 0).all()
    assert (alpha[6:] == 255).all()  # pants and the unlabelled rest stay


def test_rule_small_mask_keeps_the_matte_and_flags_fallback() -> None:
    grid = np.zeros((10, 10), dtype=np.uint8)
    grid[0, 0] = 2
    matte = _rgba(10, 10, (0, 0, 10, 10))
    cut = cut_garment_by_rule(matte, _fashn(grid), "top", min_ratio=0.05)
    assert cut.fallback
    assert np.array_equal(np.asarray(cut.rgba), np.asarray(matte))
