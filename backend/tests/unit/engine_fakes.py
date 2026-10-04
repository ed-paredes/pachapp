"""Builders for outfit-engine tests: tiny hand-made garments and a synthetic wardrobe."""

from __future__ import annotations

import math
import random
from datetime import date

from engine import EngineColor, EngineGarment, EngineSettings, GenerationRequest
from shared.enums import GarmentCategory, GarmentPattern

TODAY = date(2026, 10, 4)
NEUTRAL = {"negro", "blanco", "gris", "beige", "camel", "marino", "denim"}


def color(name: str, hue: float = 0.0) -> EngineColor:
    """A dominant colour whose Lab hue angle is `hue` degrees."""
    a, b = 40 * math.cos(math.radians(hue)), 40 * math.sin(math.radians(hue))
    return EngineColor(name=name, hex="#808080", lab=(50.0, a, b), proportion=1.0)


def garment(
    gid: str,
    category: GarmentCategory,
    *,
    colour: str = "negro",
    hue: float = 0.0,
    subcategory: str | None = None,
    formality: int | None = 3,
    tags: tuple[str, ...] = ("casual",),
    pattern: GarmentPattern = GarmentPattern.solid,
    embedding: tuple[float, ...] | None = None,
    embedding_model: str | None = None,
    last_worn_at: date | None = None,
    status: str = "active",
) -> EngineGarment:
    from shared.enums import GarmentStatus

    return EngineGarment(
        id=gid,
        category=category,
        subcategory=subcategory,
        colors=(color(colour, hue),),
        is_neutral=colour in NEUTRAL,
        pattern=pattern,
        formality=formality,
        style_tags=tags,
        embedding=embedding,
        embedding_model=embedding_model,
        last_worn_at=last_worn_at,
        status=GarmentStatus(status),
    )


def request(garments: list[EngineGarment], **kwargs) -> GenerationRequest:
    settings = kwargs.pop("settings", EngineSettings())
    return GenerationRequest(
        garments=tuple(garments), today=kwargs.pop("today", TODAY), settings=settings, **kwargs
    )


def basic_wardrobe() -> list[EngineGarment]:
    """Two tops, two bottoms, two shoes, all neutral and formality 3."""
    cat = GarmentCategory
    return [
        garment("t1", cat.top, colour="blanco"),
        garment("t2", cat.top, colour="gris"),
        garment("b1", cat.bottom, colour="negro"),
        garment("b2", cat.bottom, colour="denim"),
        garment("s1", cat.shoes, colour="negro"),
        garment("s2", cat.shoes, colour="blanco"),
    ]


_COLOURS = [
    ("negro", 0), ("blanco", 0), ("gris", 0), ("beige", 0), ("marino", 0), ("denim", 0),
    ("rojo", 20), ("verde", 130), ("azul", 250), ("amarillo", 90), ("rosa", 340),
]  # fmt: skip
_TAGS = ("casual", "classic", "street", "minimal", "sport")
_ACCESSORY_SUBTYPES = ("cinturón", "bufanda", "gorro", "reloj", "gafas", "collar")


def synthetic_wardrobe(total: int = 300, seed: int = 7) -> list[EngineGarment]:
    """A varied wardrobe covering every category, with embeddings."""
    rng = random.Random(seed)
    cat = GarmentCategory
    shares = [
        (cat.top, 0.25), (cat.bottom, 0.2), (cat.one_piece, 0.05), (cat.mid_layer, 0.1),
        (cat.outerwear, 0.1), (cat.shoes, 0.15), (cat.accessory, 0.15),
    ]  # fmt: skip
    out: list[EngineGarment] = []
    for category, share in shares:
        for n in range(round(total * share)):
            name, hue = rng.choice(_COLOURS)
            out.append(
                garment(
                    f"{category.value}-{n:03d}",
                    category,
                    colour=name,
                    hue=hue + rng.uniform(-8, 8),
                    subcategory=rng.choice(_ACCESSORY_SUBTYPES)
                    if category == cat.accessory
                    else None,
                    formality=rng.choice([2, 3, 3, 3, 4]),
                    tags=tuple(rng.sample(_TAGS, 2)),
                    pattern=rng.choice(list(GarmentPattern)),
                    embedding=tuple(rng.gauss(0, 1) for _ in range(16)),
                    embedding_model="test-model@1",
                    last_worn_at=None if rng.random() < 0.4 else date(2026, rng.randint(7, 10), 1),
                )
            )
    return out


def components_of(garments: list[EngineGarment], ids: list[str], **kwargs) -> dict[str, float]:
    """The four score components of one explicit set, via the engine's own batch code."""
    import numpy as np

    from engine.context import build_context, eligible
    from engine.scoring import SetView, components

    req = request(garments, **kwargs)
    ctx = build_context(req, [g for g in garments if eligible(g)])
    idx = np.array([[ctx.index[i] for i in ids]])
    c = components(SetView(ctx, idx))[0]
    return {"color": c[0], "style": c[1], "novelty": c[2], "preference": c[3]}


def is_valid(garments: list[EngineGarment], ids: list[str], **kwargs) -> bool:
    """Whether one explicit set passes the hard filters (003, 007, 008)."""
    import numpy as np

    from engine.context import build_context, eligible
    from engine.scoring import SetView, valid_mask

    ctx = build_context(request(garments, **kwargs), [g for g in garments if eligible(g)])
    idx = np.array([[ctx.index[i] for i in ids]])
    return bool(valid_mask(SetView(ctx, idx))[0])


def ids_of(proposal) -> set[str]:
    return {item.garment_id for item in proposal.items}
