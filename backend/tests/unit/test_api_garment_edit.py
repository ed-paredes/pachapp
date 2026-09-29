"""PATCH /garments/{id} and POST /garments/{id}/review/complete
(API-REQ-006/007/019, API-SCN-002/002b, DAT-REQ-012/016/018/019)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from api.deps import get_engine
from api.main import create_app
from shared.enums import GarmentCategory, GarmentPattern
from shared.models import AiCorrection, Garment
from shared.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", ml_embed_revision="test-revision"
    )
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as test_client:
        yield test_client


def _db(client: TestClient) -> Session:
    return Session(get_engine(client.app), expire_on_commit=False)  # type: ignore[arg-type]


def _color(name: str, proportion: float = 1.0) -> dict:
    return {"name": name, "hex": "#112233", "lab": [1.0, 2.0, 3.0], "proportion": proportion}


def _seed(client: TestClient, **fields) -> str:
    fields.setdefault("img_original", "original/x.jpg")
    garment = Garment(**fields)
    with _db(client) as session:
        session.add(garment)
        session.commit()
    return garment.id


def _reviewable(client: TestClient) -> str:
    """The API-SCN-002 garment."""
    return _seed(
        client,
        category=GarmentCategory.top,
        formality=2,
        needs_review=True,
        ai_confidence={
            "category": {"value": "top", "confidence": 0.6, "source": "zero_shot"},
            "formality": {"value": 2, "confidence": 0.4, "source": "zero_shot"},
        },
    )


def _corrections(client: TestClient, garment_id: str) -> list[AiCorrection]:
    with _db(client) as session:
        return list(
            session.exec(select(AiCorrection).where(AiCorrection.garment_id == garment_id)).all()
        )


def _row(client: TestClient, garment_id: str) -> Garment:
    with _db(client) as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment


def test_api_scn_002_correction_writes_ai_correction_and_keeps_review_state(
    client: TestClient,
) -> None:
    garment_id = _reviewable(client)

    response = client.patch(f"/garments/{garment_id}", json={"category": "mid_layer"})

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "mid_layer"
    assert body["ai_confidence"]["category"] == {
        "value": "mid_layer", "confidence": 1.0, "source": "user",
    }  # fmt: skip
    assert body["ai_confidence"]["formality"]["source"] == "zero_shot"
    assert (body["needs_review"], body["user_verified"]) == (True, False)
    (correction,) = _corrections(client, garment_id)
    assert (correction.field, correction.ai_value, correction.corrected_value) == (
        "category", "top", "mid_layer",
    )  # fmt: skip


def test_api_scn_002b_review_complete_after_partial_fix(client: TestClient) -> None:
    garment_id = _reviewable(client)
    client.patch(f"/garments/{garment_id}", json={"category": "mid_layer"})

    response = client.post(f"/garments/{garment_id}/review/complete")

    assert response.status_code == 200
    body = response.json()
    assert (body["needs_review"], body["user_verified"]) == (False, True)
    assert body["ai_confidence"]["formality"]["confidence"] == 0.4  # untouched
    assert body["category"] == "mid_layer"


def test_review_complete_is_idempotent_and_404s(client: TestClient) -> None:
    garment_id = _reviewable(client)

    first = client.post(f"/garments/{garment_id}/review/complete").json()
    second = client.post(f"/garments/{garment_id}/review/complete").json()

    assert (second["needs_review"], second["user_verified"]) == (False, True)
    assert second["updated_at"] == first["updated_at"]
    assert client.post("/garments/missing/review/complete").status_code == 404
    assert client.post("/garments/missing/review/complete").json()["error"]["code"] == (
        "GARMENT_NOT_FOUND"
    )


def test_patch_404(client: TestClient) -> None:
    response = client.patch("/garments/missing", json={"notes": "x"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GARMENT_NOT_FOUND"


def test_every_edit_of_a_tracked_field_writes_a_correction(client: TestClient) -> None:
    garment_id = _reviewable(client)

    client.patch(f"/garments/{garment_id}", json={"formality": 4})
    client.patch(f"/garments/{garment_id}", json={"formality": 5})

    pairs = [(c.ai_value, c.corrected_value) for c in _corrections(client, garment_id)]
    assert sorted(pairs) == [(2, 4), (4, 5)]
    assert _row(client, garment_id).formality == 5


def test_unchanged_value_writes_no_correction(client: TestClient) -> None:
    garment_id = _reviewable(client)

    body = client.patch(f"/garments/{garment_id}", json={"category": "top"}).json()

    assert _corrections(client, garment_id) == []
    assert body["ai_confidence"]["category"]["source"] == "zero_shot"


def test_untracked_field_writes_no_correction(client: TestClient) -> None:
    garment_id = _seed(client, pattern=GarmentPattern.solid)

    body = client.patch(
        f"/garments/{garment_id}",
        json={"pattern": "striped", "brand": "X", "notes": "n", "status": "laundry"},
    ).json()

    assert _corrections(client, garment_id) == []
    assert body["ai_confidence"] is None
    assert (body["pattern"], body["brand"], body["notes"], body["status"]) == (
        "striped", "X", "n", "laundry",
    )  # fmt: skip


def test_patch_updates_list_fields_and_clears_brand(client: TestClient) -> None:
    garment_id = _seed(
        client,
        style_tags=["casual"],
        seasons=["summer"],
        brand="X",
        ai_confidence={"seasons": {"value": ["summer"], "confidence": 0.5, "source": "llm"}},
    )

    body = client.patch(
        f"/garments/{garment_id}",
        json={"style_tags": ["classic", "minimal"], "seasons": ["winter"], "brand": None},
    ).json()

    assert body["style_tags"] == ["classic", "minimal"]
    assert body["brand"] is None
    (correction,) = _corrections(client, garment_id)
    assert (correction.field, correction.ai_value, correction.corrected_value) == (
        "seasons", ["summer"], ["winter"],
    )  # fmt: skip
    assert body["ai_confidence"]["seasons"]["value"] == ["winter"]


def test_colors_pipeline_value_is_corrected_and_neutral_recomputed(client: TestClient) -> None:
    garment_id = _seed(
        client,
        colors=[_color("rojo")],
        is_neutral=False,
        color_confidence=0.5,
        needs_review=True,
    )

    body = client.patch(
        f"/garments/{garment_id}", json={"colors": [_color("marino", 0.7), _color("blanco", 0.3)]}
    ).json()

    assert body["colors"][0]["name"] == "marino"
    assert body["is_neutral"] is True
    assert body["color_confidence"] == 1.0
    assert body["needs_review"] is True
    (correction,) = _corrections(client, garment_id)
    assert correction.field == "colors"
    assert correction.ai_value[0]["name"] == "rojo"
    assert correction.corrected_value[0]["name"] == "marino"

    # A second edit now replaces a user value: no new correction row, still recomputed.
    body = client.patch(f"/garments/{garment_id}", json={"colors": [_color("rojo")]}).json()
    assert body["is_neutral"] is False
    assert len(_corrections(client, garment_id)) == 1


def test_colors_without_previous_value_writes_no_correction(client: TestClient) -> None:
    garment_id = _seed(client)

    body = client.patch(f"/garments/{garment_id}", json={"colors": [_color("gris")]}).json()

    assert _corrections(client, garment_id) == []
    assert (body["is_neutral"], body["color_confidence"]) == (True, 1.0)


def test_identical_colors_are_a_no_op(client: TestClient) -> None:
    garment_id = _seed(client, colors=[_color("rojo")], is_neutral=False, color_confidence=0.5)

    body = client.patch(f"/garments/{garment_id}", json={"colors": [_color("rojo")]}).json()

    assert _corrections(client, garment_id) == []
    assert body["color_confidence"] == 0.5


@pytest.mark.parametrize(
    "field",
    [
        "wear_count", "last_worn_at", "embedding", "ai_confidence", "needs_review",
        "user_verified", "img_original", "img_cutout", "img_thumb", "color_confidence",
        "is_neutral", "id",
    ],
)  # fmt: skip
def test_forbidden_fields_are_422_and_change_nothing(client: TestClient, field: str) -> None:
    garment_id = _reviewable(client)

    response = client.patch(f"/garments/{garment_id}", json={"notes": "x", field: 1})

    assert response.status_code == 422
    row = _row(client, garment_id)
    assert row.notes is None and row.wear_count == 0
    assert (row.needs_review, row.user_verified) == (True, False)
    assert _corrections(client, garment_id) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "hat"},
        {"pattern": "dotted"},
        {"status": "gone"},
        {"status": None},
        {"category": None},
        {"colors": None},
        {"formality": 0},
        {"formality": 6},
        {"warmth": 6},
        {"style_tags": ["goth"]},
        {"seasons": ["monsoon"]},
        {"colors": [_color("rojo", 0.3), _color("azul", 0.7)]},
        {"colors": [_color("rojo", 0.8), _color("azul", 0.8)]},
    ],
)
def test_invalid_values_are_422(client: TestClient, payload: dict) -> None:
    garment_id = _reviewable(client)

    assert client.patch(f"/garments/{garment_id}", json=payload).status_code == 422
    assert _corrections(client, garment_id) == []


def test_empty_patch_is_a_no_op(client: TestClient) -> None:
    garment_id = _reviewable(client)

    response = client.patch(f"/garments/{garment_id}", json={})

    assert response.status_code == 200
    assert _corrections(client, garment_id) == []
