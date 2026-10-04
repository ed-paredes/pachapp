"""Hard filters of the outfit engine (ENG-REQ-002..008, 026)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from engine_fakes import TODAY, basic_wardrobe, garment, ids_of, is_valid, request

from engine import (
    EngineSettings,
    InvalidRequest,
    WornOutfit,
    generate_outfits,
)
from shared.enums import GarmentCategory as Cat


def test_formality_spread_of_one_is_allowed_and_two_is_not() -> None:
    wardrobe = [
        garment("t", Cat.top, formality=3),
        garment("b", Cat.bottom, formality=4),
        garment("s", Cat.shoes, formality=5),
    ]

    assert is_valid(wardrobe, ["t", "b"])
    assert not is_valid(wardrobe, ["t", "b", "s"])


def test_formality_spread_also_applies_to_extensions() -> None:
    # Base is formality 3; the formality-5 outerwear must never be added.
    wardrobe = [*basic_wardrobe(), garment("coat", Cat.outerwear, formality=5)]

    proposals = generate_outfits(request(wardrobe))

    assert proposals
    assert all("coat" not in ids_of(p) for p in proposals)


def test_at_most_two_non_neutral_colours() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("b", Cat.bottom, colour="verde", hue=130),
        garment("s", Cat.shoes, colour="azul", hue=250),
    ]

    assert is_valid(wardrobe, ["t", "b"])
    assert not is_valid(wardrobe, ["t", "b", "s"])


def test_neutrals_and_a_repeated_colour_do_not_add_to_the_count() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("t2", Cat.mid_layer, colour="rojo", hue=22),
        garment("b", Cat.bottom, colour="verde", hue=130),
        garment("s", Cat.shoes, colour="negro"),
        garment("o", Cat.outerwear, colour="marino"),
    ]

    # rojo, rojo, verde, + neutrals = 2 distinct non-neutral colours
    assert is_valid(wardrobe, ["t", "t2", "b", "s", "o"])


def test_accessory_colours_are_excluded_from_the_colour_limit() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("b", Cat.bottom, colour="verde", hue=130),
        garment("s", Cat.shoes),
        garment("scarf", Cat.accessory, colour="azul", hue=250, subcategory="bufanda"),
    ]

    assert is_valid(wardrobe, ["t", "b", "s", "scarf"])


def test_two_accessories_of_one_subtype_are_rejected() -> None:
    wardrobe = [
        garment("a", Cat.accessory, subcategory="Cinturón"),
        garment("b", Cat.accessory, subcategory="cinturón "),
        garment("c", Cat.accessory, subcategory="reloj"),
        garment("d", Cat.accessory, subcategory=None),
        garment("e", Cat.accessory, subcategory=None),
    ]

    assert not is_valid(wardrobe, ["a", "b"])
    assert is_valid(wardrobe, ["a", "c"])
    assert is_valid(wardrobe, ["d", "e"])  # unknown subtypes are never "the same"


@pytest.mark.parametrize("status", ["laundry", "archived"])
def test_only_active_garments_are_eligible(status: str) -> None:
    wardrobe = [*basic_wardrobe(), garment("t3", Cat.top, status=status)]

    proposals = generate_outfits(request(wardrobe))

    assert proposals
    assert all("t3" not in ids_of(p) for p in proposals)


def test_garments_without_a_category_are_ignored() -> None:
    wardrobe = [*basic_wardrobe(), garment("x", Cat.top)]
    wardrobe[-1] = wardrobe[-1].__class__(id="x", category=None)

    proposals = generate_outfits(request(wardrobe))

    assert proposals
    assert all("x" not in ids_of(p) for p in proposals)


def _single_outfit() -> list:
    return [
        garment("t", Cat.top, last_worn_at=None),
        garment("b", Cat.bottom),
        garment("s", Cat.shoes),
    ]


def test_exact_set_worn_inside_the_window_is_excluded() -> None:
    history = (WornOutfit(TODAY - timedelta(days=5), frozenset({"t", "b", "s"})),)

    assert generate_outfits(request(_single_outfit(), history=history)) == []


def test_exact_set_worn_outside_the_window_is_allowed() -> None:
    old = (WornOutfit(TODAY - timedelta(days=14), frozenset({"t", "b", "s"})),)
    recent = (WornOutfit(TODAY - timedelta(days=13), frozenset({"t", "b", "s"})),)

    assert len(generate_outfits(request(_single_outfit(), history=old))) == 1
    assert generate_outfits(request(_single_outfit(), history=recent)) == []


def test_no_repeat_days_zero_disables_the_filter() -> None:
    history = (WornOutfit(TODAY, frozenset({"t", "b", "s"})),)
    settings = EngineSettings(no_repeat_days=0)

    assert len(generate_outfits(request(_single_outfit(), history=history, settings=settings))) == 1


def test_partial_overlap_with_a_worn_outfit_is_still_allowed() -> None:
    history = (WornOutfit(TODAY - timedelta(days=2), frozenset({"t1", "b1", "s1"})),)

    proposals = generate_outfits(request(basic_wardrobe(), history=history))

    assert proposals
    assert all(ids_of(p) != {"t1", "b1", "s1"} for p in proposals)
    assert any({"t1", "b1"} <= ids_of(p) or "s1" in ids_of(p) for p in proposals)


def test_extension_of_a_worn_base_is_a_different_set() -> None:
    wardrobe = [*_single_outfit(), garment("jersey", Cat.mid_layer)]
    history = (WornOutfit(TODAY - timedelta(days=1), frozenset({"t", "b", "s"})),)

    proposals = generate_outfits(request(wardrobe, history=history))

    # base alone is excluded, base + jersey is a new set
    assert [ids_of(p) for p in proposals] in ([{"t", "b", "s", "jersey"}], [])


def test_fixed_garment_is_in_every_proposal() -> None:
    proposals = generate_outfits(request(basic_wardrobe(), fixed_garment_ids=("t1",)))

    assert proposals
    assert all(any(i.garment_id == "t1" and i.slot == "top" for i in p.items) for p in proposals)


def test_replace_garment_is_excluded_everywhere() -> None:
    proposals = generate_outfits(request(basic_wardrobe(), replace_garment_id="s1"))

    assert proposals
    assert all("s1" not in ids_of(p) for p in proposals)


def test_swap_one_piece_keeps_the_others_and_drops_the_replaced() -> None:
    proposals = generate_outfits(
        request(basic_wardrobe(), fixed_garment_ids=("t1", "b1"), replace_garment_id="s1")
    )

    assert [ids_of(p) for p in proposals] == [{"t1", "b1", "s2"}]


def test_fixed_one_piece_rules_out_template_a() -> None:
    wardrobe = [*basic_wardrobe(), garment("dress", Cat.one_piece)]

    proposals = generate_outfits(request(wardrobe, fixed_garment_ids=("dress",)))

    assert proposals
    assert all("dress" in ids_of(p) and not ids_of(p) & {"t1", "t2", "b1", "b2"} for p in proposals)


def test_fixed_garments_that_conflict_return_nothing_instead_of_failing() -> None:
    wardrobe = [*basic_wardrobe(), garment("dress", Cat.one_piece)]

    assert generate_outfits(request(wardrobe, fixed_garment_ids=("dress", "t1"))) == []


@pytest.mark.parametrize(
    ("fixed", "replace"),
    [
        (("t1", "t2"), None),  # two tops
        (("ghost",), None),  # unknown id
        (("t1",), "t1"),  # fixed and replaced
        (("laundry-top",), None),  # not active
    ],
)
def test_invalid_fixed_requests_raise(fixed: tuple[str, ...], replace: str | None) -> None:
    wardrobe = [*basic_wardrobe(), garment("laundry-top", Cat.top, status="laundry")]

    with pytest.raises(InvalidRequest):
        generate_outfits(request(wardrobe, fixed_garment_ids=fixed, replace_garment_id=replace))


def test_too_many_or_duplicate_accessories_are_invalid() -> None:
    wardrobe = [
        garment("a1", Cat.accessory, subcategory="reloj"),
        garment("a2", Cat.accessory, subcategory="bufanda"),
        garment("a3", Cat.accessory, subcategory="gorro"),
        garment("a4", Cat.accessory, subcategory="reloj"),
    ]

    with pytest.raises(InvalidRequest, match="más de 2"):
        generate_outfits(request(wardrobe, fixed_garment_ids=("a1", "a2", "a3")))
    with pytest.raises(InvalidRequest, match="mismo tipo"):
        generate_outfits(request(wardrobe, fixed_garment_ids=("a1", "a4")))
