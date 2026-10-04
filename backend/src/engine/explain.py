"""One-sentence Spanish explanations from templates (ENG-REQ-018).

The 1-2 components with the largest weighted contribution pick the template;
when the runner-up is close behind, both sentences are joined.
"""

from __future__ import annotations

from collections import Counter

from engine import constants as C
from engine.context import Context
from engine.scoring import Array

_STYLE_ES = {
    "casual": "casual",
    "classic": "clásico",
    "street": "urbano",
    "minimal": "minimalista",
    "sport": "deportivo",
    "elegant": "elegante",
    "bohemian": "bohemio",
    "preppy": "preppy",
}

_ORDER = ("color", "style", "novelty", "preference")


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _color_sentence(ctx: Context, members: list[int], color_score: float) -> str:
    clothing = [ctx.garments[i] for i in members if ctx.slot[i] != "accessory"]
    names: list[str] = []
    for g in clothing:
        if g.colors and g.colors[0].name not in names:
            names.append(g.colors[0].name)
    non_neutral = [
        n
        for n in names
        if any(g.colors and g.colors[0].name == n and g.is_neutral is False for g in clothing)
    ]
    if len(non_neutral) >= 2:
        first, second = non_neutral[0], non_neutral[1]
        if color_score >= C.HUE_SCORE_ANALOGOUS - 1e-9:
            relation = "tonos análogos que armonizan"
        elif color_score >= C.HUE_SCORE_COMPLEMENTARY - 1e-9:
            relation = "colores complementarios con contraste"
        else:
            relation = "un contraste de color atrevido"
        return _capitalize(f"{first} y {second}: {relation}.")
    if len(non_neutral) == 1:
        return _capitalize(f"{non_neutral[0]} con neutros: una combinación fácil.")
    if len(names) >= 2:
        return _capitalize(f"{names[0]} y {names[1]}: neutros clásicos.")
    if names:
        return _capitalize(f"Look en {names[0]} de una sola tonalidad.")
    return "Una combinación de colores sencilla."


def _novelty_sentence(ctx: Context, members: list[int]) -> str:
    oldest = max(members, key=lambda i: (ctx.days_since[i], -i))
    garment = ctx.garments[oldest]
    name = (garment.subcategory or "").strip() or ctx.slot[oldest].replace("_", " ")
    days = int(ctx.days_since[oldest])
    if days >= C.NEVER_WORN_DAYS:
        return f"Todavía no has estrenado tu {name}."
    if days >= 14:
        return f"Hace {days // 7} semanas que no usas tu {name}."
    if days >= 7:
        return f"Hace 1 semana que no usas tu {name}."
    if days == 1:
        return f"Hace 1 día que no usas tu {name}."
    return f"Hace {days} días que no usas tu {name}."


def _style_sentence(ctx: Context, members: list[int]) -> str:
    tags = Counter(tag for i in members for tag in ctx.garments[i].style_tags)
    if not tags:
        return "Look coherente de arriba abajo."
    top = sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return f"Look {_STYLE_ES.get(top, top)} coherente de arriba abajo."


def explain(ctx: Context, members: list[int], comps: Array) -> str:
    """`comps` is the `(4,)` component vector of the proposal."""
    contribution = ctx.weights * comps
    candidates = [
        k for k in range(4) if _ORDER[k] != "preference" or comps[k] >= C.PREFERENCE_EXPLAIN_MIN
    ]
    ranked = sorted(candidates, key=lambda k: (-contribution[k], k))
    chosen = [ranked[0]]
    if (
        len(ranked) > 1
        and contribution[ranked[1]] >= C.EXPLANATION_TIE_RATIO * contribution[ranked[0]]
    ):
        chosen.append(ranked[1])
    sentences = []
    for k in chosen:
        name = _ORDER[k]
        if name == "color":
            sentences.append(_color_sentence(ctx, members, float(comps[0])))
        elif name == "style":
            sentences.append(_style_sentence(ctx, members))
        elif name == "novelty":
            sentences.append(_novelty_sentence(ctx, members))
        else:
            sentences.append("Combina prendas de looks que te gustaron.")
    return " ".join(sentences)
