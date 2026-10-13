"""Turn a dressed try-on render into a featureless dummy (odd/tasks/tryon-dummy.md, V6c).

Port of the V6 spike (`~/pachapp-data/eval-results/tryon-v6-dummy-2026-10-12/v6_dummy.py`,
look "flat", alpha from SegFormer, hair transparent): crop from the chin to the ankle, cut the
person out of the backdrop, drop the hair below the chin and paint the skin (face/neck, arms,
legs) with one flat matte tone whose low-frequency luminance keeps a faint +-12% volume.

Pure numpy/PIL/scipy, no torch: the label map comes from a parser (`ml.garment_parse`) and is
passed in. `cut_out` does the tone-independent work once per render; `recolour` is a cheap
multiply, run once per skin tone.

Sizes scale with the render height (the constants below are tuned at 576x768).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from PIL import Image
from scipy import ndimage

if TYPE_CHECKING:  # keeps the API process (which imports DUMMY_VERSION) free of the ML stack
    from ml.garment_parse import ParseResult

# Bump when the look or the cut changes: it joins the render cache key, so old renders are not
# served as the new look.
DUMMY_VERSION: Final = "dummy-1"
# Cache-key / `params.postprocess` value of a render left as CatVTON produced it.
NO_POSTPROCESS: Final = "none"

REFERENCE_HEIGHT: Final = 768
# Output canvas ratio (width / height): 3:4, as the render.
CANVAS_RATIO: Final = 0.75
# The figure fills at most this share of the canvas height / width, and stands 5% above the bottom.
FIT_HEIGHT: Final = 0.90
FIT_WIDTH: Final = 0.92
BOTTOM_MARGIN: Final = 0.05
# Alpha above this (of 255) counts as figure when measuring the bounding box.
_BBOX_ALPHA: Final = 20 / 255
# A figure smaller than this share of the frame is a failed parse, not a person.
MIN_FIGURE_RATIO: Final = 0.02

# Shading: masked low-pass luminance, mapped to +-SHADE_BAND around the tone.
SHADE_SIGMA: Final = 14.0
SHADE_BAND: Final = 0.12
SKIN_FEATHER_SIGMA: Final = 1.2
ALPHA_FEATHER_SIGMA: Final = 0.8
HAIR_DILATION_PX: Final = 3
ANKLE_FADE_PX: Final = 3
# Shoe pixels in a row before it counts as the shoe top (a stray label does not).
_SHOE_ROW_MIN_PX: Final = 3

_SKIN_CLASSES: Final = frozenset({"face", "left_arm", "right_arm", "left_leg", "right_leg"})
_SHOE_CLASSES: Final = frozenset({"left_shoe", "right_shoe"})
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


class DummyError(Exception):
    """The render cannot be turned into a dummy (bad calibration, empty parse, ...)."""


class NoFigureError(DummyError):
    """The parse found no person to cut out."""


@dataclass(frozen=True)
class DummyMeta:
    """Calibrated cut lines of a base mannequin (`meta.json` `dummy`), as ratios of the render
    height: `chin` is the row the head is cut at; the ankle is the first shoe row, or
    `ankle_fallback` when the parse finds no shoes."""

    chin: float
    ankle_fallback: float


def dummy_meta(meta: Mapping[str, Any]) -> DummyMeta:
    """Read the `dummy` block of a mannequin's `meta.json`; `DummyError` when it is missing or
    malformed (a base that was not calibrated cannot be turned into a dummy)."""
    block = meta.get("dummy")
    if not isinstance(block, dict):
        raise DummyError("the mannequin has no `dummy` calibration in meta.json")
    ankle = block.get("ankle")
    if not isinstance(ankle, dict) or ankle.get("rule") != "shoe_top":
        raise DummyError("`dummy.ankle.rule` must be 'shoe_top'")
    chin, fallback = block.get("chin"), ankle.get("fallback")
    for name, value in (("chin", chin), ("ankle.fallback", fallback)):
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value < 1:
            raise DummyError(f"`dummy.{name}` must be a ratio between 0 and 1, got {value!r}")
    assert isinstance(chin, int | float) and isinstance(fallback, int | float)
    if chin >= fallback:
        raise DummyError("`dummy.chin` must be above `dummy.ankle.fallback`")
    return DummyMeta(float(chin), float(fallback))


@dataclass(frozen=True)
class Prepared:
    """The cut-out, tone-independent part, all arrays (H x W) on the final canvas."""

    rgb: np.ndarray  # float32 H x W x 3, 0..255, the render's own colours
    alpha: np.ndarray  # float32 0..1
    skin: np.ndarray  # float32 0..1, feathered mask of the skin to repaint
    shade: np.ndarray  # float32, relative luminance offset in [-SHADE_BAND, SHADE_BAND]

    @property
    def size(self) -> tuple[int, int]:
        """(width, height)."""
        return self.alpha.shape[1], self.alpha.shape[0]

    def neutral(self) -> Image.Image:
        """The cut-out with the render's own skin (no recolour), RGBA."""
        return _rgba(self.rgb, self.alpha)


