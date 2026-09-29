"""Background removal (BiRefNet via `rembg`), 08-local-vision.md step 2.

`BiRefNetRemover.remove` returns an RGBA image cropped to the foreground
bounding box (03-garment-ingestion.md `cutout` step, ING-REQ-009). The pure
helpers (`alpha_coverage`, `crop_to_foreground`) are torch-free so they can be
unit-tested with synthetic PIL images (VIS-REQ-029).

Near-empty mask contract (ING-SCN-005): when the model finds (almost) no
foreground, `remove` raises `EmptyCutoutError` instead of returning a useless
crop. The worker's `cutout` step (plan step 4) MUST catch it and apply the
soft failure: fall back to the full preprocessed image as `img_cutout`, set
`needs_review=true`, and continue the pipeline rather than failing the job.

Callers MUST call `ml.cache.configure_model_cache` before the first `remove`
(VIS-REQ-008); the session comes from `ml.registry.get_background_remover`
(process-wide, lazy, VIS-REQ-004). `rembg` is imported inside `remove`.
"""

from __future__ import annotations

import logging
from typing import Protocol

from PIL import Image, ImageOps

from ml import registry
from shared.settings import Settings

logger = logging.getLogger(__name__)

# Alpha values strictly above this count as foreground, on the 0-255 scale
# (default, tunable). Matches the "opaque pixel" notion of ING-REQ-010.
OPACITY_THRESHOLD = 10

# Minimum fraction of pixels that must be foreground for a cutout to be
# considered usable: 0.5% of the image (default, tunable). Below this the mask
# is treated as empty (ING-SCN-005).
MIN_COVERAGE = 0.005


class EmptyCutoutError(Exception):
    """The background remover produced a near-empty mask (ING-SCN-005)."""

    def __init__(self, coverage: float, min_coverage: float = MIN_COVERAGE) -> None:
        self.coverage = coverage
        self.min_coverage = min_coverage
        super().__init__(
            f"Cutout mask is near-empty: foreground coverage {coverage:.4%} "
            f"is below the minimum {min_coverage:.4%}"
        )


class BackgroundRemover(Protocol):
    def remove(self, img: Image.Image) -> Image.Image:
        """Return an RGBA image cropped to the foreground bbox."""
        ...


def _foreground_mask(rgba: Image.Image, threshold: int) -> Image.Image:
    """Binary ("L", 0/255) mask of pixels whose alpha is above `threshold`."""
    return rgba.getchannel("A").point(lambda a: 255 if a > threshold else 0)


def alpha_coverage(rgba: Image.Image, threshold: int = OPACITY_THRESHOLD) -> float:
    """Fraction (0..1) of pixels whose alpha is strictly above `threshold`."""
    rgba = rgba.convert("RGBA")
    total = rgba.width * rgba.height
    if total == 0:
        return 0.0
    histogram = rgba.getchannel("A").histogram()
    opaque = sum(histogram[threshold + 1 :])
    return opaque / total


def crop_to_foreground(rgba: Image.Image, threshold: int = OPACITY_THRESHOLD) -> Image.Image:
    """Crop to the bbox of pixels with alpha above `threshold`.

    Raises `EmptyCutoutError` (coverage 0) if no pixel qualifies.
    """
    rgba = rgba.convert("RGBA")
    bbox = _foreground_mask(rgba, threshold).getbbox()
    if bbox is None:
        raise EmptyCutoutError(0.0)
    return rgba.crop(bbox)


def _to_rgb(img: Image.Image) -> Image.Image:
    """Normalize any PIL image to RGB: apply EXIF orientation if present and
    composite transparency (RGBA/LA/P with transparency) over white."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return img.convert("RGB")


class BiRefNetRemover:
    """`BackgroundRemover` backed by the process-wide BiRefNet `rembg` session."""

    def __init__(self, settings: Settings, min_coverage: float = MIN_COVERAGE) -> None:
        self._settings = settings
        self._min_coverage = min_coverage

    def remove(self, img: Image.Image) -> Image.Image:
        """Cut out the foreground and crop to its bbox (RGBA).

        Raises `EmptyCutoutError` when coverage is below `min_coverage`
        (ING-SCN-005); see the module docstring for the caller contract.
        """
        from rembg import remove

        session = registry.get_background_remover(self._settings)
        result = remove(_to_rgb(img), session=session)
        if not isinstance(result, Image.Image):
            raise TypeError(f"rembg.remove returned {type(result).__name__}, expected PIL image")
        rgba = result.convert("RGBA")
        coverage = alpha_coverage(rgba)
        if coverage < self._min_coverage:
            raise EmptyCutoutError(coverage, self._min_coverage)
        return crop_to_foreground(rgba)
