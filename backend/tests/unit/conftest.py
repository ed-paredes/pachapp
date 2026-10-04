"""Shared fixtures for backend unit tests."""

from __future__ import annotations

import os

import pytest

_PACHAPP_PREFIX = "PACHAPP_"

# `api.main` builds its module-level `app` eagerly at import time (by
# design: it fails fast on bad settings), and `shared.settings`
# resolves its `.env` file path at *module import* time. Both must be set
# before any app code is imported/collected, so that the test suite never
# reads the developer's real repo-root `.env` (R3-test-suite-nonhermetic) and
# never depends on it existing.
#
# Point PACHAPP_ENV_FILE at the empty `os.devnull`: it exists (get_settings()
# requires the env file to exist) but defines nothing, so this is equivalent
# to disabling dotenv loading entirely for tests.
# Values are forced, not defaulted: the Makefile exports PACHAPP_ENV_FILE, and
# a developer shell may export other PACHAPP_* settings.
for _key in [key for key in os.environ if key.startswith(_PACHAPP_PREFIX)]:
    del os.environ[_key]
os.environ["PACHAPP_ENV_FILE"] = os.devnull
# The vision LLM fallback is opt-in and off by default (08-local-vision.md,
# VIS-REQ-021), so these are no longer required for Settings() to succeed;
# kept for modules (e.g. api.main) that still build a full app at collection
# time and may want to exercise the fallback path.
os.environ["PACHAPP_LLM_PROVIDER"] = "test-provider"
os.environ["PACHAPP_LLM_MODEL_ID"] = "test-model-1"
os.environ["PACHAPP_LLM_API_KEY"] = "test-collection-time-key"
# Required, no default (VIS-REQ-002): must be set before any app code that
# builds Settings() is imported/collected.
os.environ["PACHAPP_ML_EMBED_REVISION"] = "test-collection-time-revision"


@pytest.fixture(autouse=True)
def _clean_pachapp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ambient PACHAPP_* env vars and the settings cache never leak
    between tests."""
    from shared.settings import get_settings

    get_settings.cache_clear()
    for key in list(os.environ):
        if key.startswith(_PACHAPP_PREFIX):
            monkeypatch.delenv(key, raising=False)
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _offline_ai_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """`default_steps` must never load SigLIP in a test (VIS-REQ-029): without an
    injected `models_factory` it gets the offline fakes."""
    from ai_fakes import make_models

    monkeypatch.setattr("worker.ai.production_models_factory", lambda settings: make_models)
