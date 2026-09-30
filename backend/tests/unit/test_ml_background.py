"""Unit tests for `ml.background` and `ml.cutout_preview` (08-local-vision.md
step 2, VIS-REQ-004/026/029, ING-SCN-005): `rembg` is faked via `sys.modules`
and the registry session is patched, so no torch, no model and no network."""

from __future__ import annotations

import statistics
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import ml.background as background
import ml.cutout_preview as cutout_preview
import ml.registry as registry
from ml.background import (
    MIN_COVERAGE,
    OPACITY_THRESHOLD,
    BiRefNetRemover,
    EmptyCutoutError,
    alpha_coverage,
    crop_to_foreground,
)
from shared.settings import Settings


def _rgba_with_square(size: int, box: tuple[int, int, int, int], alpha: int = 255) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste((200, 30, 30, alpha), box)
    return img


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    registry.reset_registry()
    yield
    registry.reset_registry()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
    )


def _install_fake_rembg(
    monkeypatch: pytest.MonkeyPatch, produce: Callable[[Image.Image], Image.Image]
) -> list[tuple[Image.Image, Any]]:
    """Fake `rembg.remove`; returns the list of (input image, session) calls."""
    calls: list[tuple[Image.Image, Any]] = []

    def fake_remove(img: Image.Image, session: Any = None) -> Image.Image:
        calls.append((img, session))
        return produce(img)

    fake = types.ModuleType("rembg")
    fake.remove = fake_remove  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rembg", fake)
    monkeypatch.setattr(registry, "get_background_remover", lambda s: "fake-session")
    return calls


def test_alpha_coverage_counts_opaque_fraction() -> None:
    img = _rgba_with_square(100, (0, 0, 50, 50))  # 2500 / 10000
    assert alpha_coverage(img) == pytest.approx(0.25)


def test_alpha_coverage_threshold_edge_is_strictly_above() -> None:
    at = _rgba_with_square(10, (0, 0, 10, 10), alpha=OPACITY_THRESHOLD)
    above = _rgba_with_square(10, (0, 0, 10, 10), alpha=OPACITY_THRESHOLD + 1)
    assert alpha_coverage(at) == 0.0
    assert alpha_coverage(above) == 1.0
    with pytest.raises(EmptyCutoutError):
        crop_to_foreground(at)


def test_alpha_coverage_of_non_rgba_image_is_full() -> None:
    assert alpha_coverage(Image.new("RGB", (4, 4))) == 1.0


def test_crop_to_foreground_matches_opaque_square() -> None:
    img = _rgba_with_square(100, (20, 30, 60, 90))  # 40 x 60
    cropped = crop_to_foreground(img)
    assert cropped.mode == "RGBA"
    assert cropped.size == (40, 60)


def test_crop_fully_transparent_raises_with_zero_coverage() -> None:
    with pytest.raises(EmptyCutoutError) as excinfo:
        crop_to_foreground(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))
    assert excinfo.value.coverage == 0.0


