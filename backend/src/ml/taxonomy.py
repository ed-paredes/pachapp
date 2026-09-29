"""Zero-shot taxonomy and prompts (08-local-vision.md, VIS-REQ-011/VIS-REQ-012).

Keys of `category`, `pattern` and `style_tags` are exactly the values of the
enums in `shared.enums` (`GarmentCategory`, `GarmentPattern`, `StyleTag`);
`material` keys are free-text Spanish values (no enum in 02-data-model.md);
`formality` keys are the ordinal integers 1-5. Prompts stay in English (the
model was trained on English text).

`style_tags` covers only 5 of the 8 `StyleTag` values on purpose (open question
in 08): `elegant`, `bohemian` and `preppy` have no prompts yet.

Pure module: no torch, no model. Everything here is unit-testable offline.
"""

from __future__ import annotations

from typing import Any

from shared.enums import GarmentCategory, GarmentPattern, StyleTag

TAXONOMY: dict[str, dict[Any, list[str]]] = {
    "category": {
        GarmentCategory.top.value: ["a t-shirt", "a shirt", "a polo shirt", "a blouse"],
        GarmentCategory.bottom.value: ["jeans", "trousers", "chinos", "shorts", "a skirt"],
        GarmentCategory.one_piece.value: ["a dress", "a jumpsuit"],
        GarmentCategory.mid_layer.value: ["a sweater", "a hoodie", "a cardigan", "an overshirt"],
        GarmentCategory.outerwear.value: ["a jacket", "a coat", "a blazer", "a parka"],
        GarmentCategory.shoes.value: ["sneakers", "boots", "leather shoes", "sandals"],
        GarmentCategory.accessory.value: ["a belt", "a scarf", "a cap", "a bag", "a watch"],
    },
    "pattern": {
        GarmentPattern.solid.value: ["a plain solid-color garment"],
        GarmentPattern.striped.value: ["a striped garment"],
        GarmentPattern.plaid.value: ["a plaid garment", "a checked garment"],
        GarmentPattern.printed.value: [
            "a garment with a printed pattern",
            "a floral print garment",
        ],
        GarmentPattern.textured.value: ["a textured knit garment", "a ribbed garment"],
    },
    "material": {
        "algodón": ["a cotton garment"],
        "denim": ["a denim garment"],
        "lana": ["a wool garment"],
        "cuero": ["a leather item"],
        "lino": ["a linen garment"],
        "sintético": ["a polyester garment"],
    },
    "formality": {
        1: ["sportswear", "gym clothes"],
        2: ["casual everyday clothes"],
        3: ["smart casual clothes"],
        4: ["business clothes"],
        5: ["formal suit clothing", "black tie attire"],
    },
    "style_tags": {
        StyleTag.casual.value: ["casual style"],
        StyleTag.classic.value: ["classic style"],
        StyleTag.street.value: ["streetwear style"],
        StyleTag.minimal.value: ["minimalist style"],
        StyleTag.sport.value: ["athletic style"],
    },
}

PROMPT_TEMPLATES: list[str] = [
    "a photo of {}",
    "{}, product photo on a plain background",
]

# VIS-REQ-012: winning category prompt -> free-text `garment.subcategory`.
# Articles are dropped; "a t-shirt" -> "t-shirt", "jeans" -> "jeans".
SUBCATEGORY_BY_PROMPT: dict[str, str] = {
    "a t-shirt": "t-shirt",
    "a shirt": "shirt",
    "a polo shirt": "polo shirt",
    "a blouse": "blouse",
    "jeans": "jeans",
    "trousers": "trousers",
    "chinos": "chinos",
    "shorts": "shorts",
    "a skirt": "skirt",
    "a dress": "dress",
    "a jumpsuit": "jumpsuit",
    "a sweater": "sweater",
    "a hoodie": "hoodie",
    "a cardigan": "cardigan",
    "an overshirt": "overshirt",
    "a jacket": "jacket",
    "a coat": "coat",
    "a blazer": "blazer",
    "a parka": "parka",
    "sneakers": "sneakers",
    "boots": "boots",
    "leather shoes": "leather shoes",
    "sandals": "sandals",
    "a belt": "belt",
    "a scarf": "scarf",
    "a cap": "cap",
    "a bag": "bag",
    "a watch": "watch",
}


def expand_prompts(prompts: list[str], templates: list[str] | None = None) -> list[str]:
    """Every prompt formatted into every template, prompt-major order
    (`[p0*t0, p0*t1, p1*t0, ...]`). VIS-REQ-011 ensemble input."""
    used = PROMPT_TEMPLATES if templates is None else templates
    return [t.format(p) for p in prompts for t in used]
