"""GET/PATCH /settings (API-REQ-014/015, API-SCN-005, DAT-REQ-011)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from api.deps import get_engine
from api.main import create_app
from shared.models import Setting
from shared.settings import Settings

DEFAULTS = {
    "weight_color": 0.35,
    "weight_style": 0.25,
    "weight_novelty": 0.25,
    "weight_preference": 0.15,
    "no_repeat_days": 14,
    "max_accessories": 2,
    "duplicate_warning_threshold": 0.92,
    "needs_review_threshold": 0.7,
    "color_review_threshold": 0.7,
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", ml_embed_revision="test-revision"
    )
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with Session(get_engine(app)) as session:  # the migration seeds this row in production
        session.add(Setting())
        session.commit()
    with TestClient(app) as test_client:
        yield test_client


def test_get_returns_the_nine_fields(client: TestClient) -> None:
    response = client.get("/settings")

    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_get_creates_defaults_when_row_is_missing(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", ml_embed_revision="r")
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as bare:
        assert bare.get("/settings").json() == DEFAULTS


def test_partial_patch_changes_only_given_fields(client: TestClient) -> None:
    response = client.patch("/settings", json={"no_repeat_days": 7, "needs_review_threshold": 0.5})

    assert response.status_code == 200
    assert response.json() == {**DEFAULTS, "no_repeat_days": 7, "needs_review_threshold": 0.5}
    assert client.get("/settings").json() == response.json()


def test_weights_summing_to_one_are_accepted(client: TestClient) -> None:
    weights = {
        "weight_color": 0.4,
        "weight_style": 0.3,
        "weight_novelty": 0.2,
        "weight_preference": 0.105,  # 1.005: inside the tolerance
    }
    response = client.patch("/settings", json=weights)

    assert response.status_code == 200
    assert response.json()["weight_preference"] == 0.105


def test_api_scn_005_weights_over_one_are_rejected_and_nothing_changes(
    client: TestClient,
) -> None:
    response = client.patch("/settings", json={"weight_color": 0.9, "no_repeat_days": 1})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_WEIGHTS"
    assert client.get("/settings").json() == DEFAULTS  # incl. the non-weight field


def test_weight_sum_uses_stored_values_for_absent_weights(client: TestClient) -> None:
    ok = client.patch("/settings", json={"weight_color": 0.25, "weight_style": 0.35})
    assert ok.status_code == 200

    bad = client.patch("/settings", json={"weight_novelty": 0.5})
    assert bad.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"needs_review_threshold": 1.1},
        {"color_review_threshold": -0.1},
        {"duplicate_warning_threshold": 2},
        {"no_repeat_days": -1},
        {"max_accessories": -1},
        {"weight_color": -0.2},
        {"no_repeat_days": None},
        {"unknown_field": 1},
        {"id": 2},
        {"updated_at": "2026-01-01T00:00:00"},
    ],
)
def test_invalid_patch_is_422_and_writes_nothing(client: TestClient, payload: dict) -> None:
    assert client.patch("/settings", json=payload).status_code == 422
    assert client.get("/settings").json() == DEFAULTS


def test_empty_patch_is_a_no_op(client: TestClient) -> None:
    assert client.patch("/settings", json={}).json() == DEFAULTS
