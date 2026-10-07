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
        self.seeds: list[int] = []
        self.oom_on = oom_on or set()
        self.freed = 0

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        config: ts.Config,
        seed: int,
        on_step: Callable[[], None],
    ) -> Image.Image:
        self.seeds.append(seed)
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
    if "overall" in slots:
        Image.new("RGB", (45, 80), (150, 30, 90)).save(d / "overall.png")
    return d


# --- pure helpers -------------------------------------------------------------------------


def test_parse_choice_defaults_validates_and_dedupes() -> None:
    assert ts.parse_choice(None, ["A", "B", "C"], "config") == ["A", "B", "C"]
    assert ts.parse_choice("B, A,B", ["A", "B", "C"], "config") == ["B", "A"]
    with pytest.raises(ts.SpikeSetupError, match="unknown config Z"):
        ts.parse_choice("A,Z", ["A", "B", "C"], "config")
    with pytest.raises(ts.SpikeSetupError):
        ts.parse_choice(" , ", ["A"], "config")


def test_parse_choice_explicit_default() -> None:
    assert ts.parse_choice(None, ["A", "D"], "config", ["A"]) == ["A"]
    assert ts.parse_choice("D", ["A", "D"], "config", ["A"]) == ["D"]


def test_parse_seeds() -> None:
    assert ts.parse_seeds(None) == [42]
    assert ts.parse_seeds("7, 42,7") == [7, 42]
    with pytest.raises(ts.SpikeSetupError, match="integers"):
        ts.parse_seeds("1,x")
    with pytest.raises(ts.SpikeSetupError, match="empty"):
        ts.parse_seeds(" , ")


def test_spec_configurations() -> None:
    assert ts.CONFIGS["A"] == ts.Config("A", 576, 768, 30)
    assert ts.CONFIGS["B"] == ts.Config("B", 384, 512, 30)
    assert ts.CONFIGS["C"] == ts.Config("C", 576, 768, 20)
    assert ts.CONFIGS["D"] == ts.Config("D", 768, 1024, 20)  # CatVTON's native resolution
    assert ts.DEFAULT_CONFIGS == ("A", "B", "C")  # D is opt-in
    assert ts.DEFAULT_CASES == ("upper", "lower", "outfit")  # overall is opt-in
    assert [s for s, _ in ts.CASES["overall"]] == ["overall"]
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
    # overall: needs overall.* in the set and mask_overall.png on the mannequin.
    assert ts.missing_inputs("overall", m, g_full) == "no overall garment in full"
    g_dress = ts.load_garment_set(_garments(tmp_path, "dress", slots=("overall",)))
    assert set(g_dress.garments) == {"overall"}
    assert ts.missing_inputs("overall", m, g_dress) == "no mask_overall.png for neutral-01"
    m_all = ts.load_mannequin(_mannequin(tmp_path, "m2", masks=("upper", "overall")))
    assert ts.missing_inputs("overall", m_all, g_dress) is None


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
    assert "| OOM runs | blank runs |" in report and "## Per mannequin" in report
    assert "| neutral-01 |" in report and "PARTIAL" not in report
    partial = ts.format_report(results, configs, info, [], partial=True)
    assert "PARTIAL" in partial


def test_main_reports_setup_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mannequin = _mannequin(tmp_path / "in")
    garments = _garments(tmp_path / "in")
    base = ["--mannequin", str(mannequin), "--garments", str(garments), "--out", str(tmp_path)]
    assert ts.main(["--catvton-dir", str(tmp_path / "nope"), *base]) == 1
    assert "tryon-setup" in capsys.readouterr().err
    assert ts.main(["--catvton-dir", str(tmp_path), *base, "--configs", "Z"]) == 1
    assert "unknown config Z" in capsys.readouterr().err


# --- V0c: seeds, config D, overall, comparison sheets, checkpoints ---------------------------


