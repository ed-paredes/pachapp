from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pachapp_shared.settings import Settings


def _base_kwargs(tmp_path: Path) -> dict:
    return {
        "_env_file": None,
        "data_dir": tmp_path / "pachapp-data",
        "llm_provider": "anthropic",
        "llm_model_id": "claude-sonnet-5-20260101",
        "llm_api_key": "test-secret-key",
    }


def test_defaults_derive_db_path_and_images_root(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)

    settings = Settings(**kwargs)

    assert settings.db_path == kwargs["data_dir"] / "db" / "pachapp.sqlite3"
    assert settings.images_root == kwargs["data_dir"] / "images"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.cors_origins == ["http://localhost:8081"]
    assert settings.worker_poll_interval_ms == 500
    assert settings.db_busy_timeout_ms == 5000
    assert settings.upload_max_px == 2048
    assert settings.thumb_px == 400


def test_explicit_db_path_and_images_root_are_not_overridden(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    custom_db = tmp_path / "custom.sqlite3"
    custom_images = tmp_path / "custom-images"
    kwargs["db_path"] = custom_db
    kwargs["images_root"] = custom_images

    settings = Settings(**kwargs)

    assert settings.db_path == custom_db
    assert settings.images_root == custom_images


def test_data_dir_under_mnt_raises_with_d14(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["data_dir"] = Path("/mnt/d/pachapp-data")

    with pytest.raises(ValidationError, match="D14"):
        Settings(**kwargs)


def test_missing_api_key_raises(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    del kwargs["llm_api_key"]

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_missing_llm_provider_raises(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    del kwargs["llm_provider"]

    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize("model_id", ["", "claude-latest", "gpt-LATEST-preview"])
def test_latest_or_empty_model_id_raises(tmp_path: Path, model_id: str) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["llm_model_id"] = model_id

    with pytest.raises(ValidationError, match="D11"):
        Settings(**kwargs)
