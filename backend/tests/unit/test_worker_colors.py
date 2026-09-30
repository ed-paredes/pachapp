"""worker.colors: CIELAB/CIEDE2000 and palette extraction (ING-REQ-010..014)."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from shared.schemas import Colors
from worker.colors import (
    ALPHA_THRESHOLD,
    NEUTRAL_NAMES,
    PALETTE,
    ciede2000,
    extract_colors,
    nearest_palette_name,
    srgb_to_lab,
)

# Sharma, Wu & Dalal (2005) CIEDE2000 test data: (lab1, lab2, expected dE00).
SHARMA_PAIRS = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 2.5, 0.0), (50.0, 0.0, -2.5), 4.3065),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((50.0, 2.5, 0.0), (61.0, -5.0, 29.0), 22.8977),
    ((50.0, 2.5, 0.0), (56.0, -27.0, -3.0), 31.9030),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


def _solid(rgb: tuple[int, int, int], size: tuple[int, int] = (20, 20), alpha: int = 255):
    return Image.new("RGBA", size, (*rgb, alpha))


def _split(left: tuple[int, int, int], right: tuple[int, int, int], left_cols: int, total: int):
    """`total`x10 image whose first `left_cols` columns are `left`, rest `right`."""
    image = Image.new("RGBA", (total, 10), (*right, 255))
    image.paste(Image.new("RGBA", (left_cols, 10), (*left, 255)), (0, 0))
    return image


# --- colour science -----------------------------------------------------


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA_PAIRS)
def test_ciede2000_matches_sharma_reference(lab1, lab2, expected) -> None:
    assert float(ciede2000(np.array(lab1), np.array(lab2))) == pytest.approx(expected, abs=1e-4)
    # symmetric
    assert float(ciede2000(np.array(lab2), np.array(lab1))) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_broadcasts_over_arrays() -> None:
    result = ciede2000(
        np.array([[50.0, 2.5, 0.0]]), np.array([[50.0, 0.0, -2.5], [50.0, 2.5, 0.0]])
    )
    assert result.shape == (2,)
    assert result[1] == pytest.approx(0.0)


def test_srgb_to_lab_reference_points() -> None:
    lab = srgb_to_lab(np.array([[0, 0, 0], [255, 255, 255], [255, 0, 0]]))
    assert lab[0] == pytest.approx([0, 0, 0], abs=0.01)
    assert lab[1] == pytest.approx([100, 0, 0], abs=0.01)
    assert lab[2] == pytest.approx([53.24, 80.09, 67.20], abs=0.05)


def test_palette_has_the_twenty_names_and_names_itself() -> None:
    assert len(PALETTE) == 20
    for name, rgb in PALETTE.items():
        assert nearest_palette_name(srgb_to_lab(np.array(rgb))) == name


def test_neutral_names_match_the_spec() -> None:
    assert {"negro", "blanco", "gris", "beige", "camel", "marino", "denim"} == NEUTRAL_NAMES
    assert set(PALETTE) >= NEUTRAL_NAMES


# --- extraction ---------------------------------------------------------


def test_solid_colour_is_a_single_dominant_entry() -> None:
    result = extract_colors(_solid((200, 30, 40)))

    assert [c.name for c in result.colors.root] == ["rojo"]
    assert result.colors.root[0].proportion == pytest.approx(1.0)
    assert result.colors.root[0].hex == "#c81e28"
    assert result.is_neutral is False
    assert result.confidence == pytest.approx(1.0)


def test_neutral_dominant_sets_is_neutral() -> None:
    assert extract_colors(_solid((20, 30, 80))).is_neutral is True  # marino
    assert extract_colors(_solid((245, 245, 243))).is_neutral is True  # blanco


def test_two_colours_are_sorted_with_expected_proportions() -> None:
    result = extract_colors(_split((200, 30, 40), (30, 90, 220), left_cols=6, total=10))

    names = [c.name for c in result.colors.root]
    assert names == ["rojo", "azul"]
    assert [c.proportion for c in result.colors.root] == pytest.approx([0.6, 0.4])
    assert result.is_neutral is False
    assert result.confidence > 0.9


def test_dominance_decides_is_neutral() -> None:
    result = extract_colors(_split((20, 30, 80), (200, 30, 40), left_cols=7, total=10))
    assert result.colors.root[0].name == "marino"
    assert result.is_neutral is True


def test_transparent_pixels_are_ignored() -> None:
    image = _split((200, 30, 40), (30, 90, 220), left_cols=5, total=10)
    pixels = np.array(image)
    pixels[:, 5:, 3] = ALPHA_THRESHOLD  # not strictly above the threshold
    result = extract_colors(Image.fromarray(pixels, "RGBA"))

    assert [c.name for c in result.colors.root] == ["rojo"]
    assert result.colors.root[0].proportion == pytest.approx(1.0)


def test_cluster_under_ten_percent_is_dropped() -> None:
    result = extract_colors(_split((245, 245, 243), (200, 30, 40), left_cols=19, total=20))

    assert [c.name for c in result.colors.root] == ["blanco"]
    assert result.colors.root[0].proportion == pytest.approx(0.95)  # sum <= 1, not renormalised


def test_clusters_with_the_same_name_are_merged() -> None:
    image = _split((20, 30, 80), (26, 36, 92), left_cols=5, total=10)  # two navies

    result = extract_colors(image)

    assert [c.name for c in result.colors.root] == ["marino"]
    assert result.colors.root[0].proportion == pytest.approx(1.0)


def test_fully_transparent_image_has_no_colours_and_zero_confidence() -> None:
    result = extract_colors(_solid((200, 30, 40), alpha=0))

    assert result.colors.root == []
    assert result.confidence == 0.0
    assert result.is_neutral is None


def test_extraction_is_deterministic_on_large_noisy_input() -> None:
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 256, (300, 300, 4), dtype=np.uint8)
    noise[..., 3] = 255
    image = Image.fromarray(noise, "RGBA")

    first, second = extract_colors(image), extract_colors(image)

    assert first.colors == second.colors
    assert first.confidence == second.confidence


def test_output_validates_against_the_colors_schema() -> None:
    result = extract_colors(_split((200, 30, 40), (30, 90, 220), left_cols=6, total=10))

    dumped = result.colors.model_dump(mode="json")
    assert Colors.model_validate(dumped) == result.colors
    assert sum(c["proportion"] for c in dumped) <= 1 + 1e-6
    assert all(c["hex"].startswith("#") and len(c["hex"]) == 7 for c in dumped)


# --- confidence monotonicity (ING-REQ-014) ------------------------------


def test_tight_clusters_score_higher_than_diffuse_ones() -> None:
    rng = np.random.default_rng(0)
    flat = _split((200, 30, 40), (30, 90, 220), left_cols=50, total=100)
    noisy = np.array(flat).astype(np.int16)
    noisy[..., :3] += rng.normal(0, 45, noisy[..., :3].shape).astype(np.int16)
    diffuse = Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8), "RGBA")

    assert extract_colors(flat).confidence > extract_colors(diffuse).confidence


def test_well_separated_clusters_score_higher_than_close_ones() -> None:
    far = _split((0, 0, 0), (255, 255, 255), left_cols=5, total=10)  # negro / blanco
    close = _split((222, 205, 175), (193, 154, 107), left_cols=5, total=10)  # beige / camel

    far_result, close_result = extract_colors(far), extract_colors(close)

    assert far_result.confidence > close_result.confidence
    assert 0.0 <= close_result.confidence <= 1.0
