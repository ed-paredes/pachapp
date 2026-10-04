"""Outfit generation: templates, layers, accessories, MMR, determinism, edge sizes."""

from __future__ import annotations

import random
from collections import Counter
from datetime import timedelta

import pytest
from engine_fakes import TODAY, basic_wardrobe, garment, ids_of, request, synthetic_wardrobe

from engine import EngineSettings, InvalidRequest, WornOutfit, generate_outfits
from engine import constants as C
from shared.enums import GarmentCategory as Cat


def _worn(days: int | None) -> dict:
    return {"last_worn_at": None if days is None else TODAY - timedelta(days=days)}


# --- templates -------------------------------------------------------------------


def test_template_a_is_top_bottom_shoes() -> None:
    proposals = generate_outfits(request(basic_wardrobe()))

    assert proposals
    for p in proposals:
        assert [i.slot for i in p.items] == ["top", "bottom", "shoes"]


def test_template_b_is_one_piece_plus_shoes() -> None:
    wardrobe = [garment("d", Cat.one_piece), garment("s", Cat.shoes)]

    proposals = generate_outfits(request(wardrobe))

    assert [[(i.slot, i.garment_id) for i in p.items] for p in proposals] == [
        [("one_piece", "d"), ("shoes", "s")]
    ]


def test_both_templates_compete_in_one_pool() -> None:
    wardrobe = [*basic_wardrobe(), garment("d", Cat.one_piece, colour="marino")]

    sets = [ids_of(p) for p in generate_outfits(request(wardrobe))]

    assert any("d" in s for s in sets) and any("t1" in s or "t2" in s for s in sets)


def test_layers_follow_the_stacking_order_and_accessories_have_none() -> None:
    wardrobe = [
        *basic_wardrobe(),
        garment("m", Cat.mid_layer, **_worn(None)),
        garment("o", Cat.outerwear, **_worn(None)),
        garment("a", Cat.accessory, subcategory="reloj", **_worn(None)),
    ]
    wardrobe = [g if g.id[0] not in "tbs" else _replace(g, last_worn_at=TODAY) for g in wardrobe]

    top = generate_outfits(request(wardrobe))[0]

    assert [(i.slot, i.layer) for i in top.items] == [
        ("outerwear", 4),
        ("mid_layer", 3),
        ("top", 2),
        ("bottom", 1),
        ("shoes", 0),
        ("accessory", None),
    ]


def _replace(g, **changes):
    return g.__class__(**{**g.__dict__, **changes})


# --- greedy layers ---------------------------------------------------------------


def _worn_base() -> list:
    """A single base worn recently, so any never-worn extra raises the novelty."""
    return [
        garment("t", Cat.top, **_worn(2)),
        garment("b", Cat.bottom, **_worn(2)),
        garment("s", Cat.shoes, **_worn(2)),
    ]


def test_a_layer_is_added_only_when_it_improves_the_score() -> None:
    fresh = [*_worn_base(), garment("m", Cat.mid_layer, **_worn(None))]
    stale = [*_worn_base(), garment("m", Cat.mid_layer, **_worn(0))]

    assert ids_of(generate_outfits(request(fresh))[0]) == {"t", "b", "s", "m"}
    assert ids_of(generate_outfits(request(stale))[0]) == {"t", "b", "s"}


def _red_base_with_orange_mid() -> list:
    return [
        garment("t", Cat.top, colour="rojo", hue=20, **_worn(2)),
        garment("b", Cat.bottom, **_worn(2)),
        garment("s", Cat.shoes, **_worn(2)),
        garment("m", Cat.mid_layer, colour="naranja", hue=40, **_worn(None)),
    ]


def test_scn005_extension_that_breaks_the_colour_limit_falls_back_to_a_valid_one() -> None:
    # rojo + naranja already use both non-neutral colours; the best outerwear
    # (never worn, green) would be a third, so the next valid one is taken.
    wardrobe = [
        *_red_base_with_orange_mid(),
        garment("o-green", Cat.outerwear, colour="verde", hue=130, **_worn(None)),
        garment("o-grey", Cat.outerwear, colour="gris", **_worn(10)),
    ]

    outfit = ids_of(generate_outfits(request(wardrobe))[0])

    assert "o-green" not in outfit
    assert outfit == {"t", "b", "s", "m", "o-grey"}


def test_scn005b_layer_is_skipped_when_no_alternative_fits() -> None:
    wardrobe = [
        *_red_base_with_orange_mid(),
        garment("o1", Cat.outerwear, colour="verde", hue=130, **_worn(None)),
        garment("o2", Cat.outerwear, colour="azul", hue=250, **_worn(None)),
    ]

    assert ids_of(generate_outfits(request(wardrobe))[0]) == {"t", "b", "s", "m"}


