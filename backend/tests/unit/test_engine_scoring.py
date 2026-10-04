"""Score components of the outfit engine (ENG-REQ-011..013, 018, formulas of 05)."""

from __future__ import annotations

import itertools
import math
import random
from datetime import timedelta

import pytest
from engine_fakes import (
    TODAY,
    components_of,
    garment,
    is_valid,
    request,
    synthetic_wardrobe,
)

from engine import EngineSettings, PreferencePair, WornOutfit, generate_outfits
from shared.enums import GarmentCategory as Cat
from shared.enums import GarmentPattern as Pat


def _trio(top_hue: float | None, bottom_hue: float | None):
    def part(gid: str, category: Cat, hue: float | None):
        if hue is None:
            return garment(gid, category, colour="negro")
        return garment(gid, category, colour=f"c{int(hue)}", hue=hue)

    return [part("t", Cat.top, top_hue), part("b", Cat.bottom, bottom_hue)]


# --- C_color -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hues", "expected"),
    [
        ((None, None), 0.9),  # all neutral: high
        ((20, None), 0.9),  # one non-neutral with a neutral: high
        ((20, 45), 0.9),  # analogous, delta 25
        ((350, 10), 0.9),  # analogous across the 0/360 seam
        ((20, 200), 0.5),  # complementary, delta 180
        ((10, 170), 0.5),  # delta 160 is complementary
        ((20, 150), 0.1),  # delta 130: any other relation
        ((20, 60), 0.1),  # delta 40: just outside analogous
    ],
)
def test_color_levels(hues: tuple[float | None, float | None], expected: float) -> None:
    score = components_of(_trio(*hues), ["t", "b"])["color"]

    assert score == pytest.approx(expected)


def test_same_colour_name_counts_as_one_colour() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("b", Cat.bottom, colour="rojo", hue=30),
    ]

    assert components_of(wardrobe, ["t", "b"])["color"] == pytest.approx(0.9)


def test_two_loud_patterns_get_a_strong_penalty() -> None:
    def pair(p1: Pat, p2: Pat) -> float:
        wardrobe = [
            garment("t", Cat.top, pattern=p1),
            garment("b", Cat.bottom, pattern=p2),
        ]
        return components_of(wardrobe, ["t", "b"])["color"]

    assert pair(Pat.striped, Pat.solid) == pytest.approx(0.9)
    assert pair(Pat.textured, Pat.plaid) == pytest.approx(0.9)
    assert pair(Pat.striped, Pat.printed) == pytest.approx(0.5)


def test_accessories_do_not_take_part_in_colour_or_loud_pattern() -> None:
    wardrobe = [
        garment("t", Cat.top, pattern=Pat.striped),
        garment("a", Cat.accessory, colour="rojo", hue=20, pattern=Pat.printed, subcategory="x"),
    ]

    assert components_of(wardrobe, ["t", "a"])["color"] == pytest.approx(0.9)


def test_mid_layer_and_outerwear_count_for_the_hue_relation() -> None:
    wardrobe = [
        garment("t", Cat.top, colour="rojo", hue=20),
        garment("o", Cat.outerwear, colour="verde", hue=150),
    ]

    assert components_of(wardrobe, ["t", "o"])["color"] == pytest.approx(0.1)


# --- C_style -------------------------------------------------------------------


def test_style_formality_term() -> None:
    same = [
        garment("a", Cat.top, formality=3, tags=()),
        garment("b", Cat.bottom, formality=3, tags=()),
    ]
    apart = [
        garment("a", Cat.top, formality=3, tags=()),
        garment("b", Cat.bottom, formality=4, tags=()),
    ]

    assert components_of(same, ["a", "b"])["style"] == pytest.approx(1.0)
    assert components_of(apart, ["a", "b"])["style"] == pytest.approx(0.0)  # variance 0.25 / 0.25


