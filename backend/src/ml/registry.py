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
from dataclasses import dataclass
from typing import Any

from ml.device import check_session_providers, onnxruntime_providers, resolve_device
from shared.settings import Settings

logger = logging.getLogger(__name__)

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


def _repo_id(embed_model: str) -> str:
    """Strip open_clip's `hf-hub:` schema prefix, if present, to get a bare
    Hugging Face repo id for `huggingface_hub.snapshot_download`."""
    if embed_model.startswith(_HF_HUB_PREFIX):
        return embed_model[len(_HF_HUB_PREFIX) :]
    return embed_model


def get_background_remover(settings: Settings) -> Any:
    """Return the process-wide `rembg` session for `settings.ml_bg_model`,
    creating it on first call. Subsequent calls (and calls with a different
    `settings.ml_bg_model`) return the same cached session."""
    global _bg_session
    with _lock:
        if _bg_session is not None:
            return _bg_session

        from rembg import new_session

        device = resolve_device(settings.ml_device)
        providers = onnxruntime_providers(device)
        logger.info(
            "Loading rembg session %r on device=%s (providers=%s)",
            settings.ml_bg_model,
            device,
            providers,
        )
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


def reset_registry() -> None:
    """Clear cached singletons. Test-only: production code paths never need
    to reload a model mid-process."""
    global _bg_session, _embedder
    with _lock:
        _bg_session = None
        _embedder = None
