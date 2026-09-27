"""Application settings for pachapp, read from the environment and `.env`.

See docs/specs/01-dev-tooling.md (settings table) and docs/architecture/c4.md
(D14: data must live on WSL2's ext4, never under /mnt/*; D15: CORS).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/pachapp_shared/settings.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Overridable so the test suite never depends on the developer's real
# repo-root `.env` (R3-test-suite-nonhermetic): tests/unit/conftest.py points
# this at a path that is guaranteed not to exist before any app code is
# imported. This is a test-only escape hatch, not a user-facing setting, so
# it is intentionally not part of the `Settings` model and not documented in
# `.env.example`.
_ENV_FILE = Path(os.environ.get("PACHAPP_ENV_FILE", str(_REPO_ROOT / ".env")))

_MOUNT_PREFIX = "/mnt"


def _is_under_wsl_mount(path: Path) -> bool:
    """Return True if `path` resolves under WSL2's 9P-mounted /mnt/* tree."""
    posix = path.expanduser().resolve().as_posix()
    return posix == _MOUNT_PREFIX or posix.startswith(_MOUNT_PREFIX + "/")


def _reject_mnt_path(path: Path, *, env_var: str) -> None:
    """Raise if `path` resolves under WSL2's 9P-mounted /mnt/* tree (D14)."""
    if _is_under_wsl_mount(path):
        raise ValueError(
            f"{env_var} must NOT resolve under /mnt/* (D14): SQLite's WAL mode needs a "
            "reliable shared-memory lock, and /mnt/* is 9P-mounted from Windows. "
            f"Got: {path.expanduser().resolve()}. Use a path under the WSL2 ext4 "
            "filesystem instead, e.g. ~/pachapp-data."
        )


def _reject_blank(value: str, *, env_var: str) -> None:
    """Raise if `value` is empty or whitespace-only (DEV-REQ-011)."""
    if not value.strip():
        raise ValueError(
            f"{env_var} must not be empty or whitespace-only (DEV-REQ-011): secrets and "
            "other required settings must fail fast instead of silently accepting a "
            f"copied-but-unfilled `.env` line, e.g. `{env_var}=`."
        )


class Settings(BaseSettings):
    """Backend settings, sourced from `PACHAPP_*` environment variables / `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="PACHAPP_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("~/pachapp-data"))
    db_path: Path | None = None
    images_root: Path | None = None

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8081"])

    # Required, no versioned default (DEV-REQ-011).
    llm_provider: str
    llm_model_id: str
    llm_api_key: SecretStr

    worker_poll_interval_ms: int = Field(default=500, gt=0)
    db_busy_timeout_ms: int = Field(default=5000, gt=0)
    upload_max_px: int = Field(default=2048, gt=0)
    thumb_px: int = Field(default=400, gt=0)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @model_validator(mode="after")
    def _derive_paths_and_validate(self) -> Settings:
        data_dir = self.data_dir.expanduser()
        self.data_dir = data_dir

        _reject_mnt_path(data_dir, env_var="PACHAPP_DATA_DIR")
        if self.db_path is not None:
            _reject_mnt_path(self.db_path, env_var="PACHAPP_DB_PATH")
        if self.images_root is not None:
            _reject_mnt_path(self.images_root, env_var="PACHAPP_IMAGES_ROOT")

        if self.db_path is None:
            self.db_path = data_dir / "db" / "pachapp.sqlite3"
        if self.images_root is None:
            self.images_root = data_dir / "images"

        _reject_blank(self.llm_provider, env_var="PACHAPP_LLM_PROVIDER")
        _reject_blank(self.llm_api_key.get_secret_value(), env_var="PACHAPP_LLM_API_KEY")

        if not self.llm_model_id.strip():
            raise ValueError(
                "PACHAPP_LLM_MODEL_ID must not be empty or whitespace-only (DEV-REQ-011) "
                "and must be an exact, pinned model identifier/version (D11). "
                f"Got: {self.llm_model_id!r}."
            )
        if "latest" in self.llm_model_id.lower():
            raise ValueError(
                "PACHAPP_LLM_MODEL_ID must be an exact, pinned model identifier/version "
                f"(D11), not an alias containing 'latest'. Got: {self.llm_model_id!r}."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
