"""Unit tests for `ml.cache.configure_model_cache` (08-local-vision.md,
VIS-REQ-008): creates the cache dir and derives `HF_HOME`/`U2NET_HOME` from
it. Uses `tmp_path` only -- no network, no model download (VIS-REQ-029)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ml.cache import configure_model_cache


def test_creates_cache_dir_and_sets_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("U2NET_HOME", raising=False)
    cache_dir = tmp_path / "models"
    assert not cache_dir.exists()

    configure_model_cache(cache_dir)

    assert cache_dir.is_dir()
    assert os.environ["HF_HOME"] == str(cache_dir)
    assert os.environ["U2NET_HOME"] == str(cache_dir)


def test_is_idempotent_on_an_existing_dir(tmp_path: Path) -> None:
    cache_dir = tmp_path / "models"
    cache_dir.mkdir()
    (cache_dir / "already-here.txt").write_text("keep me")

    configure_model_cache(cache_dir)
    configure_model_cache(cache_dir)

    assert (cache_dir / "already-here.txt").read_text() == "keep me"


def test_creates_nested_parent_dirs(tmp_path: Path) -> None:
    cache_dir = tmp_path / "a" / "b" / "models"

    configure_model_cache(cache_dir)

    assert cache_dir.is_dir()


def test_expands_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cache_dir = Path("~/models-cache")

    configure_model_cache(cache_dir)

    expected = str(tmp_path / "models-cache")
    assert os.environ["HF_HOME"] == expected
    assert (tmp_path / "models-cache").is_dir()
