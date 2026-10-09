"""fp16 safetensors copy of the base checkpoint and fp16 model building (lower load RAM peak)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import torch
from huggingface_hub import constants
from huggingface_hub.errors import LocalEntryNotFoundError
from safetensors.torch import load_file

from tryon import weights
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


def test_a_partial_copy_is_repaired_not_reconverted_forever(tmp_path: Path) -> None:
    base = _base(tmp_path)
    cache = tmp_path / "cache"
    partial = cache / "base-fp16-abc123"
    (partial / "unet").mkdir(parents=True)  # the scheduler and the weights are missing
    (partial / "unet" / "config.json").write_text("{}", encoding="utf-8")
    (partial / "junk.txt").write_text("x", encoding="utf-8")

    out = fp16_base_checkpoint(base, cache)

    assert out == partial
    assert (out / "unet" / UNET_FILE).is_file()
    assert (out / "scheduler").is_dir()
    assert not (out / "junk.txt").exists()  # replaced, not merged
    assert [p.name for p in cache.iterdir()] == ["base-fp16-abc123"]  # no temp or stale dir left
    (base / "unet" / "diffusion_pytorch_model.bin").unlink()
    assert fp16_base_checkpoint(base, cache) == out  # now reused


def test_a_partial_copy_is_kept_when_the_rebuild_fails(tmp_path: Path) -> None:
    base = _base(tmp_path)
    (base / "unet" / "diffusion_pytorch_model.bin").write_bytes(b"not a checkpoint")
    partial = tmp_path / "cache" / "base-fp16-abc123"
    partial.mkdir(parents=True)

    assert fp16_base_checkpoint(base, tmp_path / "cache") == base
    assert partial.is_dir()


def test_cached_snapshot_does_not_touch_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake(repo_id: str, **kwargs: object) -> str:
        calls.append({"repo": repo_id, **kwargs})
        return "/cache/snap"

    monkeypatch.setattr(weights, "snapshot_download", fake)

    assert weights.cached_snapshot("a/b", "rev1", ["unet/*"]) == "/cache/snap"
    assert len(calls) == 1
    assert calls[0]["local_files_only"] is True and calls[0]["revision"] == "rev1"


def test_cached_snapshot_downloads_when_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []

    def fake(repo_id: str, **kwargs: object) -> str:
        calls.append(bool(kwargs.get("local_files_only")))
        if kwargs.get("local_files_only"):
            raise LocalEntryNotFoundError("not cached")
        return "/cache/downloaded"

    monkeypatch.setattr(weights, "snapshot_download", fake)

    assert weights.cached_snapshot("a/b", "rev1", ["unet/*"]) == "/cache/downloaded"
    assert calls == [True, False]


def test_hub_is_offline_only_inside_the_block_when_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(weights, "snapshot_download", lambda repo_id, **kw: "/cache/vae")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False)

    with weights.hub_offline_if_cached("a/vae") as offline:
        assert offline is True
        assert os.environ["HF_HUB_OFFLINE"] == "1" and constants.HF_HUB_OFFLINE is True

    assert "HF_HUB_OFFLINE" not in os.environ and constants.HF_HUB_OFFLINE is False


def test_hub_stays_online_when_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(repo_id: str, **kwargs: object) -> str:
        raise LocalEntryNotFoundError("not cached")

    monkeypatch.setattr(weights, "snapshot_download", fake)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

    with weights.hub_offline_if_cached("a/vae") as offline:
        assert offline is False
        assert "HF_HUB_OFFLINE" not in os.environ
