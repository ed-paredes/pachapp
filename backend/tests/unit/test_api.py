from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from shared.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        llm_provider="anthropic",
        llm_model_id="claude-sonnet-5-20260101",
        llm_api_key="test-secret-key",
        ml_embed_revision="test-revision",
    )


def test_health_ok(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_preflight_allows_configured_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"
    assert response.headers.get("access-control-allow-credentials") != "true"


def test_cors_preflight_rejects_unknown_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.options(
        "/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert response.headers.get("access-control-allow-credentials") != "true"
