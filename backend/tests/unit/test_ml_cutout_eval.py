"""Cutout evaluation orchestration with fake matter/parsers and tiny images (VIS-REQ-029)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import ml.cutout_eval as ce
from ml.garment_parse import ParseResult

ATR = {0: "background", 2: "upper_clothes", 3: "pants", 5: "face"}


class FakeMatter:
    closed = False

    def matte(self, rgb: Image.Image) -> Image.Image:
        out = rgb.convert("RGBA")
        out.putalpha(Image.new("L", rgb.size, 255))  # everything is foreground
        return out

    def close(self) -> None:
        self.closed = True


class FakeParser:
    revision = "rev1"

    def __init__(self, name: str, *, person: bool) -> None:
        self.name = name
        self.person = person
        self.closed = False

    def parse(self, rgb: Image.Image) -> ParseResult:
        grid = np.zeros((rgb.height, rgb.width), dtype=np.uint8)
        grid[: rgb.height // 2] = 2  # top half is the upper garment
        grid[rgb.height // 2 :] = 3
        if self.person:
            grid[:4, :4] = 5
        return ParseResult(grid, ATR)

    def close(self) -> None:
        self.closed = True


def _photo_dir(tmp_path: Path, name: str = "photos") -> Path:
    d = tmp_path / name
    d.mkdir()
    Image.new("RGB", (16, 16), (200, 30, 30)).save(d / "a.jpg")
    Image.new("RGB", (16, 16), (30, 30, 200)).save(d / "b.png")
    (d / "notes.txt").write_text("ignored")
    return d


def test_parse_methods_defaults_and_validation() -> None:
    assert ce.parse_methods(None) == list(ce.ALL_METHODS)
    # the baseline is always first, duplicates dropped
    assert ce.parse_methods("birefnet+u2net-cloth,birefnet+u2net-cloth") == [
        "birefnet",
        "birefnet+u2net-cloth",
    ]
    with pytest.raises(ce.EvalSetupError, match="unknown"):
        ce.parse_methods("birefnet+magic")


def test_parse_mask_modes() -> None:
    assert ce.parse_mask_modes(None) == ["intersect", "subtract"]
    assert ce.parse_mask_modes("subtract,subtract") == ["subtract"]
    with pytest.raises(ce.EvalSetupError, match="unknown mask mode"):
        ce.parse_mask_modes("intersect,magic")
    assert {"fashn", "schp-atr", "schp-lip"} <= set(ce.PARSER_KEYS)


def test_collect_photos_reads_categories_and_prefixes_keys(tmp_path: Path) -> None:
    d = _photo_dir(tmp_path)
    (d / "labels.json").write_text(json.dumps({"a.jpg": {"category": "top"}, "b.png": None}))
    photos = ce.collect_photos([d])
    assert [(p.key, p.category) for p in photos] == [
        ("photos__a.jpg", "top"),
        ("photos__b.png", None),
    ]
    with pytest.raises(ce.EvalSetupError):
        ce.collect_photos([tmp_path / "missing"])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ce.EvalSetupError, match="no .jpg"):
        ce.collect_photos([empty])


def test_warm_latencies_skip_first_and_empty() -> None:
    rows = [
        ce.Row("a", 900, "-", None),
        ce.Row("b", 10, "-", None),
        ce.Row("c", 50, "-", None, empty=True),
        ce.Row("d", 20, "-", None),
    ]
    assert ce.warm_latencies(rows) == [10, 20]


def test_evaluate_runs_methods_serially_and_writes_outputs(tmp_path: Path) -> None:
    photos = ce.collect_photos([_photo_dir(tmp_path)])
    out = tmp_path / "out"
    matter = FakeMatter()
    parsers: dict[str, FakeParser] = {}

    def factory(key: str) -> FakeParser:
        parsers[key] = FakeParser(key, person=True)
        return parsers[key]

    methods = ce.parse_methods("birefnet+segformer-b3,birefnet+u2net-cloth")
    selected, skipped, results = ce.evaluate(
        photos, methods, out, matter_factory=lambda: matter, parser_factory=factory
    )
    assert matter.closed and all(p.closed for p in parsers.values())
    assert sorted(parsers) == ["segformer-b3", "u2net-cloth"]  # one parser load per method
    assert [r.method for r in results] == [
        "birefnet",
        "birefnet+segformer-b3.intersect",
        "birefnet+segformer-b3.subtract",
        "birefnet+u2net-cloth.intersect",
        "birefnet+u2net-cloth.subtract",
    ]
    assert [r.mode for r in results] == [None, "intersect", "subtract", "intersect", "subtract"]
    assert skipped == [] and len(selected) == 2
    assert not (out / "_mattes").exists()
    for r in results:
        for photo in selected:
            assert (out / r.rows[photo.key].out_file).is_file()  # type: ignore[arg-type]
    base, parsed = results[0].rows["photos__a.jpg"], results[1].rows["photos__a.jpg"]
    assert base.top_color != "-" and parsed.ms >= base.ms
    assert results[1].revision == "rev1" and results[2].revision == "rev1"
    # garment-only cutout is the top half of the 16 px image
    with Image.open(out / "birefnet+segformer-b3.intersect" / "photos__a.jpg.png") as cut:
        assert cut.size == (16, 8)
    # subtract keeps the matte minus the 4x4 face (and, unknown category, no other group)
    with Image.open(out / "birefnet+segformer-b3.subtract" / "photos__a.jpg.png") as cut:
        assert cut.size == (16, 16)
        assert np.asarray(cut.getchannel("A"))[:4, :4].sum() == 0


def test_mask_modes_selection_limits_columns(tmp_path: Path) -> None:
    photos = ce.collect_photos([_photo_dir(tmp_path)])
    _, _, results = ce.evaluate(
        photos,
        ["birefnet", "birefnet+fashn"],
        tmp_path / "out",
        matter_factory=FakeMatter,
        parser_factory=lambda k: FakeParser(k, person=True),
        mask_modes=["subtract"],
    )
    assert [r.method for r in results] == ["birefnet", "birefnet+fashn.subtract"]


def test_worn_only_filters_with_first_parser(tmp_path: Path) -> None:
    photos = ce.collect_photos([_photo_dir(tmp_path)])

    class Selective(FakeParser):
        def parse(self, rgb: Image.Image) -> ParseResult:
            self.person = rgb.getpixel((0, 0))[0] > 100  # only the red photo shows a person
            return super().parse(rgb)

    selected, skipped, results = ce.evaluate(
        photos,
        ["birefnet", "birefnet+segformer-b3"],
        tmp_path / "out",
        matter_factory=FakeMatter,
        parser_factory=lambda key: Selective(key, person=False),
        worn_only=True,
    )
    assert [p.key for p in selected] == ["photos__a.jpg"]
    assert [p.key for p in skipped] == ["photos__b.png"]
    assert set(results[0].rows) == {"photos__a.jpg"}


def test_worn_only_errors(tmp_path: Path) -> None:
    photos = ce.collect_photos([_photo_dir(tmp_path)])
    kwargs = {"matter_factory": FakeMatter, "worn_only": True}
    with pytest.raises(ce.EvalSetupError, match="parser method"):
        ce.evaluate(
            photos,
            ["birefnet"],
            tmp_path / "o1",
            parser_factory=lambda k: FakeParser(k, person=True),
            **kwargs,  # type: ignore[arg-type]
        )

    class Nobody(FakeParser):
        def parse(self, rgb: Image.Image) -> ParseResult:
            return ParseResult(np.zeros((rgb.height, rgb.width), dtype=np.uint8), ATR)

    with pytest.raises(ce.EvalSetupError, match="no photo with a person"):
        ce.evaluate(
            photos,
            ["birefnet", "birefnet+segformer-b3"],
            tmp_path / "o2",
            parser_factory=lambda k: Nobody(k, person=False),
            **kwargs,  # type: ignore[arg-type]
        )


def test_report_and_contact_sheets(tmp_path: Path) -> None:
    photos = ce.collect_photos([_photo_dir(tmp_path)])
    out = tmp_path / "out"
    selected, skipped, results = ce.evaluate(
        photos,
        ["birefnet", "birefnet+segformer-b3"],
        out,
        matter_factory=FakeMatter,
        parser_factory=lambda k: FakeParser(k, person=True),
    )
    sheets = ce.write_contact_sheets(selected, results, out, per_sheet=1)
    assert [s.name for s in sheets] == ["contact_01.jpg", "contact_02.jpg"]
    with Image.open(sheets[0]) as sheet:
        assert sheet.width == 4 * ce.THUMB_PX  # original + baseline + two modes
    report = ce.format_report(selected, skipped, results, sheets, device="cpu")
    assert "| birefnet+segformer-b3.intersect |" in report
    assert "| birefnet+segformer-b3.subtract |" in report
    assert "| median ms |" in report and "contact_01.jpg" in report
    assert "photos__a.jpg" in report


def test_colour_change_is_flagged() -> None:
    a = ce.Row("x", 1, "negro 60%", "negro")
    b = ce.Row("x", 1, "rojo 90%", "rojo")
    assert ce.colour_changed(a, b) and not ce.colour_changed(a, a)
