"""Garment-only cutout in the worker `cutout` step (U5c) with a fake matte remover and a
fake parser: no person keeps the matte, clothing intersects, footwear subtracts, unknown
category, small-mask fallback + review flag, eroded colour image, parser failure and the
`ml_garment_parse` toggle. No model is loaded (VIS-REQ-029)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from ml.background import EmptyCutoutError, crop_to_foreground
from ml.garment_parse import ParseResult
from shared.db import create_db_engine, create_session_factory
from shared.enums import GarmentCategory
from shared.models import Garment
from shared.settings import Settings
from worker.runner import StepContext
from worker.steps.consolidate import consolidate_step
from worker.steps.cutout import (
    REVIEW_ITEM_KEPT,
    REVIEW_MASK_TOO_SMALL,
    REVIEW_PARSER_FAILED,
    make_cutout_step,
)

SIZE = 60
NAMES = {
    0: "background",
    1: "face",
    2: "upper_clothes",
    3: "pants",
    4: "arms",
    5: "feet",
}


class FakeMatteRemover:
    """Matte opaque on columns 10..50 of the whole image; `remove` is its bbox crop."""

    def __init__(self) -> None:
        self.matte_calls = 0
        self.remove_calls = 0

    def matte(self, img: Image.Image) -> Image.Image:
        self.matte_calls += 1
        rgba = img.convert("RGBA")
        alpha = np.zeros((img.height, img.width), dtype=np.uint8)
        alpha[:, 10:50] = 255
        rgba.putalpha(Image.fromarray(alpha, mode="L"))
        return rgba

    def remove(self, img: Image.Image) -> Image.Image:
        self.remove_calls += 1
        return crop_to_foreground(self.matte(img))


class EmptyMatteRemover(FakeMatteRemover):
    def matte(self, img: Image.Image) -> Image.Image:
        raise EmptyCutoutError(0.0)


class FakeParser:
    name = "fake"
    revision = None

    def __init__(self, result: ParseResult | None = None, *, error: bool = False) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def parse(self, rgb: Image.Image) -> ParseResult:
        self.calls += 1
        if self.error:
            raise RuntimeError("cuda out of memory")
        assert self.result is not None
        return self.result

    def close(self) -> None:
        pass


def _person_result(*, top_rows: int = 30, face: bool = True) -> ParseResult:
    """Top on rows [0, top_rows), arms on the sides of it, legs-like feet below."""
    grid = np.zeros((SIZE, SIZE), dtype=np.uint8)
    grid[0:top_rows, 14:46] = 2
    grid[0:top_rows, 10:14] = 4  # arm
    grid[top_rows:SIZE, 10:50] = 5  # feet-like body below
    if face:
        grid[0:6, 24:36] = 1
    return ParseResult(grid, NAMES)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "d", ml_embed_revision="r", thumb_px=32)


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _run(
    factory, settings: Settings, remover, parser, *, category: GarmentCategory | None = None
) -> tuple[StepContext, Image.Image, str]:
    with factory() as session:
        garment = Garment(img_original="original/x.jpg", category=category)
        session.add(garment)
        session.commit()
        garment_id = garment.id
    image = Image.new("RGB", (SIZE, SIZE), (200, 30, 30))
    ctx = StepContext(
        job_id="j",
        garment_id=garment_id,
        settings=settings,
        session_factory=factory,
        data={"image": image},
    )
    step = make_cutout_step(lambda: remover, lambda: parser)
    step(ctx)
    return ctx, ctx.data["cutout"], garment_id


def _opaque_rows(cutout: Image.Image) -> int:
    return int((np.asarray(cutout.getchannel("A")).max(axis=1) > 10).sum())


def test_no_person_keeps_the_birefnet_matte(factory, settings) -> None:
    flat_lay = ParseResult(np.zeros((SIZE, SIZE), dtype=np.uint8), NAMES)
    remover = FakeMatteRemover()
    ctx, cutout, _ = _run(factory, settings, remover, FakeParser(flat_lay))
    assert cutout.size == (40, SIZE)  # matte cropped to its bbox, untouched
    assert "cutout_review" not in ctx.data and "color_image" not in ctx.data


def test_clothing_is_intersected_with_its_group_and_cropped(factory, settings) -> None:
    ctx, cutout, _ = _run(
        factory,
        settings,
        FakeMatteRemover(),
        FakeParser(_person_result()),
        category=GarmentCategory.top,
    )
    assert cutout.size == (32, 30)  # only the top: no arms (cols 10..14), no legs/feet below
    assert "cutout_review" not in ctx.data


def _unknown_grid(*, pants_cols: int, feet_cols: int) -> ParseResult:
    """Top (rows 0-30, 480 px), pants (rows 30-45) and feet (rows 45-60) of given widths."""
    grid = np.zeros((SIZE, SIZE), dtype=np.uint8)
    grid[0:30, 14:30] = 2
    grid[30:45, 10 : 10 + pants_cols] = 3
    grid[45:60, 10 : 10 + feet_cols] = 5
    grid[0:6, 24:36] = 1
    return ParseResult(grid, NAMES)


def test_unknown_category_uses_the_largest_clothing_region(factory, settings) -> None:
    # Small feet (under the unselected-item threshold): the top wins as before, no review.
    ctx, cutout, _ = _run(
        factory, settings, FakeMatteRemover(), FakeParser(_unknown_grid(pants_cols=20, feet_cols=4))
    )
    assert cutout.size == (16, 30)
    assert "cutout_review" not in ctx.data


def test_unknown_category_keeps_worn_footwear_when_it_is_the_largest(factory, settings) -> None:
    # A photo of shoes on feet: feet (40 cols) beat the top and pants -> subtract body only.
    ctx, cutout, _ = _run(
        factory, settings, FakeMatteRemover(), FakeParser(_unknown_grid(pants_cols=8, feet_cols=40))
    )
    alpha = np.asarray(cutout.getchannel("A"))
    assert (alpha[-15:, :] == 255).all()  # shoe rows kept
    assert (alpha[0:6, 14:26] == 0).all()  # face removed
    assert "cutout_review" not in ctx.data


def test_unknown_category_keeps_a_substantial_unselected_item_and_flags_review(
    factory, settings
) -> None:
    # Pants (40 cols x 15) beat feet (30 cols x 15, 18.75% of the matte), but the feet
    # must not be cut away silently.
    ctx, cutout, _ = _run(
        factory,
        settings,
        FakeMatteRemover(),
        FakeParser(_unknown_grid(pants_cols=40, feet_cols=30)),
    )
    alpha = np.asarray(cutout.getchannel("A"))
    assert (alpha[-15:, 0:30] == 255).all()  # feet kept
    assert (alpha[30:45, :] == 255).all()  # pants kept too (subtract keeps every garment)
    assert ctx.data["cutout_review"] == REVIEW_ITEM_KEPT


def test_category_is_read_from_the_database(factory, settings) -> None:
    # The same parse cut as a bottom finds no pants -> largest-region fallback inside the
    # vocabulary would pick the top, so use pants to prove the category is honoured.
    grid = np.zeros((SIZE, SIZE), dtype=np.uint8)
    grid[0:30, 14:46] = 2  # larger top
    grid[30:50, 20:40] = 3  # smaller pants
    grid[0:6, 24:36] = 1
    _, cutout, _ = _run(
        factory,
        settings,
        FakeMatteRemover(),
        FakeParser(ParseResult(grid, NAMES)),
        category=GarmentCategory.bottom,
    )
    assert cutout.size == (20, 20)


def test_footwear_subtracts_body_only(factory, settings) -> None:
    ctx, cutout, _ = _run(
        factory,
        settings,
        FakeMatteRemover(),
        FakeParser(_person_result()),
        category=GarmentCategory.shoes,
    )
    # Face and arms removed; the top (not body) and the feet-like region stay.
    alpha = np.asarray(cutout.getchannel("A"))  # cropped to the matte's columns 10..50
    assert (alpha[0:6, 14:26] == 0).all()  # face removed
    assert (alpha[0:30, 0:4] == 0).all()  # arm removed
    assert (alpha[10:30, 6:30] == 255).all()  # clothing kept (not a body class)
    assert (alpha[30:, :] == 255).all()  # feet-like region kept
    assert "cutout_review" not in ctx.data


def test_small_garment_mask_keeps_the_matte_and_flags_review(factory, settings) -> None:
    grid = np.zeros((SIZE, SIZE), dtype=np.uint8)
    grid[0:6, 24:36] = 1  # a face, so a person is present
    grid[20:22, 20:22] = 2  # 4 px of top: far below 1 %
    ctx, cutout, garment_id = _run(
        factory, settings, FakeMatteRemover(), FakeParser(ParseResult(grid, NAMES))
    )
    assert cutout.size == (40, SIZE)
    assert ctx.data["cutout_review"] == REVIEW_MASK_TOO_SMALL
    consolidate_step(ctx)
    with factory() as session:
        flagged = session.get(Garment, garment_id)
        assert flagged is not None and flagged.needs_review is True


def test_colours_come_from_the_eroded_mask(factory, settings) -> None:
    ctx, cutout, _ = _run(factory, settings, FakeMatteRemover(), FakeParser(_person_result()))
    eroded = ctx.data["color_image"]
    assert eroded.size == cutout.size
    before = np.asarray(cutout.getchannel("A")) > 10
    after = np.asarray(eroded.getchannel("A")) > 10
    assert after.sum() < before.sum()
    assert after[~before].sum() == 0  # erosion never grows the mask


def test_parser_failure_degrades_to_the_matte_and_flags_review(factory, settings) -> None:
    ctx, cutout, _ = _run(factory, settings, FakeMatteRemover(), FakeParser(error=True))
    assert cutout.size == (40, SIZE)
    assert ctx.data["cutout_review"] == REVIEW_PARSER_FAILED


def test_setting_off_keeps_todays_cutout_without_parsing(factory, tmp_path: Path) -> None:
    off = Settings(
        _env_file=None,
        data_dir=tmp_path / "off",
        ml_embed_revision="r",
        ml_garment_parse=False,
    )
    remover = FakeMatteRemover()
    parser = FakeParser(_person_result())
    ctx, cutout, _ = _run(factory, off, remover, parser)
    assert parser.calls == 0 and remover.matte_calls == 1  # remove() -> matte, once
    assert remover.remove_calls == 1
    assert cutout.size == (40, SIZE)
    assert "color_image" not in ctx.data


def test_empty_matte_is_still_a_soft_failure(factory, settings) -> None:
    ctx, cutout, _ = _run(factory, settings, EmptyMatteRemover(), FakeParser(_person_result()))
    assert ctx.data["cutout_soft_failure"] is True
    assert cutout.size == (SIZE, SIZE)
