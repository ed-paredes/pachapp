"""Shared fixtures for backend unit tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_PACHAPP_PREFIX = "PACHAPP_"

# `pachapp_api.main` builds its module-level `app` eagerly at import time (by
# design: it fails fast on bad settings), and `pachapp_shared.settings`
# resolves its `.env` file path at *module import* time. Both must be set
# before any app code is imported/collected, so that the test suite never
# reads the developer's real repo-root `.env` (R3-test-suite-nonhermetic) and
# never depends on it existing.
#
# Point PACHAPP_ENV_FILE at a path that is guaranteed not to exist: `Settings`
# silently skips a missing `env_file` (pydantic-settings default behavior),
# so this is equivalent to disabling dotenv loading entirely for tests.
os.environ.setdefault(
    "PACHAPP_ENV_FILE", str(Path(tempfile.gettempdir()) / "pachapp-tests-no-such-env-file")
)
os.environ.setdefault("PACHAPP_LLM_PROVIDER", "test-provider")
os.environ.setdefault("PACHAPP_LLM_MODEL_ID", "test-model-1")
os.environ.setdefault("PACHAPP_LLM_API_KEY", "test-collection-time-key")


@pytest.fixture(autouse=True)
def _clean_pachapp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ambient PACHAPP_* env vars and the settings cache never leak
    between tests."""
    from pachapp_shared.settings import get_settings

    get_settings.cache_clear()
    for key in list(os.environ):
        if key.startswith(_PACHAPP_PREFIX):
            monkeypatch.delenv(key, raising=False)
    yield
    get_settings.cache_clear()
