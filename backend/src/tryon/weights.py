"""Lower the host-RAM peak of loading CatVTON (V1d: 5.9 GB RSS, in a 7.9 GB WSL).

The base repo ships its UNet only as a pickled fp32 `.bin`: diffusers reads all 3.4 GB into
memory, builds an fp32 model, and only then does the pipeline cast to fp16. `fp16_base_checkpoint`
converts the needed components once into an fp16 safetensors copy (memory-mapped on load);
together with building the models directly in fp16 (`engine.default_dtype`) the load peaks at
~1.4 GB instead of ~5.6 GB (measured on CPU, `ru_maxrss`). The conversion itself maps the `.bin`
and writes 1.7 GB; the copy lives under the ML cache dir and is reused by every later load.

This module also resolves the Hub snapshots from the local cache first (`cached_snapshot`), so a
load with everything cached makes no network call.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

logger = logging.getLogger(__name__)

UNET_FILE = "diffusion_pytorch_model.safetensors"
_UNET_BIN = "diffusion_pytorch_model.bin"
# CatVTONPipeline loads its VAE from this repo (unpinned) with `from_pretrained`.
VAE_MODEL = "stabilityai/sd-vae-ft-mse"


def cached_snapshot(repo_id: str, revision: str | None, allow_patterns: Sequence[str]) -> str:
    """Local path of a Hub snapshot. Tries the local cache first (`local_files_only`, no network
    call, not even a revision check); downloads only when it is not cached yet."""
    try:
        return snapshot_download(
            repo_id, revision=revision, allow_patterns=list(allow_patterns), local_files_only=True
        )
    except LocalEntryNotFoundError:
        logger.info("%s is not cached yet; downloading it from the Hugging Face Hub", repo_id)
        return snapshot_download(repo_id, revision=revision, allow_patterns=list(allow_patterns))


@contextmanager
def hub_offline_if_cached(repo_id: str) -> Iterator[bool]:
    """Within the block the Hub is offline (`HF_HUB_OFFLINE`) when `repo_id` is already cached,
    so third-party code that loads it by name (CatVTON's VAE) makes no network call. Scoped to
    the block: the worker's other models may still need a first download. Yields whether it is
    offline. `huggingface_hub` reads the flag at import, so the module constant is patched too."""
    from huggingface_hub import constants

    try:
        snapshot_download(repo_id, local_files_only=True)
    except LocalEntryNotFoundError:
        logger.info(
            "%s is not cached yet; it will be downloaded from the Hugging Face Hub", repo_id
        )
        yield False
        return
    previous_env = os.environ.get("HF_HUB_OFFLINE")
    previous_flag = constants.HF_HUB_OFFLINE
    os.environ["HF_HUB_OFFLINE"] = "1"
    constants.HF_HUB_OFFLINE = True
    try:
        yield True
    finally:
        constants.HF_HUB_OFFLINE = previous_flag
        if previous_env is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_env


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


def _is_complete(target: Path) -> bool:
    return (target / "unet" / UNET_FILE).is_file() and (target / "scheduler").is_dir()


def fp16_base_checkpoint(base_path: str | Path, cache_dir: Path) -> Path:
    """An fp16 safetensors copy of the base checkpoint's `unet/` and `scheduler/` under
    `cache_dir`, built on first use (named after the pinned snapshot, so a new revision gets a
    new copy). An incomplete copy (an interrupted or damaged earlier one) is rebuilt and swapped
    in. Falls back to `base_path` when it cannot convert (e.g. no `.bin`, disk full)."""
    base = Path(base_path)
    target = cache_dir / f"base-fp16-{base.name}"
    if _is_complete(target):
        return target
    tmp = cache_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _convert(base, tmp)
        stale: Path | None = None
        if target.exists():
            # `os.replace` cannot overwrite a non-empty directory: move the partial copy aside.
            stale = cache_dir / f".{target.name}.{uuid.uuid4().hex}.old"
            os.replace(target, stale)
        os.replace(tmp, target)
        if stale is not None:
            shutil.rmtree(stale, ignore_errors=True)
    except Exception:  # noqa: BLE001 - the unconverted checkpoint still loads, just heavier
        logger.exception("could not convert %s to fp16 safetensors; loading it as is", base)
        shutil.rmtree(tmp, ignore_errors=True)
        return base
    logger.info("converted the base checkpoint to fp16 safetensors at %s", target)
    return target
