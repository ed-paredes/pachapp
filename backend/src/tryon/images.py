"""Image preparation shared by the try-on engine and the V0 spike (09-virtual-tryon.md §5).

Pure PIL/numpy helpers, no torch: they build the three CatVTON inputs (person, mask,
garment) at the working size and detect the all-black image fp16 NaNs decode to.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

# app.py blurs the AutoMasker mask with VaeImageProcessor.blur(blur_factor=9) before
# inference; the pipeline then binarises it at 0.5.
MASK_BLUR = 9
# Margin (share of the longest side) kept around a cutout before CatVTON pads it.
GARMENT_MARGIN = 0.05
# Output with a near-flat colour (std below this, 0-255 scale): fp16 NaNs decode to black.
BLANK_STD = 2.0


class GarmentError(ValueError):
    """The garment image cannot be used (e.g. a fully transparent cutout)."""


def fit_crop(image: Image.Image, size: tuple[int, int], resample: int) -> Image.Image:
    """Centre-crop to `size`'s aspect ratio, then resize (CatVTON `resize_and_crop` math)."""
    w, h = image.size
    target_w, target_h = size
    if w / h < target_w / target_h:
        new_w, new_h = w, w * target_h // target_w
    else:
        new_w, new_h = h * target_w // target_h, h
    left, top = (w - new_w) // 2, (h - new_h) // 2
    return image.crop((left, top, left + new_w, top + new_h)).resize(size, resample)


def prepare_person(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """RGB person at the working size (width, height)."""
    return fit_crop(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def prepare_mask(mask: Image.Image, size: tuple[int, int], blur: int = MASK_BLUR) -> Image.Image:
    """Mask at the working size, binarised then blurred like CatVTON's app.py."""
    fitted = fit_crop(mask.convert("L"), size, Image.Resampling.NEAREST)
    binary = fitted.point(lambda v: 255 if v >= 128 else 0)
    return binary.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else binary


def prepare_garment(image: Image.Image, margin: float = GARMENT_MARGIN) -> Image.Image:
    """RGB garment input: a cutout is cropped to its opaque area (plus `margin`) and
    composited on white (§5.4); a photo without transparency is returned as is.
    CatVTON then pads it to the working size with white (`resize_and_padding`)."""
    if image.mode not in ("RGBA", "LA", "P"):
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] == 255:  # fully opaque: a photo stored as PNG
        return rgba.convert("RGB")
    box = alpha.point(lambda a: 255 if a > 0 else 0).getbbox()
    if box is None:
        raise GarmentError("garment cutout is fully transparent")
    rgba = rgba.crop(box)
    pad = round(max(rgba.size) * margin)
    canvas = Image.new("RGB", (rgba.width + 2 * pad, rgba.height + 2 * pad), (255, 255, 255))
    canvas.paste(rgba, (pad, pad), rgba)
    return canvas


def is_blank(image: Image.Image, threshold: float = BLANK_STD) -> bool:
    return float(np.asarray(image.convert("L"), dtype=np.float32).std()) < threshold
