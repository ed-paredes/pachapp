"""Colour-palette facts shared by the worker and the API (ING-REQ-013).

Lives in `shared` so `api` can recompute `is_neutral` after a colour edit
without importing `worker` (and never `ml`).
"""

from __future__ import annotations

from shared.schemas import Colors

# ING-REQ-013: palette names that count as neutral.
NEUTRAL_NAMES = frozenset({"negro", "blanco", "gris", "beige", "camel", "marino", "denim"})


def is_neutral(colors: Colors) -> bool:
    """`True` when the dominant colour (first entry) is a neutral palette name."""
    return bool(colors.root) and colors.root[0].name in NEUTRAL_NAMES
