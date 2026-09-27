"""Application settings for pachapp, read from the environment and `.env`.

See docs/specs/01-dev-tooling.md (settings table) and docs/architecture/c4.md
(D14: data must live on WSL2's ext4, never under /mnt/*; D15: CORS).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/pachapp_shared/settings.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

_MOUNT_PREFIX = "/mnt"


def _is_under_wsl_mount(path: Path) -> bool:
    """Return True if `path` resolves under WSL2's 9P-mounted /mnt/* tree."""
    posix = path.expanduser().resolve().as_posix()
    return posix == _MOUNT_PREFIX or posix.startswith(_MOUNT_PREFIX + "/")


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
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8081"])

    # Required, no versioned default (DEV-REQ-011).
    llm_provider: str
    llm_model_id: str
    llm_api_key: SecretStr

    worker_poll_interval_ms: int = 500
    db_busy_timeout_ms: int = 5000
    upload_max_px: int = 2048
    thumb_px: int = 400

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @model_validator(mode="after")
    def _derive_paths_and_validate(self) -> Settings:
        data_dir = self.data_dir.expanduser()
        self.data_dir = data_dir

        if _is_under_wsl_mount(data_dir):
            raise ValueError(
                "PACHAPP_DATA_DIR must NOT resolve under /mnt/* (D14): SQLite's WAL mode "
                "needs a reliable shared-memory lock, and /mnt/* is 9P-mounted from Windows. "
                f"Got: {data_dir.resolve()}. Use a path under the WSL2 ext4 "
                "filesystem instead, e.g. ~/pachapp-data."
            )

        if self.db_path is None:
            self.db_path = data_dir / "db" / "pachapp.sqlite3"
        if self.images_root is None:
            self.images_root = data_dir / "images"

        if not self.llm_model_id or "latest" in self.llm_model_id.lower():
            raise ValueError(
                "PACHAPP_LLM_MODEL_ID must be an exact, pinned model identifier/version "
                "(D11), not empty and not an alias containing 'latest'. "
                f"Got: {self.llm_model_id!r}."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
