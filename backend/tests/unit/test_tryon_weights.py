"""fp16 safetensors copy of the base checkpoint and fp16 model building (lower load RAM peak)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import load_file

from tryon.engine import default_dtype
from tryon.weights import UNET_FILE, fp16_base_checkpoint


def _base(root: Path) -> Path:
    base = root / "snapshots" / "abc123"
    (base / "unet").mkdir(parents=True)
    (base / "scheduler").mkdir()
    (base / "unet" / "config.json").write_text(json.dumps({"in_channels": 9}), encoding="utf-8")
    (base / "scheduler" / "scheduler_config.json").write_text("{}", encoding="utf-8")
    weights = {"conv.weight": torch.randn(4, 3), "conv.bias": torch.randn(4)}
    torch.save(weights, base / "unet" / "diffusion_pytorch_model.bin")
    return base


def test_converts_the_unet_to_fp16_safetensors(tmp_path: Path) -> None:
    base = _base(tmp_path)
    original = torch.load(base / "unet" / "diffusion_pytorch_model.bin", weights_only=True)

    out = fp16_base_checkpoint(base, tmp_path / "cache")

    assert out == tmp_path / "cache" / "base-fp16-abc123"
    converted = load_file(out / "unet" / UNET_FILE)
    assert set(converted) == set(original)
    for name, tensor in converted.items():
        assert tensor.dtype == torch.float16
        assert torch.equal(tensor, original[name].to(torch.float16))  # same cast as `.to(fp16)`
    assert json.loads((out / "unet" / "config.json").read_text()) == {"in_channels": 9}
    assert (out / "scheduler" / "scheduler_config.json").is_file()
    assert [p.name for p in (tmp_path / "cache").iterdir()] == ["base-fp16-abc123"]  # no temp left


def test_a_converted_copy_is_reused(tmp_path: Path) -> None:
    base = _base(tmp_path)
    first = fp16_base_checkpoint(base, tmp_path / "cache")
    (base / "unet" / "diffusion_pytorch_model.bin").unlink()  # a second call must not need it

    assert fp16_base_checkpoint(base, tmp_path / "cache") == first


def test_falls_back_to_the_original_when_it_cannot_convert(tmp_path: Path) -> None:
    base = _base(tmp_path)
    (base / "unet" / "diffusion_pytorch_model.bin").write_bytes(b"not a checkpoint")

    out = fp16_base_checkpoint(base, tmp_path / "cache")

    assert out == base
    assert list((tmp_path / "cache").iterdir()) == []  # the half-built copy is removed


def test_default_dtype_is_scoped() -> None:
    assert torch.get_default_dtype() == torch.float32
    with default_dtype(torch.float16):
        assert torch.zeros(1).dtype == torch.float16
        assert torch.nn.Linear(2, 2).weight.dtype == torch.float16
    assert torch.get_default_dtype() == torch.float32


def test_default_dtype_is_restored_after_an_error() -> None:
    with pytest.raises(RuntimeError), default_dtype(torch.float16):
        raise RuntimeError("load failed")
    assert torch.get_default_dtype() == torch.float32
