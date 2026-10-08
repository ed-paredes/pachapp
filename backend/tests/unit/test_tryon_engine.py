"""CatVTONEngine and FakeTryOnEngine without a GPU: a fake pipeline stands in for CatVTON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tryon.engine import (
    CatVTONEngine,
    TryOnBlankOutput,
    TryOnError,
    TryOnOutOfMemory,
    TryOnParams,
    TryOnUnavailable,
)
from tryon.fake_engine import FakeTryOnEngine

PARAMS = TryOnParams(
    width=48, height=64, steps=4, guidance=2.5, seed=1, oom_retry_width=24, oom_retry_height=32
)


class FakeOOM(Exception):
    pass


class FakeScheduler:
    def __init__(self) -> None:
        self.stepped = 0

    def step(self, model_output: Any, timestep: Any, sample: Any, eta: float = 0.0) -> Any:
        self.stepped += 1
        return sample


class FakePipeline:
    """Runs `steps` scheduler steps and returns a noisy image of the requested size."""

    def __init__(self, *, oom_calls: int = 0, blank: bool = False) -> None:
        self.noise_scheduler = FakeScheduler()
        self.oom_calls = oom_calls
        self.blank = blank
        self.sizes: list[tuple[int, int]] = []

    def __call__(self, **kwargs: Any) -> list[Image.Image]:
        size = (kwargs["width"], kwargs["height"])
        self.sizes.append(size)
        assert kwargs["image"].size == size and kwargs["mask"].size == size
        assert kwargs["condition_image"].mode == "RGB"
        for _ in range(kwargs["num_inference_steps"]):
            self.noise_scheduler.step(None, 0, None)
        if self.oom_calls > 0:
            self.oom_calls -= 1
            raise FakeOOM
        if self.blank:
            return [Image.new("RGB", size, (0, 0, 0))]
        image = Image.new("RGB", size, (0, 0, 0))
        image.paste((255, 255, 255), (0, 0, size[0] // 2, size[1]))
        return [image]


def images() -> tuple[Image.Image, Image.Image, Image.Image]:
    return (
        Image.new("RGB", (30, 40), (10, 20, 30)),
        Image.new("RGBA", (20, 20), (200, 10, 10, 255)),
        Image.new("L", (30, 40), 255),
    )


def make_engine(pipeline: FakePipeline, calls: list[int] | None = None) -> CatVTONEngine:
    def factory() -> FakePipeline:
        if calls is not None:
            calls.append(1)
        return pipeline

    return CatVTONEngine(
        Path("/nonexistent"),
        base_revision=None,
        attn_revision=None,
        device="cpu",
        pipeline_factory=factory,
        is_oom=lambda exc: isinstance(exc, FakeOOM),
    )


def test_lazy_load_then_reuse() -> None:
    loads: list[int] = []
    engine = make_engine(FakePipeline(), loads)
    assert not engine.loaded and loads == []
    engine.dress(*images(), params=PARAMS)
    engine.dress(*images(), params=PARAMS)
    assert engine.loaded and loads == [1]


def test_dress_returns_image_at_working_size() -> None:
    pipeline = FakePipeline()
    result = make_engine(pipeline).dress(*images(), params=PARAMS)
    assert result.size == (48, 64)
    assert pipeline.sizes == [(48, 64)]


def test_on_step_counts_diffusion_steps_and_stops_after_dress() -> None:
    pipeline = FakePipeline()
    engine = make_engine(pipeline)
    steps: list[int] = []
    engine.dress(*images(), params=PARAMS, on_step=lambda: steps.append(1))
    assert len(steps) == PARAMS.steps
    engine.dress(*images(), params=PARAMS)  # no callback: the wrapper must stay harmless
    assert len(steps) == PARAMS.steps
    assert pipeline.noise_scheduler.stepped == 2 * PARAMS.steps


def test_scheduler_step_keeps_its_signature() -> None:
    import inspect

    pipeline = FakePipeline()
    before = inspect.signature(pipeline.noise_scheduler.step)
    make_engine(pipeline).dress(*images(), params=PARAMS)
    assert inspect.signature(pipeline.noise_scheduler.step) == before


def test_oom_retries_once_at_the_retry_size() -> None:
    pipeline = FakePipeline(oom_calls=1)
    result = make_engine(pipeline).dress(*images(), params=PARAMS)
    assert pipeline.sizes == [(48, 64), (24, 32)]
    assert result.size == (24, 32)


def test_second_oom_raises_out_of_memory() -> None:
    pipeline = FakePipeline(oom_calls=5)
    with pytest.raises(TryOnOutOfMemory):
        make_engine(pipeline).dress(*images(), params=PARAMS)
    assert len(pipeline.sizes) == 2


def test_non_oom_errors_are_not_retried() -> None:
    class Boom(FakePipeline):
        def __call__(self, **kwargs: Any) -> list[Image.Image]:
            self.sizes.append((kwargs["width"], kwargs["height"]))
            raise RuntimeError("boom")

    pipeline = Boom()
    with pytest.raises(RuntimeError, match="boom"):
        make_engine(pipeline).dress(*images(), params=PARAMS)
    assert len(pipeline.sizes) == 1


def test_blank_output_raises() -> None:
    with pytest.raises(TryOnBlankOutput):
        make_engine(FakePipeline(blank=True)).dress(*images(), params=PARAMS)


def test_unload_drops_pipeline_and_next_dress_reloads() -> None:
    loads: list[int] = []
    engine = make_engine(FakePipeline(), loads)
    engine.dress(*images(), params=PARAMS)
    engine.unload()
    assert not engine.loaded
    engine.dress(*images(), params=PARAMS)
    assert loads == [1, 1]


def test_unload_before_load_is_harmless() -> None:
    engine = make_engine(FakePipeline())
    engine.unload()
    assert not engine.loaded


def test_missing_clone_is_unavailable(tmp_path: Path) -> None:
    engine = CatVTONEngine(tmp_path / "nope", base_revision=None, attn_revision=None, device="cpu")
    with pytest.raises(TryOnUnavailable, match="not a CatVTON clone"):
        engine.dress(*images(), params=PARAMS)
    assert not engine.loaded


def test_import_failure_is_unavailable() -> None:
    def factory() -> Any:
        raise ImportError("no diffusers")

    engine = CatVTONEngine(
        Path("/x"), base_revision=None, attn_revision=None, device="cpu", pipeline_factory=factory
    )
    with pytest.raises(TryOnUnavailable, match="no diffusers"):
        engine.dress(*images(), params=PARAMS)


def test_error_hierarchy() -> None:
    for cls in (TryOnOutOfMemory, TryOnBlankOutput, TryOnUnavailable):
        assert issubclass(cls, TryOnError)


@pytest.mark.parametrize(
    "overrides",
    [
        {"width": 50},
        {"height": 0},
        {"steps": 0},
        {"oom_retry_width": 20},
        {"oom_retry_width": 56},  # larger than width
        {"oom_retry_height": 72},  # larger than height
    ],
)
def test_params_validation(overrides: dict[str, int]) -> None:
    values: dict[str, Any] = {**PARAMS.__dict__, **overrides}
    with pytest.raises(ValueError):
        TryOnParams(**values)


def test_fake_engine_dresses_and_reports_steps() -> None:
    engine = FakeTryOnEngine()
    steps: list[int] = []
    result = engine.dress(*images(), params=PARAMS, on_step=lambda: steps.append(1))
    assert result.size == (48, 64)
    assert result.getpixel((10, 10)) == (200, 10, 10)  # garment colour inside the mask
    assert len(steps) == PARAMS.steps and engine.loaded and engine.calls == [PARAMS]
    engine.unload()
    assert not engine.loaded and engine.unloads == 1


def test_fake_engine_raises_configured_error() -> None:
    engine = FakeTryOnEngine(error=TryOnBlankOutput("flat"))
    with pytest.raises(TryOnBlankOutput):
        engine.dress(*images(), params=PARAMS)
