"""Application settings for pachapp, read from the environment and `.env`.

See docs/specs/01-dev-tooling.md (settings table) and docs/architecture/c4.md
(D14: data must live on WSL2's ext4, never under /mnt/*; D15: CORS).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/shared/settings.py -> repo root is three parents up.
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


def _reject_blank(value: str, *, env_var: str, req_id: str = "DEV-REQ-011") -> None:
    """Raise if `value` is empty or whitespace-only (DEV-REQ-011 by default)."""
    if not value.strip():
        raise ValueError(
            f"{env_var} must not be empty or whitespace-only ({req_id}): secrets and "
            "other required settings must fail fast instead of silently accepting a "
            f"copied-but-unfilled `.env` line, e.g. `{env_var}=`."
        )


# Moving refs that would let PACHAPP_ML_EMBED_REVISION drift (VIS-REQ-002).
_MOVING_REVISIONS = frozenset({"latest", "main", "master", "head"})


def _reject_moving_revision(value: str, *, env_var: str) -> None:
    """Raise if `value` is a moving alias/branch ref rather than a pinned
    commit or tag (VIS-REQ-002). A tag or a full SHA is accepted."""
    normalized = value.strip().lower()
    if normalized in _MOVING_REVISIONS or normalized.startswith("refs/heads/"):
        raise ValueError(
            f"{env_var} must be a pinned commit or tag (VIS-REQ-002, analogous to D11), "
            "not a moving ref such as 'latest', 'main', 'master', 'HEAD' or 'refs/heads/*': "
            f"existing embeddings must stay comparable across worker restarts. Got: {value!r}."
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

    # Optional since 08-local-vision.md (VIS-REQ-021/DEV-REQ-011): the vision
    # LLM is now an opt-in fallback, required only when `ml_llm_fallback` is
    # true. No versioned default when required (D11).
    llm_provider: str | None = None
    llm_model_id: str | None = None
    llm_api_key: SecretStr | None = None

    worker_poll_interval_ms: int = Field(default=500, gt=0)
    db_busy_timeout_ms: int = Field(default=5000, gt=0)
    upload_max_px: int = Field(default=2048, gt=0)
    thumb_px: int = Field(default=640, gt=0)

    # --- Local vision (08-local-vision.md) ---
    ml_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    ml_cache_dir: Path | None = None
    ml_bg_model: str = "birefnet-general-lite"
    # fp16 copy of the BG model, used only on cuda (VIS-REQ-026); see ml/bg_fp16.py.
    ml_bg_fp16: bool = True
    ml_embed_model: str = "hf-hub:Marqo/marqo-fashionSigLIP"
    # Required, no versioned default (VIS-REQ-002, analogous to D11).
    ml_embed_revision: str
    # Defaults for the next three come from the 08-local-vision.md settings table.
    ml_margin_threshold: float = Field(default=0.15, gt=0, lt=1)
    ml_knn_k: int = Field(default=7, gt=0)
    ml_knn_min_verified: int = Field(default=30, gt=0)
    ml_llm_fallback: bool = False
    ml_eval_dir: Path | None = None
    # Garment-only cutout in the worker (U5c): after the BiRefNet matte, the FASHN parser
    # removes the person and other garments when a person is in the photo. Turn off
    # (PACHAPP_ML_GARMENT_PARSE=false) to keep today's BiRefNet-only cutout.
    ml_garment_parse: bool = True
    # Human-parsing models used by the garment cutout evaluation (U5). Optional commit
    # pins (VIS-REQ-002 spirit): unset means "latest at download time", and the
    # evaluation report records which revision was loaded. A moving ref is rejected.
    ml_parse_b3_revision: str | None = None
    ml_parse_b2_revision: str | None = None
    # FASHN Human Parser (fashn-ai/fashn-human-parser) and the SCHP checkpoints, hosted in
    # zhengchong/CatVTON (SCHP/*.pth, also sha256-checked): commits verified on the Hub
    # on 2026-10-05.
    ml_parse_fashn_revision: str | None = "1f80c34dbab321c5730dda5c3fea279fd3e97498"
    ml_parse_schp_revision: str | None = "2969fcf85fe62f2036605716f0b56f0b81d01d79"

    # --- Virtual try-on (09-virtual-tryon.md §5.5) ---
    # CatVTON's pipeline is not a diffusers DiffusionPipeline (§12.9), so there is no
    # CPU-offload setting, and the weights live in `ml_cache_dir`, not in a dedicated dir.
    tryon_enabled: bool = False
    # Generation size; the SD VAE/UNet need multiples of 8. 576x768 is the V0 spike default.
    tryon_width: int = 576
    tryon_height: int = 768
    tryon_steps: int = Field(default=20, gt=0)
    tryon_guidance: float = Field(default=2.5, gt=0)
    tryon_seed: int = 42
    # Turing GPUs (RTX 20xx / GTX 16xx) have no usable bf16: never offer it.
    tryon_dtype: Literal["fp16", "fp32"] = "fp16"
    tryon_max_passes: int = Field(default=3, ge=1)
    # 0 = never unload the model from the GPU.
    tryon_idle_unload_seconds: int = Field(default=300, ge=0)
    # Smaller size retried once after a CUDA out-of-memory error.
    tryon_oom_retry_width: int = 384
    tryon_oom_retry_height: int = 512
    tryon_mannequin_woman: str = "m12-woman-crop-shorts"
    tryon_mannequin_man: str = "m13-man-beige-shorts"
    # Renders not accessed for this many days are deleted (row and WebP); 0 = keep them forever.
    tryon_cache_max_age_days: int = Field(default=30, ge=0)
    # Tracked mannequin assets (§5.1); defaults to `<repo root>/assets/tryon`.
    tryon_assets_dir: Path = _REPO_ROOT / "assets" / "tryon"
    # External pinned CatVTON clone (`make tryon-setup`); defaults to `<data dir>/vendor/CatVTON`.
    tryon_catvton_dir: Path | None = None
    # Hub commits verified on 2026-10-08 (V0); moving refs are rejected.
    # booksforcharlie/stable-diffusion-inpainting
    tryon_base_revision: str | None = "d260cf3646fe94c6d5d70820b77512f836d7cce2"
    # zhengchong/CatVTON
    tryon_attn_revision: str | None = "2969fcf85fe62f2036605716f0b56f0b81d01d79"

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator(
        "tryon_width", "tryon_height", "tryon_oom_retry_width", "tryon_oom_retry_height"
    )
    @classmethod
    def _tryon_size_multiple_of_8(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0 or value % 8 != 0:
            raise ValueError(
                f"PACHAPP_{str(info.field_name).upper()} must be a positive multiple of 8 "
                f"(the SD VAE downsamples by 8). Got: {value}."
            )
        return value

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

        # PACHAPP_ML_CACHE_DIR is derived like db_path/images_root and shares
        # their /mnt/* guard (08-local-vision.md, D14).
        if self.ml_cache_dir is not None:
            self.ml_cache_dir = self.ml_cache_dir.expanduser()
            _reject_mnt_path(self.ml_cache_dir, env_var="PACHAPP_ML_CACHE_DIR")
        else:
            self.ml_cache_dir = data_dir / "models"

        if self.ml_eval_dir is not None:
            self.ml_eval_dir = self.ml_eval_dir.expanduser()
        else:
            self.ml_eval_dir = data_dir / "eval" / "garments"

        if self.tryon_catvton_dir is not None:
            self.tryon_catvton_dir = self.tryon_catvton_dir.expanduser()
            _reject_mnt_path(self.tryon_catvton_dir, env_var="PACHAPP_TRYON_CATVTON_DIR")
        else:
            self.tryon_catvton_dir = data_dir / "vendor" / "CatVTON"
        self.tryon_assets_dir = self.tryon_assets_dir.expanduser()

        # No "latest" alias, analogous to D11 (VIS-REQ-002): existing
        # embeddings must stay comparable across worker restarts.
        _reject_blank(
            self.ml_embed_revision, env_var="PACHAPP_ML_EMBED_REVISION", req_id="VIS-REQ-002"
        )
        _reject_moving_revision(self.ml_embed_revision, env_var="PACHAPP_ML_EMBED_REVISION")

        for value, env_var in (
            (self.ml_parse_b3_revision, "PACHAPP_ML_PARSE_B3_REVISION"),
            (self.ml_parse_b2_revision, "PACHAPP_ML_PARSE_B2_REVISION"),
            (self.ml_parse_fashn_revision, "PACHAPP_ML_PARSE_FASHN_REVISION"),
            (self.ml_parse_schp_revision, "PACHAPP_ML_PARSE_SCHP_REVISION"),
            (self.tryon_base_revision, "PACHAPP_TRYON_BASE_REVISION"),
            (self.tryon_attn_revision, "PACHAPP_TRYON_ATTN_REVISION"),
        ):
            if value is not None:
                _reject_moving_revision(value, env_var=env_var)

        # The vision LLM is an opt-in fallback (08-local-vision.md,
        # VIS-REQ-021): its three settings are required, fail-fast, only when
        # PACHAPP_ML_LLM_FALLBACK=true; otherwise they must not be required
        # (same fail-fast pattern as DEV-REQ-011, now conditioned on the flag).
        if self.ml_llm_fallback:
            missing: list[str] = []
            if self.llm_provider is None or not self.llm_provider.strip():
                missing.append("PACHAPP_LLM_PROVIDER")
            if self.llm_model_id is None or not self.llm_model_id.strip():
                missing.append("PACHAPP_LLM_MODEL_ID")
            if self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip():
                missing.append("PACHAPP_LLM_API_KEY")
            if missing:
                raise ValueError(
                    "PACHAPP_ML_LLM_FALLBACK=true requires the following variable(s) to be "
                    f"set (VIS-REQ-021/DEV-REQ-011): {', '.join(missing)}. Set them, or set "
                    "PACHAPP_ML_LLM_FALLBACK=false to disable the vision LLM fallback."
                )
            if "latest" in (self.llm_model_id or "").lower():
                raise ValueError(
                    "PACHAPP_LLM_MODEL_ID must be an exact, pinned model identifier/version "
                    f"(D11), not an alias containing 'latest'. Got: {self.llm_model_id!r}."
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    if not _ENV_FILE.exists():
        raise RuntimeError(
            f"Missing .env file at {str(_ENV_FILE)}. See docs/specs/01-dev-tooling.md "
            "(settings table) and docs/architecture/c4.md (D14/D15)."
        )
    return Settings()
