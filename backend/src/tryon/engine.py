"""Try-on engine contract and the CatVTON implementation (09-virtual-tryon.md §5.2, §12).

`CatVTONEngine` loads the pipeline lazily from the pinned CatVTON clone (external, CC BY-NC-SA
4.0: personal use) and can unload it to give the GPU back to the other models. Tests inject a
`pipeline_factory`, so they need neither a GPU nor the weights.
"""

from __future__ import annotations

import functools
import gc
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from PIL import Image

from tryon.images import is_blank, prepare_garment, prepare_mask, prepare_person

logger = logging.getLogger(__name__)

BASE_MODEL = "booksforcharlie/stable-diffusion-inpainting"
ATTN_MODEL = "zhengchong/CatVTON"
ATTN_VERSION = "mix"
ATTN_SUBFOLDER = "mix-48k-1024"


class TryOnError(Exception):
    """A try-on generation failed."""


class TryOnOutOfMemory(TryOnError):
    """CUDA ran out of memory, also at the retry size."""


class TryOnBlankOutput(TryOnError):
    """The model returned a flat image (fp16 NaNs decode to black)."""


class TryOnUnavailable(TryOnError):
    """The engine cannot load (CatVTON clone, dependencies or weights missing)."""


@dataclass(frozen=True)
class TryOnParams:
    width: int
    height: int
    steps: int
    guidance: float
    seed: int
    # Smaller size retried once after an out-of-memory error.
    oom_retry_width: int
    oom_retry_height: int

    def __post_init__(self) -> None:
        for name in ("width", "height", "oom_retry_width", "oom_retry_height"):
            value = getattr(self, name)
            if value <= 0 or value % 8:
                raise ValueError(f"{name} must be a positive multiple of 8, got {value}")
        if self.steps <= 0:
            raise ValueError(f"steps must be positive, got {self.steps}")
        # A larger retry could only fail again.
        if self.oom_retry_width > self.width or self.oom_retry_height > self.height:
            raise ValueError(
                f"OOM retry size {self.oom_retry_width}x{self.oom_retry_height} "
                f"exceeds {self.width}x{self.height}"
            )


class TryOnEngine(Protocol):
    @property
    def loaded(self) -> bool: ...

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        params: TryOnParams,
        on_step: Callable[[], None] | None = None,
    ) -> Image.Image:
        """One CatVTON pass: dress the masked area of `person` with `garment`.

        Inputs are unprepared (any size, garment possibly an RGBA cutout); `on_step` is
        called once per diffusion step. Raises `TryOnError` subclasses."""
        ...

    def unload(self) -> None:
        """Release the model and its GPU memory; the next `dress` reloads it."""
        ...


def free_gpu_memory() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _is_cuda_oom(exc: BaseException) -> bool:
    try:
        import torch
    except ImportError:
        return False
    return isinstance(exc, torch.cuda.OutOfMemoryError)


