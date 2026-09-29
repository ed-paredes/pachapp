"""Unit tests for `ml.registry.get_background_remover` (08-local-vision.md,
VIS-REQ-004/VIS-REQ-029): `rembg` is faked via `sys.modules` and the device is
patched, so no torch, no onnxruntime, no model download and no network."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import onnxruntime as ort
import pytest

import ml.registry as registry
from ml.device import CUDA_PROVIDER_OPTIONS, onnxruntime_providers
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
    """Stands in for the `rembg` module; records every `new_session` call and
    every direct construction of a session class (the fp16 path)."""

    def __init__(self, active_providers: list[str], fp32_file: Path | None = None) -> None:
        self.active_providers = active_providers
        self.calls: list[tuple[str, list[Any]]] = []
        self.fp16_calls: list[tuple[str, list[Any], str]] = []
        self.fp16_sess_opts: list[Any] = []
        self.module = types.ModuleType("rembg")
        self.module.new_session = self._new_session  # type: ignore[attr-defined]
        fake = self
        fp32 = fp32_file

        class _FakeSessionClass(_FakeSession):
            # Same shape as rembg's `BaseSession.__init__`: `providers` is popped
            # from kwargs, the rest is forwarded to `download_models`.
            def __init__(self, model_name: str, sess_opts: Any, *args: Any, **kwargs: Any) -> None:
                super().__init__(fake.active_providers)
                providers = kwargs.pop("providers")
                fake.fp16_sess_opts.append(sess_opts)
                file = type(self).download_models(*args, **kwargs)
                fake.fp16_calls.append((model_name, providers, file))

            @classmethod
            def name(cls) -> str:
                return "birefnet-general-lite"

            @classmethod
            def download_models(cls, *args: Any, **kwargs: Any) -> str:
                return str(fp32)

        sessions = types.ModuleType("rembg.sessions")
        sessions.sessions_class = [_FakeSessionClass]  # type: ignore[attr-defined]
        self.sessions_module = sessions

    def _new_session(self, model: str, providers: list[Any]) -> _FakeSession:
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
    monkeypatch.setitem(sys.modules, "rembg.sessions", fake.sessions_module)
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
    assert fake.fp16_calls == []


def test_cuda_with_cpu_only_session_raises_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    fp32 = tmp_path / "birefnet-general-lite.onnx"
    monkeypatch.setattr(registry, "ensure_fp16_model", lambda src, dst: dst)
    broken = _FakeRembg(["CPUExecutionProvider"], fp32)
    _install_fake_rembg(monkeypatch, broken, device="cuda")

    with pytest.raises(RuntimeError, match="CUDA"):
        registry.get_background_remover(settings)
    assert len(broken.fp16_calls) == 1

    working = _FakeRembg(["CUDAExecutionProvider", "CPUExecutionProvider"], fp32)
    _install_fake_rembg(monkeypatch, working, device="cuda")

    session = registry.get_background_remover(settings)

    assert len(working.fp16_calls) == 1
    assert session.inner_session.get_providers()[0] == "CUDAExecutionProvider"


def test_cpu_only_session_is_accepted_on_cpu(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fake = _FakeRembg(["CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, fake, device="cpu")

    session = registry.get_background_remover(settings)

    assert session.inner_session.get_providers() == ["CPUExecutionProvider"]


def test_cuda_with_fp16_uses_fp16_file_and_provider_options(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    fp32 = tmp_path / "birefnet-general-lite.onnx"
    converted: list[tuple[Path, Path]] = []

    def fake_ensure(src: Path, dst: Path) -> Path:
        converted.append((src, dst))
        return dst

    monkeypatch.setattr(registry, "ensure_fp16_model", fake_ensure)
    fake = _FakeRembg(["CUDAExecutionProvider", "CPUExecutionProvider"], fp32)
    _install_fake_rembg(monkeypatch, fake, device="cuda")

    registry.get_background_remover(settings)

    fp16 = tmp_path / "birefnet-general-lite.fp16.onnx"
    assert converted == [(fp32, fp16)]
    assert fake.calls == []
    assert fake.fp16_calls == [("birefnet-general-lite", onnxruntime_providers("cuda"), str(fp16))]
    sess_opts = fake.fp16_sess_opts[0]
    assert sess_opts is not None
    assert isinstance(sess_opts, ort.SessionOptions)
    cuda_entry = fake.fp16_calls[0][1][0]
    assert cuda_entry == ("CUDAExecutionProvider", CUDA_PROVIDER_OPTIONS)


def test_cuda_with_fp16_disabled_keeps_fp32(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr(settings, "ml_bg_fp16", False)
    fake = _FakeRembg(["CUDAExecutionProvider", "CPUExecutionProvider"])
    _install_fake_rembg(monkeypatch, fake, device="cuda")

    registry.get_background_remover(settings)

    assert fake.calls == [(settings.ml_bg_model, onnxruntime_providers("cuda"))]
    assert fake.fp16_calls == []


def test_fp16_session_options_apply_omp_num_threads(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    monkeypatch.setattr(registry, "ensure_fp16_model", lambda src, dst: dst)
    fake = _FakeRembg(["CUDAExecutionProvider"], tmp_path / "birefnet-general-lite.onnx")
    _install_fake_rembg(monkeypatch, fake, device="cuda")

    registry.get_background_remover(settings)

    sess_opts = fake.fp16_sess_opts[0]
    assert sess_opts.inter_op_num_threads == 3
    assert sess_opts.intra_op_num_threads == 3


def test_fp16_session_options_default_without_omp_num_threads(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setattr(registry, "ensure_fp16_model", lambda src, dst: dst)
    fake = _FakeRembg(["CUDAExecutionProvider"], tmp_path / "birefnet-general-lite.onnx")
    _install_fake_rembg(monkeypatch, fake, device="cuda")

    registry.get_background_remover(settings)

    assert fake.fp16_sess_opts[0].intra_op_num_threads == 0


def test_cuda_fp16_unknown_model_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "ml_bg_model", "no-such-model")
    fake = _FakeRembg(["CUDAExecutionProvider"], tmp_path / "birefnet-general-lite.onnx")
    _install_fake_rembg(monkeypatch, fake, device="cuda")

    with pytest.raises(ValueError, match="no-such-model"):
        registry.get_background_remover(settings)
    assert fake.fp16_calls == []
