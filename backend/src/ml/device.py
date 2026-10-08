"""Device selection for the local vision stack (08-local-vision.md).

`select_device` is a pure function (no torch import, easy to unit-test with
synthetic availability flags, VIS-REQ-029); `resolve_device` is the thin
wrapper that actually asks torch what's available. `onnxruntime_providers`
maps a resolved device to the ordered provider list `rembg`/`onnxruntime`
should try, so BiRefNet runs on the same device as the embedder.
"""

from __future__ import annotations

import gc
from collections.abc import Sequence
from typing import Any

Device = str  # "cpu" | "cuda" | "mps"

# BiRefNet at 1024 px is memory-hungry: HEURISTIC skips cuDNN's exhaustive
# conv-algorithm search (which allocates huge workspaces) and kSameAsRequested
# stops the arena from doubling allocations. Measured 14 s -> 4.2 s per image
# for fp32 on the 6 GB reference GPU (VIS-REQ-026).
CUDA_PROVIDER_OPTIONS: dict[str, str] = {
    "cudnn_conv_algo_search": "HEURISTIC",
    "arena_extend_strategy": "kSameAsRequested",
    # Do not let cuDNN pick algorithms that need the largest workspace.
    "cudnn_conv_use_max_workspace": "0",
}

# Hard cap for onnxruntime's CUDA arena when running the fp16 BiRefNet-lite
# model. Without a cap the arena grows to fill the free VRAM (~5.5 GB measured
# on the 6 GB reference GPU) although the model peaks at ~3.3 GB at 1024 px
# (a 3 GiB cap fails with an ORT out-of-memory error). Once SigLIP (torch,
# ~1 GB) and the desktop share the GPU, the uncapped arena spills to shared
# system memory and `session.run` slows down 5-10x (0.6 s -> 3-6 s, measured by
# reserving VRAM in the same process); capped it stays ~0.6 s. 4 GiB leaves
# headroom over the measured peak. Only valid for that model: fp32 or the
# non-lite variants need more and would fail with out-of-memory.
LITE_FP16_GPU_MEM_LIMIT_BYTES = 4 * 1024**3


def select_device(
    requested: str,
    *,
    cuda_available: bool,
    mps_available: bool,
) -> Device:
    """Resolve `PACHAPP_ML_DEVICE` (`auto`/`cpu`/`cuda`/`mps`) to a concrete
    device, given availability flags. Pure and torch-free so it can be
    exercised with synthetic flags in unit tests (VIS-REQ-029).

    `auto` prefers `cuda` > `mps` > `cpu`. An explicit `cuda`/`mps` request
    that isn't available raises a clear error rather than silently falling
    back to `cpu` (08-local-vision.md: a silent CPU fallback would blow the
    <2s/<10s per-garment performance budget, VIS-REQ-026, without saying so).
    """
    if requested == "auto":
        if cuda_available:
            return "cuda"
        if mps_available:
            return "mps"
        return "cpu"

    if requested == "cpu":
        return "cpu"

    if requested == "cuda":
        if not cuda_available:
            raise RuntimeError(
                "PACHAPP_ML_DEVICE=cuda was requested but torch.cuda.is_available() is "
                "False. Check the NVIDIA driver and that torch was installed from the "
                "CUDA index (see backend/pyproject.toml), or set PACHAPP_ML_DEVICE=auto "
                "or PACHAPP_ML_DEVICE=cpu."
            )
        return "cuda"

    if requested == "mps":
        if not mps_available:
            raise RuntimeError(
                "PACHAPP_ML_DEVICE=mps was requested but torch.backends.mps.is_available() "
                "is False. MPS is only available on Apple Silicon. Set PACHAPP_ML_DEVICE=auto "
                "or PACHAPP_ML_DEVICE=cpu instead."
            )
        return "mps"

    raise ValueError(
        f"PACHAPP_ML_DEVICE must be one of 'auto', 'cpu', 'cuda', 'mps'. Got: {requested!r}."
    )


def resolve_device(requested: str) -> Device:
    """`select_device`, but querying torch for real availability. Imports
    torch lazily so importing this module never pulls torch in."""
    import torch

    return select_device(
        requested,
        cuda_available=torch.cuda.is_available(),
        mps_available=torch.backends.mps.is_available(),
    )


def free_gpu_memory() -> None:
    """Collect garbage, then hand cached CUDA blocks back to the driver. Call it after
    dropping the last reference to a model; torch is imported only if installed."""
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def onnxruntime_providers(device: Device, *, gpu_mem_limit: int | None = None) -> list[Any]:
    """Ordered onnxruntime execution providers for `rembg`'s BiRefNet session,
    matching the resolved torch device. onnxruntime has no MPS provider, so
    `mps` (like `cpu`) runs BiRefNet on CPU. The CUDA provider is a
    `(name, options)` tuple, which onnxruntime accepts in `providers`;
    `gpu_mem_limit` (bytes) adds a hard cap on its memory arena."""
    if device == "cuda":
        options = dict(CUDA_PROVIDER_OPTIONS)
        if gpu_mem_limit is not None:
            options["gpu_mem_limit"] = str(gpu_mem_limit)
        return [("CUDAExecutionProvider", options), "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def check_session_providers(device: Device, active_providers: Sequence[str]) -> None:
    """Fail loudly when an onnxruntime session for a `cuda` device ended up
    CPU-only. onnxruntime drops an unloadable CUDA provider (e.g. a CUDA major
    mismatch between onnxruntime-gpu and the libraries torch installs) with
    only a warning, which would put BiRefNet on CPU silently -- the same
    failure `select_device` refuses for an explicit `cuda` request."""
    if device == "cuda" and "CUDAExecutionProvider" not in active_providers:
        raise RuntimeError(
            "BiRefNet was requested on cuda but onnxruntime could not load its CUDA "
            f"provider (active providers: {active_providers}). onnxruntime-gpu and torch "
            "must use the same CUDA major (see backend/pyproject.toml), or set "
            "PACHAPP_ML_DEVICE=cpu."
        )
