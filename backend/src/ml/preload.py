"""CLI: download/validate the vision models into `PACHAPP_ML_CACHE_DIR`.

Usage: `python -m ml.preload` (wired up as `make ml-preload`).
Analogous to `SPEC-ML.md`'s `preload_models.py`, adapted from a Docker build
step to a local Makefile target (08-local-vision.md, VIS-REQ-009/VIS-REQ-027).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ml.bg_fp16 import model_precision
from ml.cache import configure_model_cache
from shared.settings import get_settings


def _time_warm_inference(session: Any) -> float:
    """Milliseconds for one background removal on a synthetic 1024x1024 image,
    after an untimed first call (CUDA context, kernels, arena). Reported so a
    VRAM-spilling setup shows up at preload rather than in production."""
    from PIL import Image
    from rembg import remove

    image = Image.effect_noise((1024, 1024), 64).convert("RGB")
    remove(image, session=session)
    start = time.monotonic()
    remove(image, session=session)
    return (time.monotonic() - start) * 1000


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    start = time.monotonic()

    settings = get_settings()
    # Settings._derive_paths_and_validate always fills this in; the field
    # type stays `Path | None` because it's an optional override on input.
    assert settings.ml_cache_dir is not None
    # Must run before anything below imports/uses open_clip or rembg
    # (VIS-REQ-008).
    configure_model_cache(settings.ml_cache_dir)

    from ml.device import resolve_device
    from ml.registry import get_background_remover, get_embedder

    device = resolve_device(settings.ml_device)
    bg_session = get_background_remover(settings)
    bg_file = Path(str(getattr(bg_session.inner_session, "_model_path", "unknown")))
    warm_ms = _time_warm_inference(bg_session)
    embedder = get_embedder(settings)

    elapsed = time.monotonic() - start
    print("Vision models ready:")
    print(f"  device:        {device}")
    print(f"  bg model:      {settings.ml_bg_model}")
    print(f"  bg file:       {bg_file} ({model_precision(bg_file)})")
    print(f"  bg warm:       {warm_ms:.0f} ms/image (synthetic 1024x1024)")
    print(f"  embed model:   {embedder.model_id}")
    print(f"  embedding dim: {embedder.dim}")
    print(f"  cache dir:     {settings.ml_cache_dir}")
    print(f"  elapsed:       {elapsed:.1f}s")


if __name__ == "__main__":
    main()
