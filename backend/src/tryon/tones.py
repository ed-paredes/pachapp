"""Model settings for the try-on dummy: the genders and the skin-tone palette.

Torch-free, shared by the settings API, the capabilities endpoint and (V6c) the worker, which
recolours the dummy once per tone.
"""

from __future__ import annotations

from typing import Final, Literal

Gender = Literal["woman", "man"]

GENDERS: Final[tuple[Gender, ...]] = ("woman", "man")
DEFAULT_GENDER: Final[Gender] = "woman"

# Ordered light to dark; the id is what the settings store.
SKIN_TONES: Final[tuple[tuple[int, str], ...]] = (
    (1, "#F3DBC8"),
    (2, "#E5BF9E"),
    (3, "#CF9D77"),
    (4, "#AE7650"),
    (5, "#85532F"),
    (6, "#583522"),
)
DEFAULT_SKIN_TONE: Final = 3
MIN_SKIN_TONE: Final = SKIN_TONES[0][0]
MAX_SKIN_TONE: Final = SKIN_TONES[-1][0]
