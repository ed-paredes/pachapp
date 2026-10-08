"""Lower the host-RAM peak of loading CatVTON (V1d: 5.9 GB RSS, in a 7.9 GB WSL).

The base repo ships its UNet only as a pickled fp32 `.bin`: diffusers reads all 3.4 GB into
memory, builds an fp32 model, and only then does the pipeline cast to fp16. `fp16_base_checkpoint`
converts the needed components once into an fp16 safetensors copy (memory-mapped on load);
together with building the models directly in fp16 (`engine.default_dtype`) the load peaks at
~1.4 GB instead of ~5.6 GB (measured on CPU, `ru_maxrss`). The conversion itself maps the `.bin`
and writes 1.7 GB; the copy lives under the ML cache dir and is reused by every later load.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

UNET_FILE = "diffusion_pytorch_model.safetensors"
_UNET_BIN = "diffusion_pytorch_model.bin"


def _convert(base: Path, target: Path) -> None:
    import torch
    from safetensors.torch import save_file

    unet = target / "unet"
    unet.mkdir(parents=True)
    # `mmap`: the fp32 weights are paged in from the file instead of copied into the heap.
    state = torch.load(base / "unet" / _UNET_BIN, map_location="cpu", weights_only=True, mmap=True)
    half = {name: tensor.to(torch.float16).contiguous() for name, tensor in state.items()}
    del state
    save_file(half, unet / UNET_FILE, metadata={"format": "pt"})
    shutil.copy2(base / "unet" / "config.json", unet / "config.json")
    shutil.copytree(base / "scheduler", target / "scheduler")


def fp16_base_checkpoint(base_path: str | Path, cache_dir: Path) -> Path:
    """An fp16 safetensors copy of the base checkpoint's `unet/` and `scheduler/` under
    `cache_dir`, built on first use (named after the pinned snapshot, so a new revision gets a
    new copy). Falls back to `base_path` when it cannot convert (e.g. no `.bin`, disk full)."""
    base = Path(base_path)
    target = cache_dir / f"base-fp16-{base.name}"
    if (target / "unet" / UNET_FILE).is_file() and (target / "scheduler").is_dir():
        return target
    tmp = cache_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _convert(base, tmp)
        os.replace(tmp, target)
    except Exception:  # noqa: BLE001 - the unconverted checkpoint still loads, just heavier
        logger.exception("could not convert %s to fp16 safetensors; loading it as is", base)
        shutil.rmtree(tmp, ignore_errors=True)
        return base
    logger.info("converted the base checkpoint to fp16 safetensors at %s", target)
    return target
