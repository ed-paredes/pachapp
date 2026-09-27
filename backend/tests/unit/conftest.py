"""Shared fixtures for backend unit tests."""

from __future__ import annotations

import os

import pytest

_PACHAPP_PREFIX = "PACHAPP_"

# `pachapp_api.main` builds its module-level `app` eagerly at import time (by
# design: it fails fast on bad settings). Set harmless dummy LLM settings
# before any test module is collected/imported, so that import succeeds
# without depending on a real `.env`. Individual tests still exercise
# `Settings`/`create_app` with their own explicit values.
os.environ.setdefault("PACHAPP_LLM_PROVIDER", "test-provider")
os.environ.setdefault("PACHAPP_LLM_MODEL_ID", "test-model-1")
os.environ.setdefault("PACHAPP_LLM_API_KEY", "test-collection-time-key")


@pytest.fixture(autouse=True)
def _clean_pachapp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ambient PACHAPP_* env vars never leak into a test."""
    for key in list(os.environ):
        if key.startswith(_PACHAPP_PREFIX):
            monkeypatch.delenv(key, raising=False)
