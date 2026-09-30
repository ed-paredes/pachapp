"""Image file layout under `settings.images_root` (docs/specs/03-garment-ingestion.md).

ING-REQ-008: paths stored in the DB are always relative to the images root,
never absolute. ING-REQ-009: `original/{id}.jpg`, `cutout/{id}.png`,
`thumb/{id}.webp`.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path


def original_path(garment_id: str) -> str:
    return f"original/{garment_id}.jpg"


def cutout_path(garment_id: str) -> str:
    return f"cutout/{garment_id}.png"


def thumb_path(garment_id: str) -> str:
    return f"thumb/{garment_id}.webp"


def resolve_path(images_root: Path, relative: str) -> Path:
    """Resolve a stored relative path against `images_root`.

    Rejects absolute paths and anything escaping the root (ING-REQ-008).
    """
    if Path(relative).is_absolute():
        raise ValueError(f"image path must be relative, got {relative!r}")
    root = images_root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"image path escapes the images root: {relative!r}")
    return target


def write_atomic(images_root: Path, relative: str, data: bytes) -> Path:
    """Write `data` at `relative` via a temp file and `os.replace`, creating dirs.

    Readers never see a partial file; a failed write leaves no temp file behind.
    """
    target = resolve_path(images_root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    return target


def delete_file(images_root: Path, relative: str) -> None:
    """Delete the file at `relative`; a missing file is not an error."""
    with contextlib.suppress(FileNotFoundError):
        resolve_path(images_root, relative).unlink()
