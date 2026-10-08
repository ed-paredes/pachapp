"""`tryon.images` helpers: the CatVTON input preparation shared with the V0 spike."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from tryon.images import (
    GarmentError,
    fit_crop,
    is_blank,
    prepare_garment,
    prepare_mask,
    prepare_person,
)


def test_fit_crop_centre_crops_to_the_target_aspect() -> None:
    # 40x20 landscape into a 10x20 portrait: the middle 10x20 band survives.
    image = Image.new("RGB", (40, 20), (0, 0, 255))
    image.paste((255, 0, 0), (15, 0, 25, 20))
    out = fit_crop(image, (10, 20), Image.Resampling.NEAREST)
    assert out.size == (10, 20)
    assert set(out.getdata()) == {(255, 0, 0)}


def test_fit_crop_crops_height_for_a_wide_target() -> None:
    image = Image.new("RGB", (20, 40), (0, 0, 255))
    image.paste((0, 255, 0), (0, 15, 20, 25))
    out = fit_crop(image, (20, 10), Image.Resampling.NEAREST)
    assert out.size == (20, 10)
    assert set(out.getdata()) == {(0, 255, 0)}


def test_prepare_person_is_rgb_at_the_working_size() -> None:
    out = prepare_person(Image.new("RGBA", (30, 50), (1, 2, 3, 255)), (24, 32))
    assert out.mode == "RGB" and out.size == (24, 32)


def test_prepare_mask_binarises_and_blurs() -> None:
    mask = Image.new("L", (32, 32), 0)
    mask.paste(200, (8, 8, 24, 24))  # >= 128 counts as masked
    mask.paste(100, (0, 0, 4, 4))  # below the threshold: dropped
    sharp = prepare_mask(mask, (32, 32), blur=0)
    assert set(sharp.getdata()) == {0, 255}
    assert sharp.getpixel((1, 1)) == 0 and sharp.getpixel((16, 16)) == 255
    soft = prepare_mask(mask, (32, 32))
    assert len(set(soft.getdata())) > 2  # blurred edge
    assert soft.size == (32, 32) and soft.mode == "L"


def test_prepare_garment_photo_is_returned_as_rgb() -> None:
    assert prepare_garment(Image.new("L", (10, 10), 5)).mode == "RGB"
    opaque = prepare_garment(Image.new("RGBA", (10, 12), (9, 8, 7, 255)))
    assert opaque.mode == "RGB" and opaque.size == (10, 12)


def test_prepare_garment_cutout_is_cropped_and_put_on_white() -> None:
    cutout = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    cutout.paste((200, 0, 0, 255), (40, 40, 60, 80))  # 20x40 opaque block
    out = prepare_garment(cutout, margin=0.05)
    pad = round(40 * 0.05)
    assert out.size == (20 + 2 * pad, 40 + 2 * pad)
    assert out.getpixel((0, 0)) == (255, 255, 255)
    assert out.getpixel((out.width // 2, out.height // 2)) == (200, 0, 0)


def test_prepare_garment_rejects_a_fully_transparent_cutout() -> None:
    with pytest.raises(GarmentError):
        prepare_garment(Image.new("RGBA", (10, 10), (1, 2, 3, 0)))


def test_is_blank() -> None:
    assert is_blank(Image.new("RGB", (16, 16), (0, 0, 0)))
    noisy = Image.fromarray(np.tile(np.array([0, 255], dtype=np.uint8), (16, 8)))
    assert not is_blank(noisy)
