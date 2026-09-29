"""shared.imaging: decode/validate/encode helpers (ING-REQ-002/003/009)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from shared.imaging import (
    ImageTooLargeError,
    InvalidImageError,
    decode_image,
    encode_jpeg,
    make_thumbnail,
)

_EXIF_ORIENTATION = 0x0112


def _jpeg(size: tuple[int, int], *, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    if orientation is not None:
        exif[_EXIF_ORIENTATION] = orientation
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_decode_applies_exif_orientation() -> None:
    # Stored 40x20 with orientation 6 (rotate 90 CW) displays as 20x40.
    image = decode_image(_jpeg((40, 20), orientation=6), max_long_side=100)

    assert image.size == (20, 40)


def test_decode_accepts_file_object() -> None:
    image = decode_image(io.BytesIO(_jpeg((30, 10))), max_long_side=100)

    assert image.size == (30, 10)


@pytest.mark.parametrize("payload", [b"", b"not an image at all", b"\xff\xd8\xff\xe0garbage"])
def test_decode_rejects_undecodable_bytes(payload: bytes) -> None:
    with pytest.raises(InvalidImageError):
        decode_image(payload, max_long_side=100)


def test_decode_rejects_truncated_image() -> None:
    with pytest.raises(InvalidImageError):
        decode_image(_jpeg((200, 200))[:120], max_long_side=1000)


def test_decode_rejects_oversized_long_side() -> None:
    with pytest.raises(ImageTooLargeError) as info:
        decode_image(_jpeg((101, 20)), max_long_side=100)

    assert info.value.long_side == 101
    assert info.value.max_long_side == 100


def test_decode_allows_exactly_max_long_side() -> None:
    assert decode_image(_jpeg((100, 20)), max_long_side=100).size == (100, 20)


def test_encode_jpeg_flattens_alpha_onto_white() -> None:
    rgba = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

    decoded = Image.open(io.BytesIO(encode_jpeg(rgba)))

    assert decoded.format == "JPEG"
    assert decoded.convert("RGB").getpixel((4, 4)) == (255, 255, 255)


def test_make_thumbnail_is_webp_with_bounded_long_side() -> None:
    thumb = Image.open(io.BytesIO(make_thumbnail(Image.new("RGB", (800, 400)), 100)))

    assert thumb.format == "WEBP"
    assert thumb.size == (100, 50)


def test_make_thumbnail_does_not_upscale_and_keeps_alpha() -> None:
    thumb = Image.open(io.BytesIO(make_thumbnail(Image.new("RGBA", (30, 20), (1, 2, 3, 0)), 100)))

    assert thumb.size == (30, 20)
    assert "A" in thumb.getbands()
