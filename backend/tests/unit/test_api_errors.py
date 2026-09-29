"""API error envelope (API-REQ-001) and 422 exception (API-REQ-002)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.errors import AppError
from api.main import create_app
from shared.settings import Settings


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", ml_embed_revision="test-revision"
    )
    app = create_app(settings)

    def boom() -> None:
        raise AppError("SOME_CODE", "Algo falló", 409, {"id": "x"})

    def boom_no_details() -> None:
        raise AppError("OTHER", "Otro fallo")

    def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    app.add_api_route("/_boom", boom)
    app.add_api_route("/_boom2", boom_no_details)
    app.add_api_route("/_int", needs_int)
    return TestClient(app)


def test_app_error_renders_envelope(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/_boom")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "SOME_CODE", "message": "Algo falló", "details": {"id": "x"}}
    }


def test_app_error_defaults_to_400_with_null_details(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/_boom2")

    assert response.status_code == 400
    assert response.json() == {"error": {"code": "OTHER", "message": "Otro fallo", "details": None}}


def test_validation_errors_keep_fastapi_422_format(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/_int", params={"n": "abc"})

    assert response.status_code == 422
    assert "detail" in response.json()
    assert "error" not in response.json()