class CatVTONEngine:
    def __init__(
        self,
        catvton_dir: Path,
        *,
        base_revision: str | None,
        attn_revision: str | None,
        dtype: Literal["fp16", "fp32"] = "fp16",
        device: str = "cuda",
        pipeline_factory: Callable[[], Any] | None = None,
        is_oom: Callable[[BaseException], bool] = _is_cuda_oom,
    ) -> None:
        self._catvton_dir = catvton_dir
        self._base_revision = base_revision
        self._attn_revision = attn_revision
        self._dtype = dtype
        self._device = device
        self._pipeline_factory = pipeline_factory or self._build_pipeline
        self._is_oom = is_oom
        self._pipeline: Any = None
        self._on_step: Callable[[], None] | None = None

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        params: TryOnParams,
        on_step: Callable[[], None] | None = None,
    ) -> Image.Image:
        pipeline = self._ensure_loaded()
        garment_rgb = prepare_garment(garment)
        size = (params.width, params.height)
        try:
            result = self._run(pipeline, person, garment_rgb, mask, size, params, on_step)
        except Exception as exc:
            if not self._is_oom(exc):
                raise
            retry_size = (params.oom_retry_width, params.oom_retry_height)
            logger.warning("try-on OOM at %dx%d, retrying at %dx%d", *size, *retry_size)
            free_gpu_memory()
            try:
                result = self._run(pipeline, person, garment_rgb, mask, retry_size, params, on_step)
            except Exception as retry_exc:
                if not self._is_oom(retry_exc):
                    raise
                free_gpu_memory()
                raise TryOnOutOfMemory(
                    f"out of memory at {size[0]}x{size[1]} and {retry_size[0]}x{retry_size[1]}"
                ) from retry_exc
        if is_blank(result):
            raise TryOnBlankOutput("the model returned a flat image")
        return result

    def unload(self) -> None:
        self._pipeline = None
        free_gpu_memory()

    def _run(
        self,
        pipeline: Any,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        size: tuple[int, int],
        params: TryOnParams,
        on_step: Callable[[], None] | None,
    ) -> Image.Image:
        import torch

        generator = torch.Generator(device=self._device).manual_seed(params.seed)
        self._on_step = on_step
        try:
            return pipeline(
                image=prepare_person(person, size),
                condition_image=garment,
                mask=prepare_mask(mask, size),
                num_inference_steps=params.steps,
                guidance_scale=params.guidance,
                width=size[0],
                height=size[1],
                generator=generator,
            )[0]
        finally:
            self._on_step = None

    def _ensure_loaded(self) -> Any:
        if self._pipeline is None:
            try:
                pipeline = self._pipeline_factory()
            except (ImportError, OSError) as exc:
                raise TryOnUnavailable(f"cannot load CatVTON: {exc}") from exc
            self._wrap_scheduler(pipeline)
            self._pipeline = pipeline
        return self._pipeline

    def _wrap_scheduler(self, pipeline: Any) -> None:
        """Count diffusion steps: CatVTON's pipeline has no callback (§12.9)."""
        scheduler = pipeline.noise_scheduler
        original_step = scheduler.step

        # `wraps` keeps the signature: the pipeline inspects `step` for `eta`/`generator`.
        @functools.wraps(original_step)
        def counted_step(*args: Any, **kwargs: Any) -> Any:
            out = original_step(*args, **kwargs)
            if self._on_step is not None:
                self._on_step()
            return out

        scheduler.step = counted_step

    def _build_pipeline(self) -> Any:  # pragma: no cover - needs torch, CatVTON and weights
        if not (self._catvton_dir / "model" / "pipeline.py").is_file():
            raise TryOnUnavailable(
                f"not a CatVTON clone: {self._catvton_dir} (run `make tryon-setup`)"
            )
        import torch
        from huggingface_hub import snapshot_download

        if str(self._catvton_dir) not in sys.path:
            sys.path.insert(0, str(self._catvton_dir))
        from model.pipeline import CatVTONPipeline  # ty: ignore[unresolved-import]

        # Only what CatVTONPipeline loads from the base repo (no .ckpt, text encoder, safety
        # checker or VAE: the VAE comes from sd-vae-ft-mse).
        base_path = snapshot_download(
            BASE_MODEL, revision=self._base_revision, allow_patterns=["scheduler/*", "unet/*"]
        )
        attn_path = snapshot_download(
            ATTN_MODEL, revision=self._attn_revision, allow_patterns=[f"{ATTN_SUBFOLDER}/*"]
        )
        return CatVTONPipeline(
            base_ckpt=base_path,
            attn_ckpt=attn_path,
            attn_ckpt_version=ATTN_VERSION,
            # Turing (RTX 20xx) has no fast bf16: fp16 on CUDA (§5.5, §12).
            weight_dtype=torch.float16 if self._dtype == "fp16" else torch.float32,
            device=self._device,
            # The SD safety checker costs VRAM and may swap a mannequin for NSFW.jpg.
            skip_safety_check=True,
            use_tf32=False,
        )
