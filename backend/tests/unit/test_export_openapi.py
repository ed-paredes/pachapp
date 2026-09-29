from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.export_openapi import export_openapi_json


def _set_dummy_llm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`export_openapi_json` builds the app via `get_settings()`, so it needs
    valid (dummy is fine) env vars, per the module's own docstring."""
    monkeypatch.setenv("PACHAPP_DATA_DIR", str(tmp_path / "pachapp-data"))
    monkeypatch.setenv("PACHAPP_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("PACHAPP_LLM_MODEL_ID", "claude-sonnet-5-20260101")
    monkeypatch.setenv("PACHAPP_LLM_API_KEY", "test-secret-key")
    monkeypatch.setenv("PACHAPP_ML_EMBED_REVISION", "test-revision")


def test_export_openapi_json_writes_valid_json_creating_parent_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_dummy_llm_env(monkeypatch, tmp_path)
    output = tmp_path / "nested" / "does" / "not" / "exist" / "openapi.json"
    assert not output.parent.exists()

    text = export_openapi_json(output)

    assert output.exists()
    written = output.read_text()
    assert written == text + "\n"
    schema = json.loads(written)
    assert "/health" in schema["paths"]


def test_export_openapi_json_returns_schema_text_without_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_dummy_llm_env(monkeypatch, tmp_path)

    text = export_openapi_json()

    schema = json.loads(text)
    assert "/health" in schema["paths"]
