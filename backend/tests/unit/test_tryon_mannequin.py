"""Mannequin asset loader (09-virtual-tryon.md §5.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tryon.mannequin import MASK_TYPES, MannequinError, load_mannequin

REPO_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "tryon"


def make_mannequin(root: Path, mannequin_id: str = "m1", size: tuple[int, int] = (24, 32)) -> Path:
    folder = root / "mannequins" / mannequin_id
    folder.mkdir(parents=True)
    Image.new("RGB", size, (200, 150, 120)).save(folder / "person.png")
    for kind in MASK_TYPES:
        Image.new("L", size, 255).save(folder / f"mask_{kind}.png")
    (folder / "meta.json").write_text(json.dumps({"id": mannequin_id, "licence": "test"}))
    return folder


def test_loads_person_masks_and_meta(tmp_path: Path) -> None:
    make_mannequin(tmp_path)
    mannequin = load_mannequin(tmp_path, "m1")
    assert mannequin.id == "m1"
    assert mannequin.person.mode == "RGB" and mannequin.person.size == (24, 32)
    assert set(mannequin.masks) == set(MASK_TYPES)
    assert all(m.mode == "L" for m in mannequin.masks.values())
    assert mannequin.meta["licence"] == "test"


def test_tracked_default_mannequin_loads() -> None:
    mannequin = load_mannequin(REPO_ASSETS, "m12-woman-crop-shorts")
    assert mannequin.person.size == (768, 1024)


@pytest.mark.parametrize("bad", ["", "..", "../x", "a/b", "a\\b", ".hidden", "-x", "a b", "x" * 65])
def test_rejects_invalid_ids_before_touching_disk(tmp_path: Path, bad: str) -> None:
    with pytest.raises(MannequinError, match="invalid mannequin id"):
        load_mannequin(tmp_path, bad)


def test_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(MannequinError, match="folder not found"):
        load_mannequin(tmp_path, "nope")


@pytest.mark.parametrize(
    "missing", ["person.png", "mask_upper.png", "mask_lower.png", "mask_overall.png", "meta.json"]
)
def test_missing_file(tmp_path: Path, missing: str) -> None:
    (make_mannequin(tmp_path) / missing).unlink()
    with pytest.raises(MannequinError, match=missing):
        load_mannequin(tmp_path, "m1")


def test_unreadable_image(tmp_path: Path) -> None:
    (make_mannequin(tmp_path) / "person.png").write_bytes(b"not a png")
    with pytest.raises(MannequinError, match="unreadable"):
        load_mannequin(tmp_path, "m1")


def test_mask_size_must_match_person(tmp_path: Path) -> None:
    Image.new("L", (10, 10)).save(make_mannequin(tmp_path) / "mask_lower.png")
    with pytest.raises(MannequinError, match="mask_lower.png is 10x10"):
        load_mannequin(tmp_path, "m1")


@pytest.mark.parametrize("content", ["{broken", "[1, 2]"])
def test_bad_meta(tmp_path: Path, content: str) -> None:
    (make_mannequin(tmp_path) / "meta.json").write_text(content)
    with pytest.raises(MannequinError, match="meta.json"):
        load_mannequin(tmp_path, "m1")
