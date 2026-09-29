"""Unit tests for `ml.device` (08-local-vision.md, VIS-REQ-029): pure device
selection and onnxruntime provider mapping, exercised with synthetic
availability flags -- no torch import, no network."""

from __future__ import annotations

import pytest

from ml.device import (
    CUDA_PROVIDER_OPTIONS,
    check_session_providers,
    onnxruntime_providers,
    select_device,
)


@pytest.mark.parametrize(
    ("cuda_available", "mps_available", "expected"),
    [
        (True, True, "cuda"),
        (True, False, "cuda"),
        (False, True, "mps"),
        (False, False, "cpu"),
    ],
)
def test_auto_prefers_cuda_then_mps_then_cpu(
    cuda_available: bool, mps_available: bool, expected: str
) -> None:
    result = select_device("auto", cuda_available=cuda_available, mps_available=mps_available)

    assert result == expected


@pytest.mark.parametrize("cuda_available", [True, False])
@pytest.mark.parametrize("mps_available", [True, False])
def test_explicit_cpu_always_returns_cpu(cuda_available: bool, mps_available: bool) -> None:
    result = select_device("cpu", cuda_available=cuda_available, mps_available=mps_available)

    assert result == "cpu"


def test_explicit_cuda_available_returns_cuda() -> None:
    result = select_device("cuda", cuda_available=True, mps_available=False)

    assert result == "cuda"


def test_explicit_cuda_unavailable_raises() -> None:
    with pytest.raises(RuntimeError, match="PACHAPP_ML_DEVICE=cuda"):
        select_device("cuda", cuda_available=False, mps_available=False)


def test_explicit_mps_available_returns_mps() -> None:
    result = select_device("mps", cuda_available=False, mps_available=True)

    assert result == "mps"


def test_explicit_mps_unavailable_raises() -> None:
    with pytest.raises(RuntimeError, match="PACHAPP_ML_DEVICE=mps"):
        select_device("mps", cuda_available=False, mps_available=False)


def test_unknown_device_raises_value_error() -> None:
    with pytest.raises(ValueError, match="tpu"):
        select_device("tpu", cuda_available=False, mps_available=False)


def test_onnxruntime_providers_cuda_includes_cpu_fallback() -> None:
    assert onnxruntime_providers("cuda") == [
        ("CUDAExecutionProvider", CUDA_PROVIDER_OPTIONS),
        "CPUExecutionProvider",
    ]


@pytest.mark.parametrize("device", ["cpu", "mps"])
def test_onnxruntime_providers_non_cuda_is_cpu_only(device: str) -> None:
    assert onnxruntime_providers(device) == ["CPUExecutionProvider"]


def test_cuda_session_without_cuda_provider_raises() -> None:
    with pytest.raises(RuntimeError, match="CUDA provider"):
        check_session_providers("cuda", ["CPUExecutionProvider"])


def test_cuda_session_with_cuda_provider_passes() -> None:
    check_session_providers("cuda", ["CUDAExecutionProvider", "CPUExecutionProvider"])


@pytest.mark.parametrize("device", ["cpu", "mps"])
def test_cpu_only_session_passes_for_non_cuda_devices(device: str) -> None:
    check_session_providers(device, ["CPUExecutionProvider"])