def test_style_tags_use_pairwise_jaccard() -> None:
    wardrobe = [
        garment("a", Cat.top, tags=("casual", "street")),
        garment("b", Cat.bottom, tags=("casual",)),
    ]

    # formality term 1, Jaccard 1/2 -> mean of the two
    assert components_of(wardrobe, ["a", "b"])["style"] == pytest.approx((1 + 0.5) / 2)


def test_style_cosine_is_the_third_term() -> None:
    model = "m@1"
    same = [
        garment("a", Cat.top, embedding=(1.0, 0.0), embedding_model=model),
        garment("b", Cat.bottom, embedding=(2.0, 0.0), embedding_model=model),
    ]
    orthogonal = [
        garment("a", Cat.top, tags=("street",), embedding=(1.0, 0.0), embedding_model=model),
        garment("b", Cat.bottom, tags=("minimal",), embedding=(0.0, 1.0), embedding_model=model),
    ]

    assert components_of(same, ["a", "b"])["style"] == pytest.approx(1.0)
    assert components_of(orthogonal, ["a", "b"])["style"] == pytest.approx(1 / 3)  # (1 + 0 + 0) / 3


def test_cosine_only_compares_the_same_embedding_model() -> None:
    mixed = [
        garment("a", Cat.top, tags=("street",), embedding=(1.0, 0.0), embedding_model="m@1"),
        garment("b", Cat.bottom, tags=("minimal",), embedding=(1.0, 0.0), embedding_model="m@2"),
    ]

    # identical vectors, different models: no cosine term -> mean of formality (1) and Jaccard (0)
    assert components_of(mixed, ["a", "b"])["style"] == pytest.approx(0.5)


def test_cosine_skips_pairs_with_a_missing_vector() -> None:
    model = "m@1"
    wardrobe = [
        garment("a", Cat.top, tags=("street",), embedding=(1.0, 0.0), embedding_model=model),
        garment("b", Cat.bottom, tags=("street",), embedding=(0.0, 1.0), embedding_model=model),
        garment("c", Cat.shoes, tags=("street",)),
    ]

    # only the (a, b) pair has vectors: cosine 0 -> (1 + 1 + 0) / 3
    assert components_of(wardrobe, ["a", "b", "c"])["style"] == pytest.approx(2 / 3)


# --- C_novelty -----------------------------------------------------------------


def _worn(gid: str, category: Cat, days_ago: int | None):
    when = None if days_ago is None else TODAY - timedelta(days=days_ago)
    return garment(gid, category, last_worn_at=when)


def test_novelty_decays_with_days_since_last_worn() -> None:
    wardrobe = [_worn("a", Cat.top, 7), _worn("b", Cat.bottom, 7)]

    # 1 - e^(-7/7); the 7-day pair is not in a worn outfit, so no pair penalty
    assert components_of(wardrobe, ["a", "b"])["novelty"] == pytest.approx(1 - math.exp(-1))


def test_never_worn_garments_are_fully_novel() -> None:
    wardrobe = [_worn("a", Cat.top, None), _worn("b", Cat.bottom, None)]

    assert components_of(wardrobe, ["a", "b"])["novelty"] == pytest.approx(1.0)


def test_worn_today_is_not_novel() -> None:
    wardrobe = [_worn("a", Cat.top, 0), _worn("b", Cat.bottom, 0)]

    assert components_of(wardrobe, ["a", "b"])["novelty"] == pytest.approx(0.0)


def test_pair_worn_together_in_the_window_is_penalised() -> None:
    wardrobe = [_worn("a", Cat.top, 10), _worn("b", Cat.bottom, 10), _worn("c", Cat.shoes, 10)]
    base = components_of(wardrobe, ["a", "b"])["novelty"]
    history = (WornOutfit(TODAY - timedelta(days=10), frozenset({"a", "b"})),)

    penalised = components_of(wardrobe, ["a", "b"], history=history)["novelty"]
    other_pair = components_of(wardrobe, ["a", "c"], history=history)["novelty"]

    assert penalised == pytest.approx(base - 0.15)
    assert other_pair == pytest.approx(base)


