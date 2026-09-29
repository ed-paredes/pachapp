from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared import settings as settings_module
from shared.settings import Settings, get_settings


def _base_kwargs(tmp_path: Path) -> dict:
    return {
        "_env_file": None,
        "data_dir": tmp_path / "pachapp-data",
        "ml_embed_revision": "test-revision",
    }


def _base_kwargs_with_llm(tmp_path: Path) -> dict:
    """`_base_kwargs`, plus the LLM fallback vars, for tests that exercise
    `ml_llm_fallback=True` (VIS-REQ-021)."""
    kwargs = _base_kwargs(tmp_path)
    kwargs.update(
        llm_provider="anthropic",
        llm_model_id="claude-sonnet-5-20260101",
        llm_api_key="test-secret-key",
    )
    return kwargs


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
    assert settings.llm_provider is None
    assert settings.llm_model_id is None
    assert settings.llm_api_key is None
    assert settings.ml_device == "auto"
    assert settings.ml_cache_dir == kwargs["data_dir"] / "models"
    assert settings.ml_bg_model == "birefnet-general"
    assert settings.ml_embed_model == "hf-hub:Marqo/marqo-fashionSigLIP"
    assert settings.ml_embed_revision == "test-revision"
    assert settings.ml_margin_threshold == 0.15
    assert settings.ml_knn_k == 7
    assert settings.ml_knn_min_verified == 30
    assert settings.ml_llm_fallback is False
    assert settings.ml_eval_dir == kwargs["data_dir"] / "eval" / "garments"


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


def test_llm_vars_not_required_when_fallback_disabled(tmp_path: Path) -> None:
    """VIS-REQ-021: with `ml_llm_fallback=False` (the default), none of the
    LLM vars are required -- unlike before 08-local-vision.md, where the LLM
    was the mandatory primary classifier."""
    settings = Settings(**_base_kwargs(tmp_path))

    assert settings.ml_llm_fallback is False
    assert settings.llm_provider is None


def test_missing_api_key_raises_when_fallback_enabled(tmp_path: Path) -> None:
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    del kwargs["llm_api_key"]

    with pytest.raises(ValidationError, match="PACHAPP_LLM_API_KEY"):
        Settings(**kwargs)


def test_missing_llm_provider_raises_when_fallback_enabled(tmp_path: Path) -> None:
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    del kwargs["llm_provider"]

    with pytest.raises(ValidationError, match="PACHAPP_LLM_PROVIDER"):
        Settings(**kwargs)


@pytest.mark.parametrize("model_id", ["", "claude-latest", "gpt-LATEST-preview"])
def test_latest_or_empty_model_id_raises_when_fallback_enabled(
    tmp_path: Path, model_id: str
) -> None:
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    kwargs["llm_model_id"] = model_id

    with pytest.raises(ValidationError, match="D11|DEV-REQ-011"):
        Settings(**kwargs)


@pytest.mark.parametrize("blank_provider", ["", "   ", "\t\n"])
def test_blank_llm_provider_raises_when_fallback_enabled(
    tmp_path: Path, blank_provider: str
) -> None:
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    kwargs["llm_provider"] = blank_provider

    with pytest.raises(ValidationError, match="VIS-REQ-021") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_LLM_PROVIDER" in str(exc_info.value)


@pytest.mark.parametrize("blank_key", ["", "   ", "\t\n"])
def test_blank_llm_api_key_raises_when_fallback_enabled(tmp_path: Path, blank_key: str) -> None:
    """Reproduces a copied-but-unfilled `.env.example` line: `PACHAPP_LLM_API_KEY=`."""
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    kwargs["llm_api_key"] = blank_key

    with pytest.raises(ValidationError, match="VIS-REQ-021") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_LLM_API_KEY" in str(exc_info.value)


@pytest.mark.parametrize("blank_model_id", ["   ", "\t\n"])
def test_whitespace_only_model_id_raises_when_fallback_enabled(
    tmp_path: Path, blank_model_id: str
) -> None:
    kwargs = _base_kwargs_with_llm(tmp_path)
    kwargs["ml_llm_fallback"] = True
    kwargs["llm_model_id"] = blank_model_id

    with pytest.raises(ValidationError, match="VIS-REQ-021") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_LLM_MODEL_ID" in str(exc_info.value)


@pytest.mark.parametrize("blank_revision", ["", "   ", "\t\n"])
def test_blank_ml_embed_revision_raises(tmp_path: Path, blank_revision: str) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_embed_revision"] = blank_revision

    with pytest.raises(ValidationError, match="DEV-REQ-011") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_ML_EMBED_REVISION" in str(exc_info.value)


