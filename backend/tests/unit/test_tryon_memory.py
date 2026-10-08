"""GPU unload hooks and the release-before-CatVTON entry point, without a GPU."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from PIL import Image

import ml.registry as registry
from shared.settings import Settings
from tryon.memory import release_resident_models, resident_unloaders
from worker.ai import AiModels, LazyModels
from worker.runner import StepContext
from worker.steps.cutout import CutoutEngine


class FakeEmbedder:
    dim = 2
    model_id = "fake"

    def embed_image(self, img: Image.Image) -> np.ndarray:
        return np.zeros(2, dtype=np.float32)


class FakeClassifier:
    def classify(self, img_emb: np.ndarray, *, needs_review_threshold: float | None = None) -> Any:
        raise NotImplementedError


class FakeRemover:
    def remove(self, img: Image.Image) -> Image.Image:
        return img.convert("RGBA")


class FakeParser:
    name = "fake"
    revision = None

    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def fake_models(released: list[int] | None = None) -> LazyModels:
    release = (lambda: released.append(1)) if released is not None else None
    return LazyModels(lambda: AiModels(FakeEmbedder(), FakeClassifier(), release=release))


def step_context() -> StepContext:
    session_factory: Any = None  # the plain-remover path never opens a session
    return StepContext(
        job_id="j",
        garment_id="g",
        settings=Settings.model_construct(),
        session_factory=session_factory,
    )


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    registry.reset_registry()
    yield
    registry.reset_registry()


def test_lazy_models_unload_drops_and_rebuilds() -> None:
    built: list[int] = []
    released: list[int] = []

    def factory() -> AiModels:
        built.append(1)
        return AiModels(FakeEmbedder(), FakeClassifier(), release=lambda: released.append(1))

    models = LazyModels(factory)
    assert models.unload() is False  # nothing loaded yet
    first = models.get()
    assert models.get() is first and built == [1]
    assert models.unload() is True and released == [1]
    assert models.get() is not first and built == [1, 1]


def test_lazy_models_unload_without_release_hook() -> None:
    models = fake_models()
    models.get()
    assert models.unload() is True
    assert models.unload() is False


def test_registry_unload_embedder_and_remover() -> None:
    assert registry.unload_embedder() is False
    assert registry.unload_background_remover() is False
    registry._embedder = object()  # ty: ignore[invalid-assignment]
    registry._bg_session = object()
    assert registry.unload_embedder() is True and registry._embedder is None
    assert registry._bg_session is not None  # the other model stays
    assert registry.unload_background_remover() is True and registry._bg_session is None
    assert registry.unload_embedder() is False


def test_cutout_engine_unload_closes_parser_and_rebuilds() -> None:
    removers: list[FakeRemover] = []
    parser = FakeParser()

    def remover_factory() -> Any:
        removers.append(FakeRemover())
        return removers[-1]

    engine = CutoutEngine(remover_factory, lambda: parser)  # ty: ignore[invalid-argument-type]
    assert engine.unload() is False
    engine.cut(step_context(), Image.new("RGB", (8, 8), (1, 2, 3)))
    assert len(removers) == 1
    engine._parser = parser  # as if a parsed cut had run
    assert engine.unload() is True and parser.closed == 1
    engine.cut(step_context(), Image.new("RGB", (8, 8), (1, 2, 3)))
    assert len(removers) == 2  # rebuilt lazily


def test_release_runs_every_unloader_even_when_one_fails() -> None:
    calls: list[str] = []

    def boom() -> None:
        calls.append("boom")
        raise RuntimeError("cuda")

    failed = release_resident_models([lambda: calls.append("a"), boom, lambda: calls.append("c")])
    assert calls == ["a", "boom", "c"] and failed == 1


def test_resident_unloaders_release_all_three_models() -> None:
    parser = FakeParser()
    engine = CutoutEngine(lambda: FakeRemover(), lambda: parser)  # ty: ignore[invalid-argument-type]
    engine._remover = FakeRemover()
    engine._parser = parser
    released: list[int] = []
    models = fake_models(released)
    models.get()
    registry._bg_session = object()

    assert release_resident_models(resident_unloaders(engine, models)) == 0
    assert parser.closed == 1 and engine._remover is None
    assert registry._bg_session is None
    assert released == [1]
    assert models.unload() is False  # already dropped
