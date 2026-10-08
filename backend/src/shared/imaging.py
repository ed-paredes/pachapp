"""Image decoding, validation and encoding helpers shared by `api` and `worker`.

docs/specs/03-garment-ingestion.md: ING-REQ-002 (decodable + hard size cap),
ING-REQ-003 (EXIF-corrected original), ING-REQ-009 (thumbnail layout).

Pure Pillow: this module must never import `ml`, torch, open_clip or rembg
(VIS-REQ-004/005), so the API process can use it.
"""

from __future__ import annotations

import io
from typing import BinaryIO

from PIL import Image, ImageOps

JPEG_QUALITY = 92
WEBP_QUALITY = 85


class InvalidImageError(ValueError):
    """The payload is not a decodable image (ING-REQ-002)."""


class ImageTooLargeError(ValueError):
    """The image's long side exceeds the hard cap (ING-REQ-002)."""

    def __init__(self, long_side: int, max_long_side: int) -> None:
        super().__init__(f"long side {long_side}px exceeds the {max_long_side}px limit")
        self.long_side = long_side
        self.max_long_side = max_long_side


def decode_image(source: bytes | BinaryIO, *, max_long_side: int) -> Image.Image:
    """Decode `source`, apply EXIF orientation and enforce `max_long_side`.

    The size is checked from the header before pixels are decoded, so absurd
    dimensions are rejected cheaply. Returns a fully loaded image (ING-REQ-003).
    """
    stream = io.BytesIO(source) if isinstance(source, bytes | bytearray) else source
    try:
        with Image.open(stream) as opened:
            long_side = max(opened.size)
            if long_side > max_long_side:
                raise ImageTooLargeError(long_side, max_long_side)
            opened.load()
            return ImageOps.exif_transpose(opened) or opened.copy()
    except ImageTooLargeError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError(0, max_long_side) from exc
    except Exception as exc:  # noqa: BLE001 - decoders/EXIF parsers raise KeyError, TypeError, struct.error...
        # R3-004: any decoder failure on untrusted bytes is a client error, never a 500.
        raise InvalidImageError("payload is not a decodable image") from exc


def to_rgb(image: Image.Image) -> Image.Image:
    """Return an RGB copy; transparency is flattened onto white (JPEG has no alpha)."""
    if image.mode == "RGB":
        return image
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def encode_jpeg(image: Image.Image) -> bytes:
    """JPEG bytes of `image` converted to RGB."""
    buffer = io.BytesIO()
    to_rgb(image).save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def make_thumbnail(image: Image.Image, thumb_px: int) -> bytes:
    """WebP bytes whose long side is at most `thumb_px` (never upscaled)."""
    thumb = image.copy()
    thumb.thumbnail((thumb_px, thumb_px), Image.Resampling.LANCZOS)
    if thumb.mode not in ("RGB", "RGBA"):
        thumb = thumb.convert("RGBA" if "A" in thumb.getbands() else "RGB")
    buffer = io.BytesIO()
    thumb.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def encode_webp(image: Image.Image) -> bytes:
    """Full-size lossy WebP bytes of `image` (try-on renders); alpha is kept if present."""
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()
