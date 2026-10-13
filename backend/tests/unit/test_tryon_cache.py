"""Render cache key (09-virtual-tryon.md §6.5) and the torch-free guarantee."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from shared.imaging import encode_webp
from shared.storage import tryon_path
from tryon.cache import (
    ATTN_VERSION,
    cache_key,
    hash_cutout,
    mannequin_version,
    model_version,
)
from tryon.mannequin import MannequinError

_BASE: dict[str, Any] = {
    "mannequin_id": "m12",
    "mannequin_digest": "mv1",
    "garments": [("g1", "h1", "upper"), ("g2", "h2", "lower")],
    "width": 576,
    "height": 768,
    "steps": 20,
    "guidance": 2.5,
    "seed": 42,
    "model_tag": "model1",
    "postprocess": "none",
}


def _key(**changes: Any) -> str:
    return cache_key(**{**_BASE, **changes})


def test_key_is_stable_hex_sha256() -> None:
    assert _key() == _key()
    assert len(_key()) == 64
    int(_key(), 16)


def test_key_accepts_lists_and_tuples_alike() -> None:
    assert _key(garments=[["g1", "h1", "upper"], ["g2", "h2", "lower"]]) == _key()


def test_key_depends_on_pass_order() -> None:
    assert _key(garments=[("g2", "h2", "lower"), ("g1", "h1", "upper")]) != _key()


@pytest.mark.parametrize(
    "changes",
    [
        {"mannequin_id": "other"},
        {"mannequin_digest": "mv2"},
        {"garments": [("g1", "h1", "upper")]},
        {"garments": [("g1", "h1", "overall"), ("g2", "h2", "lower")]},
        {"garments": [("g1", "h1", "upper"), ("g2", "changed", "lower")]},
        {"width": 384},
        {"height": 512},
        {"steps": 30},
        {"guidance": 3.0},
        {"seed": 1},
        {"model_tag": "model2"},
        {"postprocess": "dummy-1"},
    ],
)
def test_key_changes_with_every_input(changes: dict[str, Any]) -> None:
    assert _key(**changes) != _key()


def test_hash_cutout_changes_when_the_file_changes(tmp_path: Path) -> None:
    (tmp_path / "cutout").mkdir()
    path = tmp_path / "cutout" / "g1.png"
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(path)
    first = hash_cutout(tmp_path, "cutout/g1.png")
    assert first == hash_cutout(tmp_path, "cutout/g1.png")

    Image.new("RGBA", (4, 4), (0, 255, 0, 255)).save(path)
    second = hash_cutout(tmp_path, "cutout/g1.png")
    assert second != first
    assert _key(garments=[("g1", first, "upper")]) != _key(garments=[("g1", second, "upper")])


def test_hash_cutout_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        hash_cutout(tmp_path, "../escape.png")


def _write_mannequin(assets: Path, meta: dict[str, Any] | None = None) -> None:
    folder = assets / "mannequins" / "m1"
    folder.mkdir(parents=True)
    for name in ("person.png", "mask_upper.png", "mask_lower.png", "mask_overall.png"):
        Image.new("L", (8, 8), 0).save(folder / name)
    (folder / "meta.json").write_text(json.dumps(meta or {"id": "m1"}), encoding="utf-8")


def test_mannequin_version_tracks_assets(tmp_path: Path) -> None:
    _write_mannequin(tmp_path)
    first = mannequin_version(tmp_path, "m1")
    assert first == mannequin_version(tmp_path, "m1")

    Image.new("L", (8, 8), 255).save(tmp_path / "mannequins" / "m1" / "mask_upper.png")
    assert mannequin_version(tmp_path, "m1") != first


def test_mannequin_version_tracks_meta(tmp_path: Path) -> None:
    _write_mannequin(tmp_path)
    first = mannequin_version(tmp_path, "m1")
    (tmp_path / "mannequins" / "m1" / "meta.json").write_text('{"id": "m1", "v": 2}')
    assert mannequin_version(tmp_path, "m1") != first


def test_mannequin_version_missing_file_or_bad_id(tmp_path: Path) -> None:
    _write_mannequin(tmp_path)
    (tmp_path / "mannequins" / "m1" / "meta.json").unlink()
    with pytest.raises(MannequinError):
        mannequin_version(tmp_path, "m1")
    with pytest.raises(MannequinError):
        mannequin_version(tmp_path, "../x")


def test_model_version_includes_revisions_and_attention_flavour() -> None:
    value = model_version("base-rev", "attn-rev")
    assert "base-rev" in value
    assert "attn-rev" in value
    assert ATTN_VERSION in value
    assert model_version("other", "attn-rev") != value
    assert model_version("base-rev", None) != value


def test_tryon_path() -> None:
    assert tryon_path("abc") == "tryon/abc.webp"


def test_encode_webp_full_size_round_trip(tmp_path: Path) -> None:
    import io

    data = encode_webp(Image.new("RGB", (576, 768), (10, 120, 200)))
    with Image.open(io.BytesIO(data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (576, 768)
    # Palette images are converted rather than rejected.
    assert encode_webp(Image.new("P", (8, 8)))[:4] == b"RIFF"


def test_mapping_and_cache_stay_torch_free() -> None:
    probe = (
        "import sys\n"
        "import tryon.mapping, tryon.cache\n"
        "bad = [m for m in ('torch', 'ml', 'diffusers') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