# --- accessories -----------------------------------------------------------------


def _with_accessories(subtypes: list[str | None], **settings) -> list:
    acc = [
        garment(f"a{i}", Cat.accessory, subcategory=sub, **_worn(None))
        for i, sub in enumerate(subtypes)
    ]
    return acc, EngineSettings(**settings)


def test_accessories_are_capped_by_the_setting() -> None:
    for cap in (0, 1, 2, 3):
        acc, settings = _with_accessories(
            ["reloj", "bufanda", "gorro", "gafas"], max_accessories=cap
        )
        proposals = generate_outfits(request([*_worn_base(), *acc], settings=settings))
        counts = [sum(i.slot == "accessory" for i in p.items) for p in proposals]
        assert counts == [cap]


def test_scn006_no_two_accessories_of_the_same_subtype() -> None:
    acc, settings = _with_accessories(["cinturón", "cinturón", "reloj"])

    proposal = generate_outfits(request([*_worn_base(), *acc], settings=settings))[0]

    subtypes = [
        {"a0": "cinturón", "a1": "cinturón", "a2": "reloj"}[i.garment_id]
        for i in proposal.items
        if i.slot == "accessory"
    ]
    assert sorted(subtypes) == ["cinturón", "reloj"]


def test_fixed_accessories_are_all_forced_in() -> None:
    acc, settings = _with_accessories(["cinturón", "bufanda", "reloj"])

    proposals = generate_outfits(
        request([*_worn_base(), *acc], settings=settings, fixed_garment_ids=("a0", "a1"))
    )

    assert proposals and all({"a0", "a1"} <= ids_of(p) for p in proposals)
    assert all("a2" not in ids_of(p) for p in proposals)  # the cap of 2 is already used


def test_fixed_layer_outside_the_formality_range_gives_no_proposals() -> None:
    wardrobe = [*_worn_base(), garment("coat", Cat.outerwear, formality=5)]

    assert generate_outfits(request(wardrobe, fixed_garment_ids=("coat",))) == []


def test_fixed_layer_is_forced_into_every_proposal() -> None:
    wardrobe = [*basic_wardrobe(), garment("coat", Cat.outerwear, colour="camel")]

    proposals = generate_outfits(request(wardrobe, fixed_garment_ids=("coat",)))

    assert len(proposals) >= 2 and all("coat" in ids_of(p) for p in proposals)


# --- MMR -------------------------------------------------------------------------


def _star_wardrobe() -> list:
    """One never-worn top among tops worn yesterday: it tops almost every base."""
    tops = [garment("t-star", Cat.top, **_worn(None))]
    tops += [garment(f"t{i}", Cat.top, **_worn(1)) for i in range(8)]
    bottoms = [garment(f"b{i}", Cat.bottom, **_worn(1)) for i in range(6)]
    shoes = [garment(f"s{i}", Cat.shoes, **_worn(1)) for i in range(6)]
    return [*tops, *bottoms, *shoes]


def test_scn007_a_garment_is_in_at_most_two_proposals() -> None:
    proposals = generate_outfits(request(_star_wardrobe()))

    assert len(proposals) == 5
    usage = Counter(g for p in proposals for g in ids_of(p))
    assert usage["t-star"] == 2  # the best garment, but capped
    assert max(usage.values()) <= C.MAX_GARMENT_APPEARANCES


def test_proposals_are_distinct_and_best_first() -> None:
    proposals = generate_outfits(request(synthetic_wardrobe(120)))

    sets = [frozenset(ids_of(p)) for p in proposals]
    assert len(proposals) == 5 and len(set(sets)) == 5
    assert proposals[0].score == max(p.score for p in proposals)
    assert max(Counter(g for s in sets for g in s).values()) <= 2


def test_mmr_trades_a_little_score_for_diversity() -> None:
    wardrobe = synthetic_wardrobe(200)

    proposals = generate_outfits(request(wardrobe))

    # without diversity the runner-ups would be near-copies of the best outfit
    best = ids_of(proposals[0])
    assert all(len(best & ids_of(p)) < len(best) for p in proposals[1:])


# --- determinism -----------------------------------------------------------------


def test_same_input_gives_the_same_output() -> None:
    wardrobe = synthetic_wardrobe(100)

    assert generate_outfits(request(wardrobe)) == generate_outfits(request(wardrobe))


def test_garment_order_does_not_change_the_result() -> None:
    wardrobe = synthetic_wardrobe(100)
    shuffled = wardrobe[:]
    random.Random(1).shuffle(shuffled)

    assert generate_outfits(request(wardrobe)) == generate_outfits(request(shuffled))


