"""shared.storage: relative layout and atomic writes (ING-REQ-008/009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from shared import storage


def test_relative_layout_matches_convention() -> None:
    assert storage.original_path("abc") == "original/abc.jpg"
    assert storage.cutout_path("abc") == "cutout/abc.png"
    assert storage.thumb_path("abc") == "thumb/abc.webp"


def test_write_atomic_creates_dirs_and_leaves_no_temp_files(tmp_path: Path) -> None:
    target = storage.write_atomic(tmp_path / "images", "original/abc.jpg", b"data")

    assert target == (tmp_path / "images" / "original" / "abc.jpg").resolve()
    assert target.read_bytes() == b"data"
    assert [p.name for p in target.parent.iterdir()] == ["abc.jpg"]


def test_write_atomic_replaces_existing_file(tmp_path: Path) -> None:
    storage.write_atomic(tmp_path, "cutout/a.png", b"old")
    storage.write_atomic(tmp_path, "cutout/a.png", b"new")

    assert (tmp_path / "cutout" / "a.png").read_bytes() == b"new"


def test_write_atomic_failure_keeps_old_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage.write_atomic(tmp_path, "cutout/a.png", b"old")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        storage.write_atomic(tmp_path, "cutout/a.png", b"new")

    assert (tmp_path / "cutout" / "a.png").read_bytes() == b"old"
    assert [p.name for p in (tmp_path / "cutout").iterdir()] == ["a.png"]


def test_delete_file_is_idempotent(tmp_path: Path) -> None:
    storage.write_atomic(tmp_path, "thumb/a.webp", b"x")

    storage.delete_file(tmp_path, "thumb/a.webp")
    storage.delete_file(tmp_path, "thumb/a.webp")

    assert not (tmp_path / "thumb" / "a.webp").exists()


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.jpg", "original/../../x"])
def test_resolve_rejects_absolute_and_escaping_paths(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        storage.resolve_path(tmp_path, bad)