def test_ml_cache_dir_under_mnt_raises_with_d14(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_cache_dir"] = Path("/mnt/d/pachapp-data/models")

    with pytest.raises(ValidationError, match="D14") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_ML_CACHE_DIR" in str(exc_info.value)


def test_explicit_ml_cache_dir_and_ml_eval_dir_are_not_overridden(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    custom_cache = tmp_path / "custom-models"
    custom_eval = tmp_path / "custom-eval"
    kwargs["ml_cache_dir"] = custom_cache
    kwargs["ml_eval_dir"] = custom_eval

    settings = Settings(**kwargs)

    assert settings.ml_cache_dir == custom_cache
    assert settings.ml_eval_dir == custom_eval


@pytest.mark.parametrize("margin", [0.0, 1.0, -0.1, 1.1])
def test_ml_margin_threshold_outside_open_unit_interval_raises(
    tmp_path: Path, margin: float
) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_margin_threshold"] = margin

    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize("value", [0, -1])
def test_ml_knn_k_non_positive_raises(tmp_path: Path, value: int) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_knn_k"] = value

    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize("value", [0, -1])
def test_ml_knn_min_verified_non_positive_raises(tmp_path: Path, value: int) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_knn_min_verified"] = value

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_ml_device_rejects_unknown_literal(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["ml_device"] = "tpu"

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_explicit_db_path_under_mnt_raises_with_d14(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["db_path"] = Path("/mnt/d/pachapp-data/db/pachapp.sqlite3")

    with pytest.raises(ValidationError, match="D14") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_DB_PATH" in str(exc_info.value)


def test_explicit_images_root_under_mnt_raises_with_d14(tmp_path: Path) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["images_root"] = Path("/mnt/d/pachapp-data/images")

    with pytest.raises(ValidationError, match="D14") as exc_info:
        Settings(**kwargs)
    assert "PACHAPP_IMAGES_ROOT" in str(exc_info.value)


@pytest.mark.parametrize("interval_ms", [0, -1])
def test_non_positive_worker_poll_interval_raises(tmp_path: Path, interval_ms: int) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["worker_poll_interval_ms"] = interval_ms

    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize("port", [0, -1, 65536, 100000])
def test_api_port_outside_valid_range_raises(tmp_path: Path, port: int) -> None:
    kwargs = _base_kwargs(tmp_path)
    kwargs["api_port"] = port

    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_repo_root_dotenv_never_read_by_default_settings() -> None:
    """Hermeticity proof (R3-test-suite-nonhermetic): tests/unit/conftest.py
    points `PACHAPP_ENV_FILE` at the empty `os.devnull` before any app code is
    imported, so the developer's repo-root `.env` is never consulted by
    `Settings`. Checked without writing into the repository.
    """
    repo_root_env = Path(__file__).resolve().parents[3] / ".env"
    env_file = Path(str(Settings.model_config["env_file"]))

    assert env_file != repo_root_env
    assert env_file == Path(os.devnull)


def test_env_file_is_read_when_configured(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PACHAPP_DATA_DIR=/mnt/d/x\n")

    with pytest.raises(ValidationError, match="D14"):
        Settings(
            _env_file=env_file,
            llm_provider="anthropic",
            llm_model_id="claude-sonnet-5-20260101",
            llm_api_key="test-secret-key",
            ml_embed_revision="test-revision",
        )


def test_get_settings_raises_when_env_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`get_settings()` fails fast (R3-missing-env-file-guard-untested) when
    the file `_ENV_FILE` points at doesn't exist, naming the path.

    `_ENV_FILE` is resolved once at module-import time from
    `PACHAPP_ENV_FILE`, so it's monkeypatched directly on the module rather
    than via the env var (which would have no effect after import).
    """
    missing_env_file = tmp_path / "does-not-exist" / ".env"
    monkeypatch.setattr(settings_module, "_ENV_FILE", missing_env_file)

    with pytest.raises(RuntimeError, match=re.escape(str(missing_env_file))):
        get_settings()


def test_get_settings_returns_settings_when_env_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing file at `_ENV_FILE` satisfies the guard and `get_settings()`
    returns a `Settings` instance. `Settings`' own `env_file` (in
    `model_config`) is frozen at test-collection time to `os.devnull` (see
    conftest.py), so the required fields come from the process environment
    here, not from this file's contents -- dotenv loading itself is covered
    separately by `test_env_file_is_read_when_configured`.
    """
    existing_env_file = tmp_path / ".env"
    existing_env_file.write_text("")
    monkeypatch.setattr(settings_module, "_ENV_FILE", existing_env_file)
    monkeypatch.setenv("PACHAPP_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("PACHAPP_LLM_MODEL_ID", "claude-sonnet-5-20260101")
    monkeypatch.setenv("PACHAPP_LLM_API_KEY", "test-secret-key")
    monkeypatch.setenv("PACHAPP_ML_EMBED_REVISION", "test-revision")

    result = get_settings()

    assert isinstance(result, Settings)
    assert result.llm_provider == "anthropic"