def test_pair_penalty_ignores_outfits_outside_the_window() -> None:
    wardrobe = [_worn("a", Cat.top, 30), _worn("b", Cat.bottom, 30)]
    history = (WornOutfit(TODAY - timedelta(days=30), frozenset({"a", "b"})),)

    assert components_of(wardrobe, ["a", "b"], history=history)["novelty"] == pytest.approx(
        components_of(wardrobe, ["a", "b"])["novelty"]
    )


def test_forgotten_garments_add_a_capped_bonus() -> None:
    one = [_worn("a", Cat.top, 0), _worn("b", Cat.bottom, 100)]
    # mean(0, ~1) + 0.1 for the garment unused for 60+ days
    assert components_of(one, ["a", "b"])["novelty"] == pytest.approx(
        (0 + (1 - math.exp(-100 / 7))) / 2 + 0.1
    )

    many = [_worn(f"g{i}", Cat.accessory, 100) for i in range(5)] + [_worn("z", Cat.top, 0)]
    wardrobe = [g.__class__(**{**g.__dict__, "subcategory": f"s{i}"}) for i, g in enumerate(many)]
    ids = [g.id for g in wardrobe]
    expected = min(1.0, 5 * (1 - math.exp(-100 / 7)) / 6 + 0.3)  # bonus capped at 0.3, not 0.5
    assert components_of(wardrobe, ids)["novelty"] == pytest.approx(expected)


def test_layers_and_accessories_count_like_any_other_garment() -> None:
    wardrobe = [
        _worn("t", Cat.top, 0),
        _worn("o", Cat.outerwear, 0),
        _worn("a", Cat.accessory, 0),
    ]

    assert components_of(wardrobe, ["t", "o", "a"])["novelty"] == pytest.approx(0.0)
    assert components_of(wardrobe, ["t"])["novelty"] == pytest.approx(0.0)


# --- C_preference --------------------------------------------------------------


def test_preference_is_neutral_without_feedback() -> None:
    wardrobe = [garment("a", Cat.top), garment("b", Cat.bottom)]

    assert components_of(wardrobe, ["a", "b"])["preference"] == 0.5


def test_preference_rises_with_liked_pairs_and_falls_with_disliked() -> None:
    wardrobe = [garment("a", Cat.top), garment("b", Cat.bottom), garment("c", Cat.accessory)]
    liked = (PreferencePair("a", "b", liked=2),)
    disliked = (PreferencePair("b", "a", disliked=2),)
    mixed = (PreferencePair("a", "b", liked=1, disliked=1),)

    assert components_of(wardrobe, ["a", "b"], preferences=liked)["preference"] == pytest.approx(
        0.5 + 0.5 * math.tanh(2 / 3)
    )
    assert components_of(wardrobe, ["a", "b"], preferences=disliked)["preference"] == pytest.approx(
        0.5 - 0.5 * math.tanh(2 / 3)
    )
    assert components_of(wardrobe, ["a", "b"], preferences=mixed)["preference"] == 0.5
    # accessory pairs take part like any other (ENG-REQ-013)
    assert (
        components_of(wardrobe, ["a", "c"], preferences=(PreferencePair("a", "c", liked=1),))[
            "preference"
        ]
        > 0.5
    )
    # a pair that is not entirely inside the set contributes nothing
    assert components_of(wardrobe, ["a", "c"], preferences=liked)["preference"] == 0.5


# --- the weighted total and an independent reference ---------------------------


def test_total_uses_the_settings_weights() -> None:
    wardrobe = [_worn("t", Cat.top, 0), _worn("b", Cat.bottom, 0), _worn("s", Cat.shoes, 0)]
    weights = EngineSettings(
        weight_color=0.5, weight_style=0.3, weight_novelty=0.1, weight_preference=0.1
    )

    proposal = generate_outfits(request(wardrobe, settings=weights))[0]

    b = proposal.breakdown
    assert b.total == pytest.approx(
        0.5 * b.color + 0.3 * b.style + 0.1 * b.novelty + 0.1 * b.preference
    )
    assert proposal.score == b.total
    assert b.preference == 0.5 and b.novelty == pytest.approx(0.0)