def _rgba(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    data = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(data, "RGBA")


def _blur(array: np.ndarray, sigma: float) -> np.ndarray:
    return ndimage.gaussian_filter(array, sigma)


def _shade(luma: np.ndarray, skin: np.ndarray, sigma: float) -> np.ndarray:
    """Masked low-pass luminance of the skin, relative to its mean, scaled so its 95th
    percentile reaches the band edge."""
    weight = skin.astype(np.float32)
    mean = float((luma * weight).sum() / max(float(weight.sum()), 1.0))
    low = _blur(luma * weight, sigma) / (_blur(weight, sigma) + 1e-4)
    rel = (low - mean) / (mean + 1e-4)
    inside = weight > 0.5
    scale = float(np.percentile(np.abs(rel[inside]), 95)) + 1e-4 if inside.any() else 1.0
    return (np.clip(rel / scale, -1, 1) * SHADE_BAND).astype(np.float32)


def _ankle_row(parse: ParseResult, fallback: float, height: int) -> int:
    rows = np.where(parse.mask_for(_SHOE_CLASSES).sum(axis=1) > _SHOE_ROW_MIN_PX)[0]
    return int(rows[0]) if len(rows) else round(fallback * height)


def _resize(channel: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    resized = Image.fromarray(channel.astype(np.float32), "F").resize(
        size, Image.Resampling.LANCZOS
    )
    return np.asarray(resized, dtype=np.float32)


def cut_out(image: Image.Image, parse: ParseResult, meta: DummyMeta) -> Prepared:
    """Cut the dressed render out of its backdrop, between the calibrated chin and the ankle.

    `parse` labels `image` at its own size. Raises `NoFigureError` when it holds no person and
    `DummyError` when the cut lines do not fit the image."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = rgb.shape[:2]
    if parse.labels.shape != (height, width):
        raise DummyError(f"label map {parse.labels.shape} does not match the image {rgb.shape[:2]}")
    scale = height / REFERENCE_HEIGHT

    foreground = ~parse.mask_for({"background"})
    if foreground.mean() < MIN_FIGURE_RATIO:
        raise NoFigureError("the parse found no person in the render")
    skin = parse.mask_for(_SKIN_CLASSES)
    # Hair below the chin goes (long hair would hang over the shoulders as a dark mass).
    hair = ndimage.binary_dilation(
        parse.mask_for({"hair"}), iterations=max(1, round(HAIR_DILATION_PX * scale))
    )
    hair &= ~skin

    chin = round(meta.chin * height)
    ankle = _ankle_row(parse, meta.ankle_fallback, height)
    if not 0 <= chin < ankle <= height:
        raise DummyError(f"cut lines chin={chin} ankle={ankle} do not fit {height} rows")

    alpha = foreground.astype(np.float32)
    alpha[hair] = 0
    alpha = np.clip(_blur(alpha, ALPHA_FEATHER_SIGMA * scale), 0, 1)
    alpha[:chin] = 0
    alpha[ankle:] = 0
    fade = max(1, round(ANKLE_FADE_PX * scale))
    for i in range(min(fade, ankle - chin)):
        alpha[ankle - 1 - i] *= (i + 1) / (fade + 1)

    box = np.argwhere(alpha > _BBOX_ALPHA)
    if len(box) == 0:
        raise NoFigureError("nothing of the figure is left between the chin and the ankle")
    top, left = box.min(axis=0)
    bottom, right = box.max(axis=0) + 1

    skin_soft = np.clip(_blur(skin.astype(np.float32), SKIN_FEATHER_SIGMA * scale), 0, 1)
    shade = _shade(rgb @ _LUMA / 255.0, skin, SHADE_SIGMA * scale)

    window = (slice(top, bottom), slice(left, right))
    crop_h, crop_w = int(bottom - top), int(right - left)
    canvas_h = height
    canvas_w = round(canvas_h * CANVAS_RATIO)
    fit = min(FIT_HEIGHT * canvas_h / crop_h, FIT_WIDTH * canvas_w / crop_w)
    new_w, new_h = max(1, round(crop_w * fit)), max(1, round(crop_h * fit))
    x0 = (canvas_w - new_w) // 2
    y0 = canvas_h - new_h - round(BOTTOM_MARGIN * canvas_h)

    def place(channel: np.ndarray) -> np.ndarray:
        out = np.zeros((canvas_h, canvas_w), dtype=np.float32)
        out[y0 : y0 + new_h, x0 : x0 + new_w] = _resize(channel[window], (new_w, new_h))
        return out

    new_alpha = np.clip(place(alpha), 0, 1)
    # Colours are resized premultiplied so the backdrop behind the edge does not bleed in.
    premult = np.dstack([place(rgb[..., c] * alpha) for c in range(3)])
    new_rgb = np.clip(premult / np.maximum(new_alpha, 1e-3)[..., None], 0, 255)
    return Prepared(
        rgb=new_rgb.astype(np.float32),
        alpha=new_alpha,
        skin=np.clip(place(skin_soft), 0, 1),
        shade=np.clip(place(shade), -SHADE_BAND, SHADE_BAND),
    )


def recolour(prepared: Prepared, tone_hex: str) -> Image.Image:
    """The cut-out with its skin painted in `tone_hex` (flat matte plus the faint volume)."""
    if not _HEX.fullmatch(tone_hex):
        raise ValueError(f"tone must be a #RRGGBB colour, got {tone_hex!r}")
    tone = np.array([int(tone_hex[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)
    paint = np.clip(tone[None, None, :] * (1 + prepared.shade)[..., None], 0, 255)
    skin = prepared.skin[..., None]
    return _rgba(prepared.rgb * (1 - skin) + paint * skin, prepared.alpha)
