"""Try-on spike orchestration with a fake dresser and tiny images (VIS-REQ-029)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import ml.tryon_spike as ts

TINY = ts.Config("T", 30, 40, 3)


class FakeOOM(Exception):
    pass


class FakeDresser:
    """Paints the masked area with the garment's mean colour; can OOM on given calls."""

    def __init__(self, *, oom_on: set[int] | None = None) -> None:
        self.calls: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int], str]] = []
        self.oom_on = oom_on or set()
        self.freed = 0

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        config: ts.Config,
        on_step: Callable[[], None],
    ) -> Image.Image:
        self.calls.append((person.size, garment.size, mask.size, config.name))
        if len(self.calls) in self.oom_on:
            raise FakeOOM("CUDA out of memory")
        for _ in range(config.steps):
            on_step()
        colour = tuple(int(c) for c in np.asarray(garment).reshape(-1, 3).mean(axis=0))
        out = person.copy()
        out.paste(Image.new("RGB", out.size, colour), (0, 0), mask.point(lambda v: v))
        return out

    def peak_mib(self) -> float | None:
        return 123.0

    def reset_peak(self) -> None:
        pass

    def is_oom(self, exc: BaseException) -> bool:
        return isinstance(exc, FakeOOM)

    def free(self) -> None:
        self.freed += 1


def _mannequin(root: Path, name: str = "neutral-01", masks=("upper", "lower")) -> Path:
    d = root / name
    d.mkdir(parents=True)
    person = Image.new("RGB", (60, 90), (40, 40, 40))
    person.paste((220, 200, 190), (10, 0, 50, 90))  # varied, so a dressed output is not blank
    person.save(d / "person.png")
    for t in masks:
        m = Image.new("L", (60, 90), 0)
        m.paste(255, (10, 10 if t == "upper" else 45, 50, 45 if t == "upper" else 85))
        m.save(d / f"mask_{t}.png")
    return d


def _garments(root: Path, name: str = "current", slots=("upper", "lower")) -> Path:
    d = root / name
    d.mkdir(parents=True)
    if "upper" in slots:
        cut = Image.new("RGBA", (50, 60), (0, 0, 0, 0))
        cut.paste((10, 20, 200, 255), (10, 5, 40, 55))
        cut.save(d / "upper.png")
    if "lower" in slots:
        Image.new("RGB", (40, 70), (200, 180, 100)).save(d / "lower.jpg")
    return d


# --- pure helpers -------------------------------------------------------------------------


def test_parse_choice_defaults_validates_and_dedupes() -> None:
    assert ts.parse_choice(None, ["A", "B", "C"], "config") == ["A", "B", "C"]
    assert ts.parse_choice("B, A,B", ["A", "B", "C"], "config") == ["B", "A"]
    with pytest.raises(ts.SpikeSetupError, match="unknown config Z"):
        ts.parse_choice("A,Z", ["A", "B", "C"], "config")
    with pytest.raises(ts.SpikeSetupError):
        ts.parse_choice(" , ", ["A"], "config")


def test_spec_configurations() -> None:
    assert ts.CONFIGS["A"] == ts.Config("A", 576, 768, 30)
    assert ts.CONFIGS["B"] == ts.Config("B", 384, 512, 30)
    assert ts.CONFIGS["C"] == ts.Config("C", 576, 768, 20)
    # Outfit: lower first, then upper over the result (§5.3).
    assert [s for s, _ in ts.CASES["outfit"]] == ["lower", "upper"]


def test_load_mannequin_and_errors(tmp_path: Path) -> None:
    m = ts.load_mannequin(_mannequin(tmp_path))
    assert m.id == "neutral-01" and set(m.masks) == {"upper", "lower"}
    with pytest.raises(ts.SpikeSetupError, match="not found"):
        ts.load_mannequin(tmp_path / "nope")
    (tmp_path / "bare").mkdir()
    Image.new("RGB", (4, 4)).save(tmp_path / "bare" / "person.jpg")
    with pytest.raises(ts.SpikeSetupError, match="tryon-masks"):
        ts.load_mannequin(tmp_path / "bare")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ts.SpikeSetupError, match="person"):
        ts.load_mannequin(tmp_path / "empty")