def _reference(garments, ids, today, history_pairs, window_pairs) -> tuple[float, float, float]:
    """Plain-Python reading of the spec formulas: color, style, novelty."""
    by_id = {g.id: g for g in garments}
    sel = [by_id[i] for i in ids]
    clothing = [g for g in sel if g.category != Cat.accessory]
    names: dict = {}
    for g in clothing:  # the first garment wearing a colour gives its hue
        if g.is_neutral is False:
            names.setdefault(g.colors[0].name, g)
    if len(names) <= 1:
        color = 0.9
    else:
        h = [
            math.degrees(math.atan2(g.colors[0].lab[2], g.colors[0].lab[1])) % 360
            for g in names.values()
        ]
        d = abs(h[0] - h[1])
        d = min(d, 360 - d)
        color = 0.9 if d <= 30 else (0.5 if d >= 150 else 0.1)
    if sum(g.pattern in (Pat.striped, Pat.plaid, Pat.printed) for g in clothing) >= 2:
        color = max(0.0, color - 0.4)

    f = [g.formality for g in sel]
    mean = sum(f) / len(f)
    terms = [1 - min(1.0, (sum((x - mean) ** 2 for x in f) / len(f)) / 0.25)]
    pairs = list(itertools.combinations(sel, 2))
    jac = [
        len(set(a.style_tags) & set(b.style_tags)) / len(set(a.style_tags) | set(b.style_tags))
        for a, b in pairs
    ]
    terms.append(sum(jac) / len(jac))
    cos = []
    for a, b in pairs:
        if a.embedding and b.embedding and a.embedding_model == b.embedding_model:
            dot = sum(x * y for x, y in zip(a.embedding, b.embedding, strict=True))
            na, nb = (math.sqrt(sum(x * x for x in v.embedding)) for v in (a, b))
            cos.append(min(1.0, max(0.0, dot / (na * nb))))
    if cos:
        terms.append(sum(cos) / len(cos))
    style = sum(terms) / len(terms)

    days = [10_000 if g.last_worn_at is None else (today - g.last_worn_at).days for g in sel]
    novelty = sum(1 - math.exp(-d / 7) for d in days) / len(days)
    if any({a.id, b.id} in window_pairs for a, b in pairs):
        novelty -= 0.15
    novelty += min(0.3, 0.1 * sum(d >= 60 for d in days))
    return color, style, min(1.0, max(0.0, novelty))


def test_vectorised_scores_match_a_plain_python_reference() -> None:
    wardrobe = synthetic_wardrobe(120)
    rng = random.Random(3)
    window = [{"top-001", "bottom-002"}, {"shoes-003", "top-001"}]
    history = (
        WornOutfit(TODAY - timedelta(days=3), frozenset({"top-001", "bottom-002", "shoes-003"})),
    )
    by_slot = {c: [g.id for g in wardrobe if g.category == c] for c in Cat}
    checked = 0
    for _ in range(300):
        ids = [
            rng.choice(by_slot[Cat.top]),
            rng.choice(by_slot[Cat.bottom]),
            rng.choice(by_slot[Cat.shoes]),
        ]
        if rng.random() < 0.5:
            ids.append(rng.choice(by_slot[Cat.outerwear]))
        if rng.random() < 0.5:
            ids.append(rng.choice(by_slot[Cat.accessory]))
        if not is_valid(wardrobe, ids):
            continue  # scores are only defined for sets that pass the hard filters
        checked += 1
        got = components_of(wardrobe, ids, history=history)
        color, style, novelty = _reference(
            wardrobe,
            ids,
            TODAY,
            None,
            [*window, {"top-001", "shoes-003"}, {"bottom-002", "shoes-003"}],
        )
        assert got["color"] == pytest.approx(color)
        assert got["style"] == pytest.approx(style)
        assert got["novelty"] == pytest.approx(novelty)
    assert checked >= 30