def test_remover_returns_cropped_rgba_using_registry_session(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    calls = _install_fake_rembg(monkeypatch, lambda img: _rgba_with_square(100, (10, 10, 60, 40)))

    result = BiRefNetRemover(settings).remove(Image.new("RGB", (100, 100), "white"))

    assert result.mode == "RGBA"
    assert result.size == (50, 30)
    assert calls[0][1] == "fake-session"


def test_remover_near_empty_output_raises_with_coverage(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # 2x2 opaque pixels in 100x100 = 0.04% < MIN_COVERAGE
    _install_fake_rembg(monkeypatch, lambda img: _rgba_with_square(100, (0, 0, 2, 2)))

    with pytest.raises(EmptyCutoutError) as excinfo:
        BiRefNetRemover(settings).remove(Image.new("RGB", (100, 100)))

    assert excinfo.value.coverage == pytest.approx(0.0004)
    assert excinfo.value.coverage < MIN_COVERAGE


@pytest.mark.parametrize("mode", ["RGBA", "P", "L", "LA"])
def test_remover_normalizes_input_to_rgb(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, mode: str
) -> None:
    calls = _install_fake_rembg(monkeypatch, lambda img: _rgba_with_square(100, (0, 0, 50, 50)))

    BiRefNetRemover(settings).remove(Image.new(mode, (100, 100)))

    assert calls[0][0].mode == "RGB"


def test_transparent_input_is_composited_over_white() -> None:
    rgb = background._to_rgb(Image.new("RGBA", (2, 2), (0, 0, 0, 0)))
    assert rgb.getpixel((0, 0)) == (255, 255, 255)


def test_preview_missing_dir_exits_nonzero_without_traceback(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cutout_preview, "get_settings", lambda: settings)

    assert cutout_preview.main([str(tmp_path / "nope")]) == 1
    assert "not found" in capsys.readouterr().err


def test_preview_empty_dir_exits_nonzero(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cutout_preview, "get_settings", lambda: settings)
    (tmp_path / "notes.txt").write_text("x")

    assert cutout_preview.main([str(tmp_path)]) == 1
    assert "no .jpg" in capsys.readouterr().err


def test_remover_rejects_non_pil_result(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _install_fake_rembg(monkeypatch, lambda img: b"raw-bytes")  # type: ignore[arg-type,return-value]

    with pytest.raises(TypeError, match="bytes"):
        BiRefNetRemover(settings).remove(Image.new("RGB", (10, 10)))


def _write_image(path: Path) -> None:
    Image.new("RGB", (100, 100), "white").save(path)


def _run_preview(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    input_dir: Path,
    out_dir: Path,
) -> tuple[int, list[float]]:
    """Run `cutout_preview.main` with a fake rembg; returns (exit code, the
    per-image durations in ms the fake clock produced, in call order)."""
    monkeypatch.setattr(cutout_preview, "get_settings", lambda: settings)
    monkeypatch.setattr(cutout_preview, "configure_model_cache", lambda path: None)
    monkeypatch.setattr("ml.device.resolve_device", lambda requested: "cpu")

    def produce(img: Image.Image) -> Image.Image:
        # Marker: images with a non-white top-left pixel yield a near-empty mask.
        if img.getpixel((0, 0)) != (255, 255, 255):
            return _rgba_with_square(100, (0, 0, 1, 1))
        return _rgba_with_square(100, (10, 10, 60, 40))

    _install_fake_rembg(monkeypatch, produce)

    # Deterministic clock: call n (start, end pairs) -> the i-th image takes 10*(i+1) ms.
    durations: list[float] = []
    state = {"now": 0.0, "pending": None}

    def fake_perf_counter() -> float:
        if state["pending"] is None:
            state["pending"] = state["now"]
            return state["now"]
        index = len(durations)
        duration_ms = 10.0 * (index + 1)
        durations.append(duration_ms)
        state["now"] += duration_ms / 1000
        state["pending"] = None
        return state["now"]

    monkeypatch.setattr(cutout_preview.time, "perf_counter", fake_perf_counter)
    code = cutout_preview.main([str(input_dir), "--out", str(out_dir)])
    return code, durations


def test_preview_writes_one_png_per_input_and_excludes_warmup_from_median(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_dir, out_dir = tmp_path / "in", tmp_path / "out"
    input_dir.mkdir()
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        _write_image(input_dir / name)

    code, durations = _run_preview(monkeypatch, settings, input_dir, out_dir)

    assert code == 0
    assert sorted(p.name for p in out_dir.iterdir()) == ["a.jpg.png", "b.jpg.png", "c.jpg.png"]
    with Image.open(out_dir / "a.jpg.png") as cutout:
        assert cutout.mode == "RGBA"
        assert cutout.size == (50, 30)
    out = capsys.readouterr().out
    assert "(includes warm-up)" in out.splitlines()[1]
    assert out.count("(includes warm-up)") == 1
    # durations 10, 20, 30 ms: warm-up (10) excluded -> median of (20, 30) = 25
    assert durations == [10.0, 20.0, 30.0]
    assert f"median ms (excluding warm-up): {statistics.median(durations[1:]):.0f}" in out


def test_preview_lists_empty_masks_continues_and_exits_zero(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_dir, out_dir = tmp_path / "in", tmp_path / "out"
    input_dir.mkdir()
    _write_image(input_dir / "a.jpg")
    Image.new("RGB", (100, 100), "black").save(input_dir / "b.jpg")  # -> near-empty mask
    _write_image(input_dir / "c.jpg")

    code, _ = _run_preview(monkeypatch, settings, input_dir, out_dir)

    assert code == 0
    assert sorted(p.name for p in out_dir.iterdir()) == ["a.jpg.png", "c.jpg.png"]
    out = capsys.readouterr().out
    assert "b.jpg: EMPTY mask" in out
    assert "empty masks: 1" in out
    assert "empty: b.jpg" in out


def test_preview_inputs_differing_only_by_extension_get_distinct_outputs(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_dir, out_dir = tmp_path / "in", tmp_path / "out"
    input_dir.mkdir()
    _write_image(input_dir / "a.jpg")
    _write_image(input_dir / "a.png")

    code, _ = _run_preview(monkeypatch, settings, input_dir, out_dir)

    assert code == 0
    assert sorted(p.name for p in out_dir.iterdir()) == ["a.jpg.png", "a.png.png"]


# --- BiRefNet split path (prepare / infer / finish, remove_many) ---------------


class _FakeBiRefNetSession:
    """Stands in for rembg's BiRefNet session: `normalize` builds a feed and
    `inner_session.run` returns a model output whose sigmoid is a centered square."""

    def __init__(self) -> None:
        self.feeds: list[Any] = []
        self.inner_session = self

    def normalize(self, img: Image.Image, mean: Any, std: Any, size: Any) -> dict[str, Any]:
        return {"input": img.size, "mean": mean, "std": std, "size": size}

    def predict(self, img: Image.Image, *args: Any, **kwargs: Any) -> list[Image.Image]:
        raise AssertionError("the split path must not call predict")

    def run(self, _outputs: Any, feed: dict[str, Any]) -> list[Any]:
        import numpy as np

        self.feeds.append(feed)
        out = np.full((1, 1, 64, 64), -20.0, dtype=np.float32)
        out[0, 0, 16:48, 16:48] = 20.0
        return [out]


def _install_fake_birefnet(monkeypatch: pytest.MonkeyPatch) -> _FakeBiRefNetSession:
    session = _FakeBiRefNetSession()
    sessions_pkg = types.ModuleType("rembg.sessions")
    mod = types.ModuleType("rembg.sessions.birefnet_general")
    mod.BiRefNetSessionGeneral = _FakeBiRefNetSession  # type: ignore[attr-defined]
    bg = types.ModuleType("rembg.bg")

    def naive_cutout(img: Image.Image, mask: Image.Image) -> Image.Image:
        out = img.convert("RGBA")
        out.putalpha(mask)
        return out

    bg.naive_cutout = naive_cutout  # type: ignore[attr-defined]
    rembg = types.ModuleType("rembg")
    rembg.remove = lambda *a, **k: pytest.fail("rembg.remove must not be used")  # type: ignore[attr-defined]
    for name, module in {
        "rembg": rembg,
        "rembg.sessions": sessions_pkg,
        "rembg.sessions.birefnet_general": mod,
        "rembg.bg": bg,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(registry, "get_background_remover", lambda s: session)
    return session


def test_birefnet_mask_matches_reference_math() -> None:
    import numpy as np

    out = np.full((1, 1, 4, 4), -20.0, dtype=np.float32)
    out[0, 0, 1:3, 1:3] = 20.0
    mask = background.birefnet_mask(out, (8, 8))
    assert mask.mode == "L"
    assert mask.size == (8, 8)
    assert mask.getpixel((4, 4)) == 255  # inside the square
    assert mask.getpixel((0, 0)) == 0  # background


def test_birefnet_path_uses_feed_constants_and_crops(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    session = _install_fake_birefnet(monkeypatch)
    result = BiRefNetRemover(settings).remove(Image.new("RGB", (80, 80), (10, 200, 10)))
    assert session.feeds[0]["mean"] == (0.485, 0.456, 0.406)
    assert session.feeds[0]["std"] == (0.229, 0.224, 0.225)
    assert session.feeds[0]["size"] == (1024, 1024)
    assert result.mode == "RGBA"
    # The square is half the image; LANCZOS ringing may widen the bbox a little.
    assert 40 <= result.width < 80
    assert 40 <= result.height < 80


def test_remove_many_equals_sequential_and_yields_empty_errors(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _install_fake_birefnet(monkeypatch)
    remover = BiRefNetRemover(settings, min_coverage=0.2)
    images = [Image.new("RGB", (80 + 8 * i, 80), (i, 0, 0)) for i in range(5)]
    expected = [remover.remove(img) for img in images]
    got = list(remover.remove_many(range(5), load=lambda i: images[i]))
    assert [g.tobytes() for g in got if isinstance(g, Image.Image)] == [
        e.tobytes() for e in expected
    ]
    strict = BiRefNetRemover(settings, min_coverage=0.9)  # square covers 25 %
    results = list(strict.remove_many(range(3), load=lambda i: images[i]))
    assert len(results) == 3
    assert all(isinstance(r, EmptyCutoutError) for r in results)


def test_non_birefnet_session_falls_back_to_rembg_remove(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    calls = _install_fake_rembg(monkeypatch, lambda img: _rgba_with_square(100, (10, 10, 60, 40)))
    got = list(
        BiRefNetRemover(settings).remove_many(
            [1, 2], load=lambda _: Image.new("RGB", (100, 100), "white")
        )
    )
    assert len(calls) == 2
    assert all(isinstance(g, Image.Image) and g.size == (50, 30) for g in got)


def test_birefnet_mask_constant_output_is_an_empty_mask() -> None:
    import warnings

    import numpy as np

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 0/0 must not even warn
        mask = background.birefnet_mask(np.full((1, 1, 4, 4), 3.0, dtype=np.float32), (8, 6))
    assert mask.mode == "L"
    assert mask.size == (8, 6)
    assert mask.getextrema() == (0, 0)


def test_constant_model_output_raises_empty_cutout(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    session = _install_fake_birefnet(monkeypatch)

    def flat_run(_outputs: Any, feed: dict[str, Any]) -> list[Any]:
        import numpy as np

        return [np.zeros((1, 1, 64, 64), dtype=np.float32)]

    monkeypatch.setattr(session, "run", flat_run)
    with pytest.raises(EmptyCutoutError):
        BiRefNetRemover(settings).remove(Image.new("RGB", (40, 40), "white"))


def test_fallback_inference_runs_under_the_infer_lock(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    import threading
    import time

    remover = BiRefNetRemover(settings)
    state = {"active": 0, "max": 0, "unlocked_calls": 0}
    guard = threading.Lock()

    def produce(img: Image.Image) -> Image.Image:
        if not remover._infer_lock.locked():
            state["unlocked_calls"] += 1
        with guard:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.01)
        with guard:
            state["active"] -= 1
        return _rgba_with_square(100, (10, 10, 60, 40))

    _install_fake_rembg(monkeypatch, produce)
    got = list(remover.remove_many(range(8), load=lambda _: Image.new("RGB", (100, 100), "white")))
    assert all(isinstance(g, Image.Image) for g in got)
    # Direct callers on other threads share the same lock.
    threads = [
        threading.Thread(target=remover.remove, args=(Image.new("RGB", (100, 100)),))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["unlocked_calls"] == 0
    assert state["max"] == 1


def test_remove_many_isolates_a_corrupt_item(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _install_fake_birefnet(monkeypatch)

    def load(i: int) -> Image.Image:
        if i == 2:
            raise OSError("cannot identify image file")
        return Image.new("RGB", (80, 80), (i, 0, 0))

    got = list(BiRefNetRemover(settings).remove_many(range(5), load=load))
    assert len(got) == 5
    assert isinstance(got[2], OSError)
    assert [isinstance(g, Image.Image) for g in got] == [True, True, False, True, True]


# --- real rembg session classes (no model file, no ONNX runtime session) --------


class _FakeOrtSession:
    """Stands in for `ort.InferenceSession`: a centered-square model output."""

    def __init__(self, path: str, **kwargs: Any) -> None:
        self.path = path
        self.runs: list[Any] = []

    def get_providers(self) -> list[str]:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def get_inputs(self) -> list[Any]:
        return [types.SimpleNamespace(name="input")]

    def run(self, _outputs: Any, feed: dict[str, Any]) -> list[Any]:
        import numpy as np

        self.runs.append(feed)
        out = np.full((1, 1, 64, 64), -20.0, dtype=np.float32)
        out[0, 0, 16:48, 16:48] = 20.0
        return [out]


def test_registry_fp16_session_takes_the_locked_birefnet_path(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    import onnxruntime as ort
    import rembg
    from rembg.sessions import sessions_class

    lite: Any = next(c for c in sessions_class if c.name() == settings.ml_bg_model)
    fp32 = tmp_path / "birefnet-general-lite.onnx"
    monkeypatch.setattr(registry, "resolve_device", lambda requested: "cuda")
    monkeypatch.setattr(registry, "ensure_fp16_model", lambda src, dst: dst)
    # No model file and no network: only the class hierarchy and rembg's own code are real.
    monkeypatch.setattr(lite, "download_models", classmethod(lambda cls, *a, **k: str(fp32)))
    monkeypatch.setattr(ort, "InferenceSession", _FakeOrtSession)
    monkeypatch.setattr(
        rembg, "remove", lambda *a, **k: pytest.fail("rembg.remove must not be used")
    )

    session = registry.get_background_remover(settings)
    assert type(session).__name__ == "Fp16Session"
    remover = BiRefNetRemover(settings)
    assert remover._is_birefnet(session)

    prepared = remover.prepare(Image.new("RGB", (60, 60), (10, 200, 10)))
    assert prepared.feed is not None  # fast path, not the fallback
    result = remover.remove(Image.new("RGB", (60, 60), (10, 200, 10)))
    assert result.mode == "RGBA"
    assert len(session.inner_session.runs) == 1  # `remove` inferred via the locked `infer`


def test_birefnet_subclass_overriding_predict_takes_the_fallback(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    from rembg.sessions.birefnet_general import BiRefNetSessionGeneral

    class Plain(BiRefNetSessionGeneral):
        pass

    class Custom(BiRefNetSessionGeneral):
        def predict(self, img: Image.Image, *args: Any, **kwargs: Any) -> list[Image.Image]:
            return [Image.new("L", img.size, 255)]

    plain = object.__new__(Plain)
    custom = object.__new__(Custom)
    remover = BiRefNetRemover(settings)
    assert remover._is_birefnet(plain)
    assert not remover._is_birefnet(custom)

    monkeypatch.setattr(registry, "get_background_remover", lambda s: custom)
    assert remover.prepare(Image.new("RGB", (20, 20))).feed is None