def test_load_garment_set(tmp_path: Path) -> None:
    g = ts.load_garment_set(_garments(tmp_path))
    assert g.id == "current" and set(g.garments) == {"upper", "lower"}
    (tmp_path / "none").mkdir()
    with pytest.raises(ts.SpikeSetupError, match="upper"):
        ts.load_garment_set(tmp_path / "none")


def test_missing_inputs(tmp_path: Path) -> None:
    m = ts.load_mannequin(_mannequin(tmp_path, masks=("upper",)))
    g = ts.load_garment_set(_garments(tmp_path, slots=("upper",)))
    assert ts.missing_inputs("upper", m, g) is None
    assert ts.missing_inputs("lower", m, g) == "no lower garment in current"
    g_full = ts.load_garment_set(_garments(tmp_path, "full"))
    assert ts.missing_inputs("outfit", m, g_full) == "no mask_lower.png for neutral-01"


def test_fit_crop_matches_catvton_math() -> None:
    wide = Image.new("RGB", (200, 100))
    wide.paste((255, 0, 0), (0, 0, 50, 100))  # left quarter red: cropped away
    out = ts.fit_crop(wide, (30, 40), Image.Resampling.NEAREST)
    assert out.size == (30, 40)
    assert out.getpixel((0, 20)) == (0, 0, 0)
    tall = ts.fit_crop(Image.new("RGB", (100, 400)), (30, 40), Image.Resampling.NEAREST)
    assert tall.size == (30, 40)


def test_prepare_mask_binarises_and_blurs() -> None:
    mask = Image.new("L", (60, 80), 0)
    mask.paste(100, (0, 0, 30, 80))  # below 128: dropped
    mask.paste(200, (30, 0, 60, 80))  # kept
    sharp = np.asarray(ts.prepare_mask(mask, TINY, blur=0))
    assert set(np.unique(sharp)) == {0, 255}
    assert sharp[:, :14].max() == 0 and sharp[:, 16:].min() == 255
    blurred = np.asarray(ts.prepare_mask(mask, TINY))
    assert blurred.shape == (40, 30) and 0 < blurred[20, 15] < 255


def test_prepare_garment_crops_cutout_onto_white() -> None:
    cut = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    cut.paste((0, 0, 255, 255), (40, 30, 60, 70))
    out = ts.prepare_garment(cut, margin=0.1)
    assert out.mode == "RGB" and out.size == (28, 48)  # 20x40 box + 4 px (10% of 40) a side
    assert out.getpixel((0, 0)) == (255, 255, 255)
    assert out.getpixel((14, 24)) == (0, 0, 255)


def test_prepare_garment_keeps_photos() -> None:
    photo = Image.new("RGB", (30, 50), (1, 2, 3))
    assert ts.prepare_garment(photo).size == (30, 50)
    opaque_png = Image.new("RGBA", (30, 50), (1, 2, 3, 255))
    assert ts.prepare_garment(opaque_png).size == (30, 50)
    with pytest.raises(ts.SpikeSetupError, match="transparent"):
        ts.prepare_garment(Image.new("RGBA", (5, 5), (0, 0, 0, 0)))


def test_is_blank() -> None:
    assert ts.is_blank(Image.new("RGB", (10, 10)))
    noisy = Image.fromarray(np.random.default_rng(0).integers(0, 255, (10, 10, 3), dtype=np.uint8))
    assert not ts.is_blank(noisy)


def _case(case: str, seconds: list[float], **flags: bool) -> ts.CaseResult:
    r = ts.CaseResult("m", "g", "A", case)
    r.passes = [ts.PassResult("x", s, None, None, 1, **flags) for s in seconds]
    return r


def test_meets_criterion() -> None:
    assert ts.meets_criterion([_case("outfit", [40, 45]), _case("upper", [200])]) is True
    assert ts.meets_criterion([_case("outfit", [50, 45])]) is False  # 95 s > 90 s
    assert ts.meets_criterion([_case("outfit", [10], oom=True)]) is False
    assert ts.meets_criterion([_case("outfit", [10, 10], blank=True)]) is False
    assert ts.meets_criterion([_case("upper", [10])]) is None


