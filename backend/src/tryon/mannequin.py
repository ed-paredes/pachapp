"""Mannequin assets for the virtual try-on (09-virtual-tryon.md §5.1).

A mannequin is a tracked folder `<assets dir>/mannequins/<id>/` with the person photo, the
three precomputed CatVTON masks (`make tryon-masks`) and a `meta.json` with source and licence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

MASK_TYPES = ("upper", "lower", "overall")
# Becomes a folder name under the assets dir: no separators, dots or leading dash.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class MannequinError(Exception):
    """The mannequin id or its asset folder is invalid."""


@dataclass(frozen=True)
class Mannequin:
    id: str
    person: Image.Image  # RGB
    masks: dict[str, Image.Image]  # mask type -> "L" image, same size as `person`
    meta: dict[str, Any]

    @property
    def gender(self) -> str | None:
        """`meta.json` `gender`; None when absent or not a string."""
        value = self.meta.get("gender")
        return value if isinstance(value, str) else None


def validate_mannequin_id(mannequin_id: str) -> str:
    if not _ID_PATTERN.fullmatch(mannequin_id):
        raise MannequinError(f"invalid mannequin id {mannequin_id!r}")
    return mannequin_id


def _open(path: Path, mode: str) -> Image.Image:
    if not path.is_file():
        raise MannequinError(f"mannequin file missing: {path}")
    try:
        with Image.open(path) as image:
            return image.convert(mode)
    except (OSError, UnidentifiedImageError) as exc:
        raise MannequinError(f"mannequin file unreadable: {path}") from exc


def load_mannequin(assets_dir: Path, mannequin_id: str) -> Mannequin:
    """Load `<assets_dir>/mannequins/<mannequin_id>/`; raises `MannequinError` if unusable."""
    validate_mannequin_id(mannequin_id)
    folder = assets_dir / "mannequins" / mannequin_id
    if not folder.is_dir():
        raise MannequinError(f"mannequin folder not found: {folder}")

    person = _open(folder / "person.png", "RGB")
    masks = {kind: _open(folder / f"mask_{kind}.png", "L") for kind in MASK_TYPES}
    for kind, mask in masks.items():
        if mask.size != person.size:
            raise MannequinError(
                f"mask_{kind}.png is {mask.size[0]}x{mask.size[1]}, "
                f"person.png is {person.size[0]}x{person.size[1]}: {folder}"
            )

    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        raise MannequinError(f"mannequin file missing: {meta_path}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MannequinError(f"mannequin meta.json unreadable: {meta_path}") from exc
    if not isinstance(meta, dict):
        raise MannequinError(f"mannequin meta.json is not an object: {meta_path}")
    return Mannequin(id=mannequin_id, person=person, masks=masks, meta=meta)