def test_the_seed_does_not_change_a_result_without_ties() -> None:
    wardrobe = synthetic_wardrobe(100)

    assert generate_outfits(request(wardrobe, seed=0)) == generate_outfits(
        request(wardrobe, seed=99)
    )


@pytest.mark.parametrize("seed", [-1, C.SEED_MAX + 1])
def test_an_out_of_range_seed_is_an_invalid_request(seed: int) -> None:
    with pytest.raises(InvalidRequest):
        generate_outfits(request(basic_wardrobe(), seed=seed))


def test_the_largest_valid_seed_is_accepted() -> None:
    assert generate_outfits(request(basic_wardrobe(), seed=C.SEED_MAX))


def test_the_seed_breaks_exact_ties_deterministically() -> None:
    clones = [garment(f"t{i}", Cat.top) for i in range(12)]
    wardrobe = [*clones, garment("b", Cat.bottom), garment("s", Cat.shoes)]

    def first(seed: int) -> str:
        proposals = generate_outfits(request(wardrobe, seed=seed))
        return next(i.garment_id for i in proposals[0].items if i.slot == "top")

    assert [first(s) for s in range(10)] == [first(s) for s in range(10)]
    assert len({first(s) for s in range(10)}) > 1


# --- widening K, small and empty wardrobes ----------------------------------------


def test_k_is_widened_when_the_top_bases_cannot_make_five_proposals(monkeypatch) -> None:
    # 1,500 bases hold the never-worn shoe, which can appear in only 2 proposals:
    # the first K=300 slice yields 2, widening reaches the other shoes.
    tops = [garment(f"t{i:03d}", Cat.top, **_worn(None)) for i in range(300)]
    bottoms = [garment(f"b{i}", Cat.bottom, **_worn(None)) for i in range(5)]
    shoes = [garment("s-star", Cat.shoes, **_worn(None))]
    shoes += [garment(f"s{i}", Cat.shoes, **_worn(0)) for i in range(4)]
    wardrobe = [*tops, *bottoms, *shoes]

    assert len(generate_outfits(request(wardrobe))) == 5

    monkeypatch.setattr(C, "BASE_TOP_K_MAX", C.BASE_TOP_K)
    assert len(generate_outfits(request(wardrobe))) < 5


@pytest.mark.parametrize(
    "wardrobe",
    [
        [],
        [garment("t", Cat.top)],
        [garment(f"t{i}", Cat.top) for i in range(5)],
        [
            garment("t", Cat.top),
            garment("b", Cat.bottom),
            garment("s", Cat.shoes, status="laundry"),
        ],
        [garment("t", Cat.top), garment("b", Cat.bottom), garment("s", Cat.accessory)],
    ],
)
def test_scn009_small_or_unusable_wardrobes_give_no_proposals_without_error(wardrobe: list) -> None:
    assert generate_outfits(request(wardrobe)) == []


def test_a_wardrobe_that_fits_few_outfits_returns_just_those() -> None:
    proposals = generate_outfits(
        request(basic_wardrobe()[:5])
    )  # 2 tops, 2 bottoms, 1 pair of shoes

    assert 0 < len(proposals) < 5
    assert len({frozenset(ids_of(p)) for p in proposals}) == len(proposals)


def test_garments_missing_attributes_do_not_break_generation() -> None:
    bare = [
        garment("t", Cat.top, formality=None, tags=()),
        garment("b", Cat.bottom, formality=None, tags=()),
        garment("s", Cat.shoes, formality=None, tags=()),
    ]
    bare = [_replace(g, colors=(), is_neutral=None) for g in bare]

    proposals = generate_outfits(request(bare))

    assert len(proposals) == 1 and 0.0 <= proposals[0].score <= 1.0


# --- explanations ----------------------------------------------------------------


def _explain(weights: EngineSettings, wardrobe: list) -> str:
    return generate_outfits(request(wardrobe, settings=weights))[0].explanation


def test_colour_led_explanation_names_the_colours() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="marino"),
        garment("b", Cat.bottom, colour="camel"),
        garment("s", Cat.shoes, colour="marino"),
    ]
    weights = EngineSettings(1, 0, 0, 0)

    assert _explain(weights, wardrobe) == "Marino y camel: neutros clásicos."


def test_non_neutral_colour_explanations() -> None:
    weights = EngineSettings(1, 0, 0, 0)
    one = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("b", Cat.bottom),
        garment("s", Cat.shoes),
    ]
    analogous = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("b", Cat.bottom, colour="naranja", hue=40),
        garment("s", Cat.shoes),
    ]

    assert _explain(weights, one) == "Rojo con neutros: una combinación fácil."
    assert _explain(weights, analogous) == "Rojo y naranja: tonos análogos que armonizan."