# --- orchestration ---------------------------------------------------------------------


def test_run_spike_dresses_every_combination(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    dresser = FakeDresser()
    out = tmp_path / "out"
    results = ts.run_spike(
        dresser, [mannequin], [garments], [TINY], ["upper", "lower", "outfit"], out
    )

    assert [r.case for r in results] == ["upper", "lower", "outfit"]
    assert len(dresser.calls) == 4  # outfit = 2 passes
    # Person, mask and config at the working size; the garment is CatVTON's to pad.
    assert all(c[0] == (30, 40) and c[2] == (30, 40) and c[3] == "T" for c in dresser.calls)
    outfit = results[2]
    assert [p.slot for p in outfit.passes] == ["lower", "upper"]
    assert all(p.steps_seen == 3 and p.step_ms is not None for p in outfit.passes)
    assert outfit.torch_peak_mib == 123.0 and not outfit.oom and not outfit.blank
    for r in results:
        assert r.out_file is not None
        assert Image.open(out / r.out_file).size == (30, 40)
    # The second pass dresses the first pass's output: both colours are in the outfit.
    pixels = np.asarray(Image.open(out / outfit.out_file))
    assert (pixels[10, 15] != pixels[35, 15]).any()


def test_run_spike_records_oom_and_goes_on(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    dresser = FakeDresser(oom_on={1})  # the outfit's first pass
    results = ts.run_spike(
        dresser, [mannequin], [garments], [TINY], ["outfit", "upper"], tmp_path / "out"
    )
    outfit, upper = results
    assert outfit.oom and len(outfit.passes) == 1 and outfit.out_file is None
    assert dresser.freed == 1
    assert upper.out_file is not None and not upper.oom


def test_run_spike_skips_cases_without_inputs(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in", slots=("upper",)))
    dresser = FakeDresser()
    results = ts.run_spike(
        dresser, [mannequin], [garments], [TINY], ["lower", "outfit"], tmp_path / "out"
    )
    assert [r.skipped for r in results] == ["no lower garment in current"] * 2
    assert dresser.calls == []


def test_unexpected_errors_propagate(tmp_path: Path) -> None:
    class Broken(FakeDresser):
        def dress(self, *args, **kwargs):  # type: ignore[override]
            raise RuntimeError("bad weights")

    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    with pytest.raises(RuntimeError, match="bad weights"):
        ts.run_spike(Broken(), [mannequin], [garments], [TINY], ["upper"], tmp_path / "out")


def test_contact_sheets_and_report(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    out = tmp_path / "out"
    configs = [TINY, ts.Config("U", 30, 40, 2)]
    cases = ["upper", "outfit"]
    results = ts.run_spike(FakeDresser(oom_on={5}), [mannequin], [garments], configs, cases, out)
    sheets = ts.write_contact_sheets([mannequin], [garments], configs, cases, results, out)
    assert [s.name for s in sheets] == ["contact_neutral-01_current.jpg"]
    assert sheets[0].is_file()

    info = ts.RunInfo("cuda", "fp16", 12.5, {ts.BASE_MODEL: "abc", "vae": None}, 2048.0, 5100.0)
    report = ts.format_report(results, configs, info, sheets)
    assert "device: cuda; dtype: fp16; model load: 12.5 s" in report
    assert f"{ts.BASE_MODEL}=abc" in report and "vae=unpinned" in report
    assert "| T | 30x40 | 3 |" in report and "| meets |" in report
    assert "| U | 30x40 | 2 |" in report and "| fails |" in report  # its outfit OOMed
    assert "OOM" in report
    assert "contact_neutral-01_current.jpg" in report


def test_main_reports_setup_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mannequin = _mannequin(tmp_path / "in")
    garments = _garments(tmp_path / "in")
    base = ["--mannequin", str(mannequin), "--garments", str(garments), "--out", str(tmp_path)]
    assert ts.main(["--catvton-dir", str(tmp_path / "nope"), *base]) == 1
    assert "tryon-setup" in capsys.readouterr().err
    assert ts.main(["--catvton-dir", str(tmp_path), *base, "--configs", "Z"]) == 1
    assert "unknown config Z" in capsys.readouterr().err
