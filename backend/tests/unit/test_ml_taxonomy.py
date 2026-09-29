"""Taxonomy tests (08-local-vision.md VIS-REQ-011/012/029): pure, no model."""

from __future__ import annotations

from ml.taxonomy import PROMPT_TEMPLATES, SUBCATEGORY_BY_PROMPT, TAXONOMY, expand_prompts
from shared.enums import GarmentCategory, GarmentPattern


def test_category_and_pattern_keys_match_enums() -> None:
    assert set(TAXONOMY["category"]) == {c.value for c in GarmentCategory}
    assert set(TAXONOMY["pattern"]) == {p.value for p in GarmentPattern}


def test_style_tags_partial_coverage_is_exactly_the_five_listed() -> None:
    assert set(TAXONOMY["style_tags"]) == {"casual", "classic", "street", "minimal", "sport"}


def test_formality_keys_are_ordinals_1_to_5() -> None:
    assert list(TAXONOMY["formality"]) == [1, 2, 3, 4, 5]


def test_material_keys_are_spanish_free_text() -> None:
    assert set(TAXONOMY["material"]) == {"algodón", "denim", "lana", "cuero", "lino", "sintético"}


def test_every_category_prompt_has_a_subcategory() -> None:
    prompts = {p for ps in TAXONOMY["category"].values() for p in ps}
    assert prompts == set(SUBCATEGORY_BY_PROMPT)
    assert SUBCATEGORY_BY_PROMPT["a t-shirt"] == "t-shirt"
    assert SUBCATEGORY_BY_PROMPT["jeans"] == "jeans"
    assert SUBCATEGORY_BY_PROMPT["a cap"] == "cap"


def test_expand_prompts_is_prompt_major_product() -> None:
    out = expand_prompts(["a cap", "a bag"])
    assert len(out) == 2 * len(PROMPT_TEMPLATES)
    assert out[0] == "a photo of a cap"
    assert out[len(PROMPT_TEMPLATES)] == "a photo of a bag"
    assert expand_prompts(["x"], ["{} y"]) == ["x y"]
