"""Lazy, process-wide model loading (08-local-vision.md, VIS-REQ-004).

Both models load once per process, on first use, never at import time: the
heavy imports (`torch`, `open_clip`, `rembg`) live inside the functions below,
not at module scope, so `import ml.registry` alone stays cheap and `api`
never pays for them even if this module were reachable from it.

Callers MUST call `ml.cache.configure_model_cache(settings.ml_cache_dir)`
before the first call here (VIS-REQ-008): both `rembg` and `huggingface_hub`
read `U2NET_HOME`/`HF_HOME` on first use.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ml.bg_fp16 import ensure_fp16_model, fp16_path, should_use_fp16
from ml.device import (
    LITE_FP16_GPU_MEM_LIMIT_BYTES,
    check_session_providers,
    free_gpu_memory,
    onnxruntime_providers,
    resolve_device,
)
from shared.settings import Settings

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image

logger = logging.getLogger(__name__)

LITE_MODEL_NAME = "birefnet-general-lite"  # the model the arena cap was measured for

_HF_HUB_PREFIX = "hf-hub:"

_lock = threading.Lock()
_bg_session: Any | None = None
_embedder: GarmentEmbedder | None = None


@dataclass
class GarmentEmbedder:
    """A loaded SigLIP embedder, pinned to `PACHAPP_ML_EMBED_REVISION`.

    `dim` is read from the loaded model at load time (a dummy forward pass),
    never hard-coded (VIS-REQ-002/08-local-vision.md interfaces).
    """

    model: Any
    preprocess: Any
    tokenizer: Any
    device: str
    dim: int
    model_id: str  # "<PACHAPP_ML_EMBED_MODEL>@<PACHAPP_ML_EMBED_REVISION>"
    _text_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False, compare=False)

    def embed_image(self, img: Image.Image) -> np.ndarray:
        """L2-normalized float32 embedding, shape `(dim,)`.

        Accepts any PIL mode: EXIF orientation is applied and transparency is
        composited over white (same normalization as the background remover).
        """
        import numpy as np
        import torch

        from ml.background import _to_rgb
        from ml.zero_shot import l2_normalize

        tensor = self.preprocess(_to_rgb(img)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feats = self.model.encode_image(tensor)
        return l2_normalize(np.asarray(feats.float().cpu().numpy()[0], dtype=np.float32))

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """L2-normalized float32 text embeddings, shape `(len(texts), dim)`.

        Cached in-process per exact text, so repeated prompts are encoded once.
        """
        import numpy as np
        import torch

        from ml.zero_shot import l2_normalize

        missing = [t for t in dict.fromkeys(texts) if t not in self._text_cache]
        if missing:
            tokens = self.tokenizer(missing).to(self.device)
            with torch.no_grad():
                feats = self.model.encode_text(tokens)
            arr = l2_normalize(np.asarray(feats.float().cpu().numpy(), dtype=np.float32))
            for text, row in zip(missing, arr, strict=True):
                self._text_cache[text] = row
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._text_cache[t] for t in texts])


def _repo_id(embed_model: str) -> str:
    """Strip open_clip's `hf-hub:` schema prefix, if present, to get a bare
    Hugging Face repo id for `huggingface_hub.snapshot_download`."""
    if embed_model.startswith(_HF_HUB_PREFIX):
        return embed_model[len(_HF_HUB_PREFIX) :]
    return embed_model


def _fp16_session_class(model_name: str) -> Any:
    """rembg's session class for `model_name`, with `download_models` wrapped
    so the model file it returns is the fp16 copy of rembg's fp32 file
    (converted on first use if `make ml-preload` has not done it yet).

    Only the model path changes: rembg's own pre/post-processing (`predict`,
    `normalize`) is inherited untouched, and inputs/outputs stay float32.
    """
    from rembg.sessions import sessions_class

    base: Any = next((sc for sc in sessions_class if sc.name() == model_name), None)
    if base is None:
        raise ValueError(f"No rembg session class found for model {model_name!r}")

    class Fp16Session(base):
        @classmethod
        def download_models(cls, *args: Any, **kwargs: Any) -> str:
            fp32 = Path(super().download_models(*args, **kwargs))
            return str(ensure_fp16_model(fp32, fp16_path(fp32)))

    return Fp16Session


def _rembg_session_options() -> Any:
    """The `ort.SessionOptions` rembg's `new_session` builds when none is given.

    Mirrors `rembg.session_factory.new_session` (not exposed separately): a
    default `SessionOptions`, with `OMP_NUM_THREADS` (if set) applied to the
    inter/intra-op thread counts still at their default of 0. Keeps the fp16
    path, which bypasses `new_session`, on the same ORT options as the fp32 path.
    """
    import os

    import onnxruntime as ort

    sess_opts = ort.SessionOptions()
    if "OMP_NUM_THREADS" in os.environ:
        threads = int(os.environ["OMP_NUM_THREADS"])
        if sess_opts.inter_op_num_threads == 0:
            sess_opts.inter_op_num_threads = threads
        if sess_opts.intra_op_num_threads == 0:
            sess_opts.intra_op_num_threads = threads
    return sess_opts


def get_background_remover(settings: Settings) -> Any:
    """Return the process-wide `rembg` session for `settings.ml_bg_model`,
    creating it on first call. Subsequent calls (and calls with a different
    `settings.ml_bg_model`) return the same cached session.

    On `cuda` with `settings.ml_bg_fp16` (default) the session loads the fp16
    copy of the model (VIS-REQ-026); cpu/mps keep the original fp32 file."""
    global _bg_session
    with _lock:
        if _bg_session is not None:
            return _bg_session

        from rembg import new_session

        device = resolve_device(settings.ml_device)
        use_fp16 = should_use_fp16(device, fp16_enabled=settings.ml_bg_fp16)
        # The arena cap is only valid for the fp16 lite model (see ml.device).
        capped = use_fp16 and settings.ml_bg_model == LITE_MODEL_NAME
        providers = onnxruntime_providers(
            device, gpu_mem_limit=LITE_FP16_GPU_MEM_LIMIT_BYTES if capped else None
        )
        logger.info(
            "Loading rembg session %r on device=%s (providers=%s)",
            settings.ml_bg_model,
            device,
            providers,
        )
        if use_fp16:
            session = _fp16_session_class(settings.ml_bg_model)(
                settings.ml_bg_model, _rembg_session_options(), providers=providers
            )
        else:
            session = new_session(settings.ml_bg_model, providers=providers)
        check_session_providers(device, session.inner_session.get_providers())
        _bg_session = session
        return _bg_session


def get_embedder(settings: Settings) -> GarmentEmbedder:
    """Return the process-wide SigLIP embedder pinned to
    `settings.ml_embed_revision`, creating it on first call.

    open_clip's `hf-hub:` loader (`create_model_and_transforms("hf-hub:...")`)
    always resolves the repo's current default revision and has no
    `revision` parameter, which can't satisfy VIS-REQ-002 (a pinned,
    reproducible revision). Instead, download the pinned snapshot ourselves
    with `huggingface_hub.snapshot_download(..., revision=...)` and load it
    through open_clip's `local-dir:` schema, which reads the exact same
    `open_clip_config.json` + checkpoint layout that the hf-hub schema does.
    """
    global _embedder
    with _lock:
        if _embedder is not None:
            return _embedder

        import open_clip
        import torch
        from huggingface_hub import snapshot_download
        from PIL import Image

        device = resolve_device(settings.ml_device)
        repo_id = _repo_id(settings.ml_embed_model)

        logger.info("Downloading pinned snapshot %s@%s", repo_id, settings.ml_embed_revision)
        snapshot_dir = snapshot_download(repo_id=repo_id, revision=settings.ml_embed_revision)

        model, _, preprocess = open_clip.create_model_and_transforms(f"local-dir:{snapshot_dir}")
        tokenizer = open_clip.get_tokenizer(f"local-dir:{snapshot_dir}")
        model = model.to(device)
        model.eval()

        # Read the embedding dimension from the loaded model via a dummy
        # forward pass, rather than relying on an attribute that may not
        # exist on every vision-tower implementation (VIS-REQ-002 spirit:
        # never fix this number in code).
        with torch.no_grad():
            dummy = preprocess(Image.new("RGB", (224, 224))).unsqueeze(0).to(device)
            dim = int(model.encode_image(dummy).shape[-1])

        model_id = f"{settings.ml_embed_model}@{settings.ml_embed_revision}"
        logger.info("Loaded embedder %s on device=%s (dim=%d)", model_id, device, dim)

        _embedder = GarmentEmbedder(
            model=model,
            preprocess=preprocess,
            tokenizer=tokenizer,
            device=device,
            dim=dim,
            model_id=model_id,
        )
        return _embedder


def unload_background_remover() -> bool:
    """Drop the BiRefNet session and give its GPU memory back; the next
    `get_background_remover` reloads it. Returns whether one was loaded."""
    global _bg_session
    with _lock:
        was_loaded = _bg_session is not None
        _bg_session = None
    free_gpu_memory()
    return was_loaded


def unload_embedder() -> bool:
    """Drop the SigLIP embedder (and its text cache) and give its GPU memory back; the
    next `get_embedder` reloads it. Returns whether one was loaded. Holders of the old
    embedder (e.g. a zero-shot classifier) keep it alive until they let go."""
    global _embedder
    with _lock:
        was_loaded = _embedder is not None
        _embedder = None
    free_gpu_memory()
    return was_loaded


def reset_registry() -> None:
    """Clear cached singletons. Test-only: production code paths never need
    to reload a model mid-process."""
    global _bg_session, _embedder
    with _lock:
        _bg_session = None
        _embedder = None
