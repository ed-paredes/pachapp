"""Synthetic figure for the try-on dummy tests: a label map and a matching painted image."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ml.garment_parse import ParseResult

NAMES = {
    0: "background",
    2: "hair",
    4: "upper_clothes",
    6: "pants",
    9: "left_shoe",
    10: "right_shoe",
    11: "face",
    12: "left_leg",
    13: "right_leg",
    14: "left_arm",
    15: "right_arm",
}
COLOURS = {
    "background": (200, 200, 200),
    "hair": (10, 10, 10),
    "upper_clothes": (30, 60, 200),
    "pants": (200, 180, 60),
    "left_shoe": (20, 200, 20),
    "right_shoe": (20, 200, 20),
    "face": (150, 90, 80),
    "left_leg": (150, 90, 80),
    "right_leg": (150, 90, 80),
    "left_arm": (150, 90, 80),
    "right_arm": (150, 90, 80),
}
GARMENT = COLOURS["upper_clothes"]
HAIR = COLOURS["hair"]
SHOE = COLOURS["left_shoe"]
SKIN = COLOURS["face"]

# Reference frame 150 x 200 (the layout scales to any size): (label id, rows, cols).
_BOXES = (
    (2, (10, 40), (55, 95)),  # hair on the head
    (2, (62, 100), (30, 40)),  # hair hanging below the chin, apart from the body
    (11, (15, 70), (65, 85)),  # face, then a neck stub under the chin (row 60)
    (4, (62, 110), (50, 100)),  # top
    (14, (62, 110), (40, 50)),  # left arm
    (15, (62, 110), (100, 110)),  # right arm
    (6, (110, 150), (55, 95)),  # trousers
    (12, (150, 185), (60, 70)),  # legs
    (13, (150, 185), (80, 90)),
    (9, (185, 195), (58, 72)),  # shoes
    (10, (185, 195), (78, 92)),
)
CHIN_RATIO = 0.30  # row 60 of 200
ANKLE_FALLBACK = 0.93
META = {"dummy": {"chin": CHIN_RATIO, "ankle": {"rule": "shoe_top", "fallback": ANKLE_FALLBACK}}}


def figure_labels(width: int, height: int, *, shoes: bool = True) -> np.ndarray:
    labels = np.zeros((height, width), dtype=np.uint8)
    for label, (r0, r1), (c0, c1) in _BOXES:
        if not shoes and label in (9, 10):
            continue
        rows = slice(round(r0 * height / 200), round(r1 * height / 200))
        cols = slice(round(c0 * width / 150), round(c1 * width / 150))
        labels[rows, cols] = label
    return labels


def figure_parse(width: int, height: int, *, shoes: bool = True) -> ParseResult:
    return ParseResult(figure_labels(width, height, shoes=shoes), dict(NAMES))


def paint(parse: ParseResult) -> Image.Image:
    """The image the label map describes, each class in a flat colour."""
    rgb = np.zeros((*parse.labels.shape, 3), dtype=np.uint8)
    for label, name in parse.names.items():
        rgb[parse.labels == label] = COLOURS[name]
    return Image.fromarray(rgb, "RGB")


class FakeParser:
    """A `GarmentParser` that labels every image with the synthetic figure."""

    name = "fake"
    revision = None

    def __init__(self, *, error: Exception | None = None, empty: bool = False) -> None:
        self.error = error
        self.empty = empty
        self.parsed: list[tuple[int, int]] = []

    def parse(self, rgb: Image.Image) -> ParseResult:
        self.parsed.append(rgb.size)
        if self.error is not None:
            raise self.error
        if self.empty:
            return ParseResult(np.zeros((rgb.height, rgb.width), dtype=np.uint8), dict(NAMES))
        return figure_parse(rgb.width, rgb.height)

    def close(self) -> None:
        pass
