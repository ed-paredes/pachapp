"""The dummy cut-out and recolour (odd/tasks/tryon-dummy.md V6c): pure image maths on a synthetic
figure, no model."""

from __future__ import annotations

import numpy as np
import pytest
from dummy_fakes import (
    ANKLE_FALLBACK,
    CHIN_RATIO,
    GARMENT,
    HAIR,
    META,
    SHOE,
    SKIN,
    figure_parse,
    paint,
)
from PIL import Image

from ml.garment_parse import ParseResult
from tryon.dummy import (
    CANVAS_RATIO,
    DUMMY_VERSION,
    FIT_HEIGHT,
    DummyError,
    DummyMeta,
    NoFigureError,
    Prepared,
    cut_out,
    dummy_meta,
    recolour,
)
from tryon.tones import SKIN_TONES

W, H = 150, 200
LINES = DummyMeta(chin=CHIN_RATIO, ankle_fallback=ANKLE_FALLBACK)


def _prepare(*, shoes: bool = True, width: int = W, height: int = H) -> Prepared:
    parse = figure_parse(width, height, shoes=shoes)
    return cut_out(paint(parse), parse, LINES)


def _bbox(alpha: np.ndarray) -> tuple[int, int, int, int]:
    rows, cols = np.where(alpha > 0.5)
    return int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1


def _near(rgb: np.ndarray, colour: tuple[int, int, int], tol: float = 12) -> np.ndarray:
    return (np.abs(rgb - np.array(colour, dtype=np.float32)).max(axis=-1)) < tol


def test_output_is_a_three_by_four_canvas_with_a_transparent_backdrop() -> None:
    prepared = _prepare()

    width, height = prepared.size
    assert (width, height) == (round(H * CANVAS_RATIO), H)
    assert prepared.alpha[0, 0] == prepared.alpha[0, -1] == prepared.alpha[-1, 0] == 0
    assert prepared.alpha.max() == pytest.approx(1.0, abs=0.01)
    image = prepared.neutral()
    assert image.mode == "RGBA" and image.size == (width, height)


def test_the_cut_runs_from_the_chin_to_the_ankle() -> None:
    prepared = _prepare()
    top, bottom, left, right = _bbox(prepared.alpha)

    # Source figure between chin (row 60) and shoe top (row 185): 125 rows by the arm span (70).
    assert (bottom - top) / (right - left) == pytest.approx(125 / 70, rel=0.05)
    assert bottom - top == pytest.approx(FIT_HEIGHT * H, abs=2)  # fills the canvas height
    assert bottom == pytest.approx(H - 0.05 * H, abs=2)  # stands 5% above the bottom (fade row)
    rgb = prepared.rgb
    on = prepared.alpha > 0.9
    assert not (_near(rgb, SHOE) & on).any()  # shoes are below the ankle cut
    # The face above the chin is gone: the top rows are the neck stub, 20 px wide, not the head.
    top_width = int((prepared.alpha[top + 2] > 0.5).sum())
    assert top_width < 0.3 * (right - left)


def test_the_ankle_falls_back_to_the_calibrated_ratio_without_shoes() -> None:
    prepared = _prepare(shoes=False)
    top, bottom, left, right = _bbox(prepared.alpha)

    # chin row 60, fallback row 186 (0.93 * 200): the legs end at 185, so the figure is 125 rows.
    assert (bottom - top) / (right - left) == pytest.approx(125 / 70, rel=0.05)


def test_hair_below_the_chin_is_transparent_and_garments_keep_their_pixels() -> None:
    prepared = _prepare()
    on = prepared.alpha > 0.95

    assert not (_near(prepared.rgb, HAIR, 30) & (prepared.alpha > 0.5)).any()
    garment = _near(prepared.rgb, GARMENT) & on & (prepared.skin < 0.01)
    assert garment.sum() > 500  # the top is there, untouched by the recolour
    # The hanging hair sat left of the left arm: its columns are not part of the figure.
    top, bottom, left, right = _bbox(prepared.alpha)
    assert (right - left) / (bottom - top) == pytest.approx(70 / 125, rel=0.05)


