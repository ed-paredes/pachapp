"""Model cache configuration (08-local-vision.md, VIS-REQ-008).

`HF_HOME` (Hugging Face Hub cache, used by `open_clip`/`huggingface_hub`) and
`U2NET_HOME` (`rembg`'s model directory) are both derived from
`PACHAPP_ML_CACHE_DIR` in code, never set as loose variables in `.env` /
`.env.example` — that way they stay subject to the same D14 (`/mnt/*`) guard
as `PACHAPP_DATA_DIR` (enforced on `ml_cache_dir` itself, in `shared.settings`).

`configure_model_cache` MUST run before anything imports/uses `open_clip` or
`rembg` (worker.main does this first, before touching any other `ml` code).
"""

from __future__ import annotations

import os
from pathlib import Path


def configure_model_cache(cache_dir: Path) -> None:
    """Create `cache_dir` and point `HF_HOME`/`U2NET_HOME` at it."""
    cache_dir = cache_dir.expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_dir_str = str(cache_dir)
    os.environ["HF_HOME"] = cache_dir_str
    os.environ["U2NET_HOME"] = cache_dir_str