def _loud_pair(hue_a: float, hue_b: float) -> list:
    from shared.enums import GarmentPattern

    striped = GarmentPattern.striped
    return [
        garment("t", Cat.top, colour="rojo", hue=hue_a, pattern=striped),
        garment("b", Cat.bottom, colour="azul", hue=hue_b, pattern=striped),
        garment("s", Cat.shoes),
    ]


@pytest.mark.parametrize(
    ("hue_b", "relation"),
    [
        (40, "tonos análogos que armonizan"),
        (200, "colores complementarios con contraste"),
        (90, "un contraste de color atrevido"),
    ],
)
def test_colour_explanation_follows_the_hue_not_the_loud_pattern_penalty(
    hue_b: float, relation: str
) -> None:
    """Two striped garments lower the colour score by 0.4: the sentence must
    still describe the hue relation (an analogous 0.9 -> 0.5 is not complementary)."""
    weights = EngineSettings(1, 0, 0, 0)

    # the "other" case scores 0 after the penalty, so a second sentence may follow
    assert _explain(weights, _loud_pair(20, hue_b)).startswith(f"Rojo y azul: {relation}.")


def test_novelty_led_explanation_names_the_least_recently_worn_garment() -> None:
    wardrobe = [
        garment("t", Cat.top, subcategory="camisa", **_worn(21)),
        garment("b", Cat.bottom, subcategory="pantalón", **_worn(30)),
        garment("s", Cat.shoes, subcategory="zapatillas", **_worn(10)),
    ]

    sentence = _explain(EngineSettings(0, 0, 1, 0), wardrobe)

    assert sentence == "Hace 4 semanas que no usas tu pantalón."


def test_novelty_explanation_for_never_worn_and_short_gaps() -> None:
    weights = EngineSettings(0, 0, 1, 0)
    fresh = [
        garment(i, c, subcategory=n, **_worn(None))
        for i, c, n in [
            ("t", Cat.top, "camisa"),
            ("b", Cat.bottom, "vaquero"),
            ("s", Cat.shoes, "botas"),
        ]
    ]
    recent = [
        garment(i, c, subcategory=n, **_worn(3))
        for i, c, n in [
            ("t", Cat.top, "camisa"),
            ("b", Cat.bottom, "vaquero"),
            ("s", Cat.shoes, "botas"),
        ]
    ]

    assert _explain(weights, fresh).startswith("Todavía no has estrenado tu ")
    assert _explain(weights, recent).startswith("Hace 3 días que no usas tu ")


def test_style_led_explanation_uses_the_dominant_tag() -> None:
    wardrobe = [
        garment(i, c, tags=("classic",))
        for i, c in [("t", Cat.top), ("b", Cat.bottom), ("s", Cat.shoes)]
    ]

    assert (
        _explain(EngineSettings(0, 1, 0, 0), wardrobe) == "Look clásico coherente de arriba abajo."
    )


def test_close_top_components_are_combined_in_one_explanation() -> None:
    wardrobe = [
        garment(i, c, colour="negro", tags=("casual",), **_worn(3))
        for i, c in [("t", Cat.top), ("b", Cat.bottom), ("s", Cat.shoes)]
    ]
    close = EngineSettings(
        weight_color=0.5, weight_style=0.45, weight_novelty=0.05, weight_preference=0
    )

    assert _explain(close, wardrobe) == (
        "Look en negro de una sola tonalidad. Look casual coherente de arriba abajo."
    )


def test_proposal_carries_the_breakdown_and_total() -> None:
    proposal = generate_outfits(request(basic_wardrobe()))[0]

    b = proposal.breakdown
    assert proposal.score == b.total
    assert all(0.0 <= v <= 1.0 for v in (b.color, b.style, b.novelty, b.preference))
    assert b.total == pytest.approx(
        0.35 * b.color + 0.25 * b.style + 0.25 * b.novelty + 0.15 * b.preference
    )


def test_history_lowers_the_novelty_of_recently_worn_garments() -> None:
    wardrobe = basic_wardrobe()
    history = (WornOutfit(TODAY - timedelta(days=1), frozenset({"t1", "b1", "s1"})),)
    worn_today = [
        _replace(g, last_worn_at=TODAY - timedelta(days=1)) if g.id in {"t1", "b1", "s1"} else g
        for g in wardrobe
    ]

    proposals = generate_outfits(request(worn_today, history=history))

    best = proposals[0]
    assert ids_of(best) != {"t1", "b1", "s1"}
    assert len(ids_of(best) & {"t1", "b1", "s1"}) <= 1
