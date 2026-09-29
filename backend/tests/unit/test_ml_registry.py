"""Unit tests for `ml.registry.get_background_remover` (08-local-vision.md,
VIS-REQ-004/VIS-REQ-029): `rembg` is faked via `sys.modules` and the device is
patched, so no torch, no onnxruntime, no model download and no network."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import ml.registry as registry
from ml.device import onnxruntime_providers
from shared.settings import Settings


class _FakeInnerSession:
    def __init__(self, providers: list[str]) -> None:
        self._providers = providers

    def get_providers(self) -> list[str]:
        return self._providers


class _FakeSession:
    def __init__(self, active_providers: list[str]) -> None:
        self.inner_session = _FakeInnerSession(active_providers)


class _FakeRembg:
    """Stands in for the `rembg` module; records every `new_session` call."""

    def __init__(self, active_providers: list[str]) -> None:
        self.active_providers = active_providers
        self.calls: list[tuple[str, list[str]]] = []
        self.module = types.ModuleType("rembg")
        self.module.new_session = self._new_session  # type: ignore[attr-defined]

    def _new_session(self, model: str, providers: list[str]) -> _FakeSession:
        self.calls.append((model, providers))
        return _FakeSession(self.active_providers)


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


def _install_fake_rembg(monkeypatch: pytest.MonkeyPatch, fake: _FakeRembg, *, device: str) -> None:
    monkeypatch.setitem(sys.modules, "rembg", fake.module)
    monkeypatch.setattr(registry, "resolve_device", lambda requested: device)


def test_background_remover_is_created_once_and_cached(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fake = _FakeRembg(["CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, fake, device="cpu")

    first: Any = registry.get_background_remover(settings)
    second: Any = registry.get_background_remover(settings)

    assert first is second
    assert fake.calls == [(settings.ml_bg_model, onnxruntime_providers("cpu"))]


def test_cuda_with_cpu_only_session_raises_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    broken = _FakeRembg(["CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, broken, device="cuda")

    with pytest.raises(RuntimeError, match="CUDA"):
        registry.get_background_remover(settings)
    assert broken.calls == [(settings.ml_bg_model, onnxruntime_providers("cuda"))]

    working = _FakeRembg(["CUDAExecutionProvider", "CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, working, device="cuda")

    session = registry.get_background_remover(settings)

    assert len(working.calls) == 1
    assert session.inner_session.get_providers()[0] == "CUDAExecutionProvider"


def test_cpu_only_session_is_accepted_on_cpu(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fake = _FakeRembg(["CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, fake, device="cpu")

    session = registry.get_background_remover(settings)

    assert session.inner_session.get_providers() == ["CPUExecutionProvider"]