def test_skin_takes_the_tone_flat_and_garments_are_unchanged() -> None:
    prepared = _prepare()
    garment_before = prepared.neutral()
    for _, tone in SKIN_TONES:
        out = np.asarray(recolour(prepared, tone), dtype=np.float32)
        wanted = np.array([int(tone[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)
        solid_skin = (prepared.skin > 0.99) & (prepared.alpha > 0.99)
        assert solid_skin.sum() > 200
        # The paint is the tone, modulated by the faint volume (at most +-12%).
        ratio = out[solid_skin][:, :3] / wanted
        assert ratio.min() >= 1 - 0.12 - 0.01 and ratio.max() <= 1 + 0.12 + 0.01
        garment = _near(prepared.rgb, GARMENT) & (prepared.skin < 0.01) & (prepared.alpha > 0.99)
        assert np.abs(out[garment][:, :3] - np.array(GARMENT)).max() < 12
    assert garment_before.getpixel((0, 0))[3] == 0
    # The neutral cut-out keeps the render's own skin.
    neutral = np.asarray(garment_before, dtype=np.float32)
    assert (
        _near(neutral[..., :3], SKIN, 12)[(prepared.skin > 0.99) & (prepared.alpha > 0.99)].mean()
        > 0.9
    )


def test_darker_tones_give_darker_skin() -> None:
    prepared = _prepare()
    solid = (prepared.skin > 0.99) & (prepared.alpha > 0.99)
    means = [np.asarray(recolour(prepared, hex_))[solid][:, :3].mean() for _, hex_ in SKIN_TONES]

    assert means == sorted(means, reverse=True)


def test_shading_keeps_a_faint_volume_within_twelve_percent() -> None:
    # Skin that is darker on the right half: the shade must follow it, but only by +-12%.
    parse = figure_parse(W, H)
    image = np.asarray(paint(parse)).copy()
    skin = np.isin(parse.labels, [11, 12, 13, 14, 15])
    image[skin & (np.arange(W)[None, :] > 75)] = (75, 45, 40)
    prepared = cut_out(Image.fromarray(image), parse, LINES)

    assert prepared.shade.min() >= -0.1201 and prepared.shade.max() <= 0.1201
    assert prepared.shade.max() - prepared.shade.min() > 0.05
    out = np.asarray(recolour(prepared, "#CF9D77"), dtype=np.float32)
    solid = (prepared.skin > 0.99) & (prepared.alpha > 0.99)
    assert out[solid][:, :3].std() > 1  # not perfectly flat


def test_it_scales_to_other_render_sizes() -> None:
    prepared = _prepare(width=96, height=128)

    assert prepared.size == (96, 128)
    assert prepared.alpha.max() > 0.9


def test_no_figure_is_a_typed_error() -> None:
    labels = np.zeros((H, W), dtype=np.uint8)
    parse = ParseResult(labels, {0: "background", 4: "upper_clothes"})

    with pytest.raises(NoFigureError):
        cut_out(Image.new("RGB", (W, H)), parse, LINES)


def test_a_figure_entirely_above_the_chin_is_no_figure() -> None:
    labels = np.zeros((H, W), dtype=np.uint8)
    labels[10:40, 60:90] = 11
    parse = ParseResult(labels, {0: "background", 11: "face"})

    with pytest.raises(NoFigureError):
        cut_out(Image.new("RGB", (W, H)), parse, LINES)


def test_labels_must_match_the_image() -> None:
    with pytest.raises(DummyError, match="does not match"):
        cut_out(Image.new("RGB", (W + 1, H)), figure_parse(W, H), LINES)


def test_cut_lines_must_fit_the_image() -> None:
    parse = figure_parse(W, H, shoes=False)
    with pytest.raises(DummyError, match="do not fit"):
        cut_out(paint(parse), parse, DummyMeta(chin=0.9, ankle_fallback=0.5))


def test_recolour_rejects_a_bad_tone() -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        recolour(_prepare(), "brown")


def test_meta_reads_the_calibration() -> None:
    assert dummy_meta(META) == LINES
    assert DUMMY_VERSION


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"dummy": "x"},
        {"dummy": {"chin": 0.2}},
        {"dummy": {"chin": 0.2, "ankle": {"rule": "legs", "fallback": 0.8}}},
        {"dummy": {"chin": "0.2", "ankle": {"rule": "shoe_top", "fallback": 0.8}}},
        {"dummy": {"chin": 1.2, "ankle": {"rule": "shoe_top", "fallback": 0.8}}},
        {"dummy": {"chin": True, "ankle": {"rule": "shoe_top", "fallback": 0.8}}},
        {"dummy": {"chin": 0.9, "ankle": {"rule": "shoe_top", "fallback": 0.8}}},
    ],
)
def test_malformed_calibration_is_a_dummy_error(meta: dict) -> None:
    with pytest.raises(DummyError):
        dummy_meta(meta)


def test_the_shipped_bases_are_calibrated() -> None:
    import json
    from pathlib import Path

    folders = (Path(__file__).parents[3] / "assets" / "tryon" / "mannequins").iterdir()
    metas = [json.loads((f / "meta.json").read_text()) for f in folders if f.is_dir()]
    assert len(metas) >= 2
    for meta in metas:
        dummy_meta(meta)
