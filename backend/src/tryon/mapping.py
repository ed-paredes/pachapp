"""Garment category -> CatVTON cloth type, and the pass plan (09-virtual-tryon.md §5.2, §5.3).

Pure and torch-free: the API plans passes (to answer 422 / `skipped_garment_ids` and to build the
cache key) without loading anything. CatVTON dresses one garment per pass; this module decides
which garments get a pass and in which order.

Plan rules:
- Pass order is `overall`, or `lower` then the upper layers inner -> outer
  (`top`, `mid_layer`, `outerwear`).
- `shoes`, `accessory` and a missing category are never dressed (`unsupported_garment_ids`).
- Ambiguous inputs are resolved deterministically by input order: a repeated garment id counts
  once; of several garments in the same category only the first is kept (the rest are skipped);
  a one-piece wins over `bottom` and `top` (a dress already covers them; the bottoms and tops are
  skipped), while a `mid_layer` or `outerwear` over it still gets its pass; with several
  one-pieces, the first is kept.
- When there are more passes than `max_passes`, the base pass (`overall` or `lower`) is kept and
  the upper layers compete for the remaining slots: the innermost and the outermost survive and
  the intermediate ones are skipped; with a single slot left only the outermost survives.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from shared.enums import GarmentCategory


class ClothType(StrEnum):
    """CatVTON `cloth_type`; the value is also the mannequin mask name (`mask_<value>.png`)."""

    upper = "upper"
    lower = "lower"
    overall = "overall"


# The single place where the app's categories meet CatVTON's cloth types (§5.2, §12.8).
CATEGORY_CLOTH_TYPE: dict[GarmentCategory, ClothType | None] = {
    GarmentCategory.top: ClothType.upper,
    GarmentCategory.mid_layer: ClothType.upper,
    GarmentCategory.outerwear: ClothType.upper,
    GarmentCategory.bottom: ClothType.lower,
    GarmentCategory.one_piece: ClothType.overall,
    GarmentCategory.shoes: None,
    GarmentCategory.accessory: None,
}

# Upper layers from the body outwards.
_UPPER_LAYERS = (GarmentCategory.top, GarmentCategory.mid_layer, GarmentCategory.outerwear)


def cloth_type(category: GarmentCategory | None) -> ClothType | None:
    """The cloth type for `category`, or None when it is not dressed on the mannequin."""
    return CATEGORY_CLOTH_TYPE.get(category) if category is not None else None


@dataclass(frozen=True)
class PlanGarment:
    id: str
    category: GarmentCategory | None


@dataclass(frozen=True)
class Pass:
    garment_id: str
    cloth_type: ClothType


@dataclass(frozen=True)
class PassPlan:
    passes: tuple[Pass, ...]
    skipped_garment_ids: tuple[str, ...]
    unsupported_garment_ids: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """Nothing compatible to dress (the API answers 422)."""
        return not self.passes

    @property
    def garment_ids(self) -> tuple[str, ...]:
        """Dressed garment ids in pass order."""
        return tuple(p.garment_id for p in self.passes)


def plan_passes(garments: Iterable[PlanGarment], max_passes: int) -> PassPlan:
    """Plan the CatVTON passes for `garments` (any order); rules in the module docstring."""
    first_by_category: dict[GarmentCategory, str] = {}
    skipped: set[str] = set()
    unsupported: list[str] = []
    input_order: list[str] = []  # unique ids, as given

    for garment in garments:
        if garment.id in input_order:
            continue
        input_order.append(garment.id)
        if cloth_type(garment.category) is None:
            unsupported.append(garment.id)
        elif garment.category in first_by_category:
            skipped.add(garment.id)
        else:
            assert garment.category is not None
            first_by_category[garment.category] = garment.id

    base: list[Pass] = []
    one_piece = first_by_category.get(GarmentCategory.one_piece)
    layers = [c for c in _UPPER_LAYERS if c in first_by_category]
    if one_piece is not None:
        base.append(Pass(one_piece, ClothType.overall))
        if GarmentCategory.bottom in first_by_category:
            skipped.add(first_by_category[GarmentCategory.bottom])
        if GarmentCategory.top in layers:
            skipped.add(first_by_category[GarmentCategory.top])
            layers.remove(GarmentCategory.top)
    elif GarmentCategory.bottom in first_by_category:
        base.append(Pass(first_by_category[GarmentCategory.bottom], ClothType.lower))

    slots = max(max_passes - len(base), 0)
    if len(layers) > slots:
        kept = layers[: slots - 1] + layers[-1:] if slots >= 1 else []
        skipped.update(first_by_category[c] for c in layers if c not in kept)
        layers = kept
    uppers = [Pass(first_by_category[c], ClothType.upper) for c in layers]

    passes = tuple(base + uppers)
    # Report in input order so the response is stable and easy to compare with the request.
    ordered_skipped = tuple(gid for gid in input_order if gid in skipped)
    return PassPlan(passes, ordered_skipped, tuple(unsupported))