def test_seeds_multiply_runs_and_reach_the_dresser(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    dresser = FakeDresser()
    out = tmp_path / "out"
    results = ts.run_spike(
        dresser, [mannequin], [garments], [TINY], ["upper", "outfit"], out, seeds=[42, 7]
    )
    assert [(r.case, r.seed) for r in results] == [
        ("upper", 42),
        ("upper", 7),
        ("outfit", 42),
        ("outfit", 7),
    ]
    assert dresser.seeds == [42, 7, 42, 42, 7, 7]  # outfit = 2 passes with the same seed
    assert [r.out_file for r in results] == [
        "neutral-01/current/T_upper_s42.png",
        "neutral-01/current/T_upper_s7.png",
        "neutral-01/current/T_outfit_s42.png",
        "neutral-01/current/T_outfit_s7.png",
    ]
    assert all((out / r.out_file).is_file() for r in results if r.out_file)


def test_default_seed_is_42(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    dresser = FakeDresser()
    (result,) = ts.run_spike(dresser, [mannequin], [garments], [TINY], ["upper"], tmp_path / "o")
    assert result.seed == 42 and dresser.seeds == [42]
    assert result.out_file == "neutral-01/current/T_upper_s42.png"


def test_config_d_dimensions_reach_the_dresser(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in"))
    garments = ts.load_garment_set(_garments(tmp_path / "in"))
    dresser = FakeDresser()
    config = ts.Config("D", 36, 48, 2)  # D's 3:4 ratio, shrunk to keep the test tiny
    ts.run_spike(dresser, [mannequin], [garments], [config], ["upper"], tmp_path / "out")
    assert dresser.calls[0][0] == (36, 48) and dresser.calls[0][3] == "D"
    prepared = ts.prepare_person(Image.new("RGB", (60, 90)), ts.CONFIGS["D"])
    assert prepared.size == (768, 1024)


def test_overall_case_uses_mask_overall(tmp_path: Path) -> None:
    mannequin = ts.load_mannequin(_mannequin(tmp_path / "in", masks=("upper", "lower", "overall")))
    dress = ts.load_garment_set(_garments(tmp_path / "in", "dress", slots=("overall",)))
    dresser = FakeDresser()
    (result,) = ts.run_spike(dresser, [mannequin], [dress], [TINY], ["overall"], tmp_path / "out")
    assert [p.slot for p in result.passes] == ["overall"] and result.out_file is not None
    assert len(dresser.calls) == 1 and not result.skipped


def test_overall_case_is_skipped_with_a_note(tmp_path: Path) -> None:
    no_mask = ts.load_mannequin(_mannequin(tmp_path / "in"))  # upper + lower masks only
    dress = ts.load_garment_set(_garments(tmp_path / "in", "dress", slots=("overall",)))
    tee = ts.load_garment_set(_garments(tmp_path / "in", "tee", slots=("upper",)))
    with_mask = ts.load_mannequin(
        _mannequin(tmp_path / "in", "full", masks=("upper", "lower", "overall"))
    )
    dresser = FakeDresser()
    results = ts.run_spike(
        dresser, [no_mask, with_mask], [dress, tee], [TINY], ["overall"], tmp_path / "out"
    )
    assert [r.skipped for r in results] == [
        "no mask_overall.png for neutral-01",
        "no overall garment in tee",
        None,
        "no overall garment in tee",
    ]
    assert len(dresser.calls) == 1
    report = ts.format_report(results, [TINY], ts.RunInfo("cpu", "fp32", 0.0, {}), [])
    assert "skipped: no mask_overall.png for neutral-01" in report


def test_outfit_never_includes_overall() -> None:
    assert "overall" not in [slot for slot, _ in ts.CASES["outfit"]]


def test_comparison_sheet_has_a_row_per_mannequin(tmp_path: Path) -> None:
    mannequins = [
        ts.load_mannequin(_mannequin(tmp_path / "in", "m1")),
        ts.load_mannequin(_mannequin(tmp_path / "in", "m2")),
        ts.load_mannequin(_mannequin(tmp_path / "in", "m3")),
    ]
    sets = [
        ts.load_garment_set(_garments(tmp_path / "in", "g1")),
        ts.load_garment_set(_garments(tmp_path / "in", "g2")),
    ]
    out = tmp_path / "out"
    cases = ["upper", "outfit"]
    results = ts.run_spike(FakeDresser(), mannequins, sets, [TINY], cases, out, seeds=[42, 7])
    sheets = ts.write_comparison_sheets(mannequins, sets, [TINY], cases, results, out, [42, 7])
    assert [s.name for s in sheets] == ["compare_g1.jpg", "compare_g2.jpg"]
    cell_w, cell_h = ts._cell(None, "").size
    for sheet in sheets:
        width, height = Image.open(sheet).size
        # header (garments) + one row per mannequin; mannequin + 2 cases x 2 seeds columns.
        assert height == (1 + 3) * cell_h
        assert width == 5 * cell_w
    assert cell_h <= 280  # thumbnails stay around 256 px high


def test_incremental_report_after_each_group(tmp_path: Path) -> None:
    mannequins = [
        ts.load_mannequin(_mannequin(tmp_path / "in", "m1")),
        ts.load_mannequin(_mannequin(tmp_path / "in", "m2")),
    ]
    sets = [ts.load_garment_set(_garments(tmp_path / "in"))]
    out = tmp_path / "out"
    out.mkdir()
    info = ts.RunInfo("cpu", "fp32", 0.0, {})
    seen: list[str] = []

    def checkpoint(partial: list[ts.CaseResult]) -> None:
        path = ts.write_checkpoint(out, partial, [TINY], info)
        seen.append(path.read_text(encoding="utf-8"))

    results = ts.run_spike(
        FakeDresser(), mannequins, sets, [TINY], ["upper"], out, on_group_done=checkpoint
    )
    assert len(seen) == 2 and len(results) == 2  # one checkpoint per mannequin x garment set
    assert "PARTIAL" in seen[0] and "| m1 |" in seen[0] and "| m2 |" not in seen[0]
    assert "| m2 |" in seen[1]
    assert (out / "tryon_spike_report.md").is_file()


def test_report_aggregates_per_mannequin() -> None:
    def case(m: str, **flags: bool) -> ts.CaseResult:
        r = ts.CaseResult(m, "g", "T", "outfit")
        r.passes = [ts.PassResult("x", s, None, None, 1, **flags) for s in (10.0, 20.0)]
        return r

    results = [case("m1"), case("m2", oom=True), case("m2", blank=True)]
    report = ts.format_report(results, [TINY], ts.RunInfo("cpu", "fp32", 0.0, {}), [])
    assert "| T | 30x40 | 3 | 30.0 | 1 | 1 | fails |" in report
    assert "| m1 | 2 | 0 | 0 | 15.0 |" in report
    assert "| m2 | 4 | 1 | 1 | 15.0 |" in report
