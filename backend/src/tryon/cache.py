"""Render cache key (09-virtual-tryon.md §6.5).

Torch-free: the API computes the key to answer 200 (cached) without loading the engine.
`ATTN_VERSION` lives here, not in `tryon.engine` (which imports the GPU stack), so that the key
and the engine share one constant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from shared.storage import resolve_path
from tryon.mannequin import MASK_TYPES, MannequinError, validate_mannequin_id

# CatVTON attention checkpoint flavour the engine loads.
ATTN_VERSION = "mix"

_CHUNK = 1 << 20


def hash_file(path: Path) -> str:
    """sha256 hex digest of the file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def hash_cutout(images_root: Path, relative: str) -> str:
    """sha256 of a garment cutout file; `relative` is the stored path (`img_cutout`)."""
    return hash_file(resolve_path(images_root, relative))


def mannequin_version(assets_dir: Path, mannequin_id: str) -> str:
    """Digest over everything that shapes a render of the mannequin: person photo, the three
    masks and `meta.json`, so replacing any asset invalidates the cache."""
    validate_mannequin_id(mannequin_id)
    folder = assets_dir / "mannequins" / mannequin_id
    digest = hashlib.sha256()
    for name in ("person.png", *(f"mask_{kind}.png" for kind in MASK_TYPES), "meta.json"):
        path = folder / name
        if not path.is_file():
            raise MannequinError(f"mannequin file missing: {path}")
        digest.update(name.encode())
        digest.update(hash_file(path).encode())
    return digest.hexdigest()


def model_version(base_revision: str | None, attn_revision: str | None) -> str:
    """The pinned base and attention revisions plus the attention flavour."""
    return f"base={base_revision or ''};attn={attn_revision or ''};flavour={ATTN_VERSION}"


def cache_key(
    *,
    mannequin_id: str,
    mannequin_version: str,
    garments: Sequence[tuple[str, str]],
    width: int,
    height: int,
    steps: int,
    guidance: float,
    seed: int,
    model_version: str,
) -> str:
    """sha256 over a canonical serialisation of the inputs that determine the image.

    `garments` is `(garment_id, cutout_sha256)` in pass order; skipped and unsupported garments
    are not part of it. Order matters (each pass dresses the previous output).
    """
    payload = {
        "mannequin_id": mannequin_id,
        "mannequin_version": mannequin_version,
        "garments": [[garment_id, cutout_hash] for garment_id, cutout_hash in garments],
        "width": width,
        "height": height,
        "steps": steps,
        "guidance": guidance,
        "seed": seed,
        "model_version": model_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
