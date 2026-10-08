"""GET /tryon/capabilities, POST /tryon and GET /tryon/{id} (09-virtual-tryon.md §6.7)."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, select

from api.deps import get_engine
from api.main import create_app
from shared.enums import GarmentCategory, JobStatus, OutfitSlot, OutfitSource
from shared.models import Garment, Outfit, OutfitItem, TryOnRender
from shared.settings import Settings


def _settings(tmp_path: Path, *, enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        tryon_enabled=enabled,
        tryon_assets_dir=tmp_path / "assets",
        tryon_mannequin="m1",
    )


def _write_mannequin(assets: Path, mannequin_id: str = "m1") -> None:
    folder = assets / "mannequins" / mannequin_id
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("person.png", "mask_upper.png", "mask_lower.png", "mask_overall.png"):
        Image.new("L", (8, 8), 0).save(folder / name)
    (folder / "meta.json").write_text(json.dumps({"id": mannequin_id}), encoding="utf-8")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    _write_mannequin(tmp_path / "assets")
    return _settings(tmp_path)


def _client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from _client(settings)


def _db(client: TestClient) -> Session:
    return Session(get_engine(client.app))  # type: ignore[arg-type]


def _garment(
    client: TestClient,
    settings: Settings,
    category: GarmentCategory | None,
    *,
    cutout: bool = True,
    color: int = 0,
) -> str:
    garment = Garment(img_original="original/x.jpg", category=category)
    if cutout:
        assert settings.images_root is not None
        garment.img_cutout = f"cutout/{garment.id}.png"
        path = settings.images_root / garment.img_cutout
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (4, 4), (color, 0, 0, 255)).save(path)
    garment_id = garment.id
    with _db(client) as session:
        session.add(garment)
        session.commit()
    return garment_id


def _post(client: TestClient, **body: Any):
    return client.post("/tryon", json=body)


def _render(client: TestClient, render_id: str) -> TryOnRender:
    with _db(client) as session:
        render = session.get(TryOnRender, render_id)
        assert render is not None
        return render


def _set_status(client: TestClient, render_id: str, status: JobStatus, **fields: Any) -> None:
    with _db(client) as session:
        render = session.get(TryOnRender, render_id)
        assert render is not None
        render.status = status
        for name, value in fields.items():
            setattr(render, name, value)
        session.add(render)
        session.commit()


def test_capabilities_enabled(client: TestClient) -> None:
    body = client.get("/tryon/capabilities").json()
    assert body["enabled"] is True
    assert body["max_passes"] == 3
    assert set(body["supported_categories"]) == {
        "top",
        "mid_layer",
        "outerwear",
        "bottom",
        "one_piece",
    }


def test_capabilities_and_post_when_disabled(tmp_path: Path) -> None:
    for client in _client(_settings(tmp_path, enabled=False)):
        assert client.get("/tryon/capabilities").json()["enabled"] is False
        response = _post(client, garment_ids=[str(uuid4())])
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "TRYON_DISABLED"


def test_get_works_when_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=False)
    for client in _client(settings):
        render = TryOnRender(cache_key="k", mannequin_id="m1")
        with _db(client) as session:
            session.add(render)
            session.commit()
            render_id = render.id
        assert client.get(f"/tryon/{render_id}").status_code == 200


def test_nothing_compatible_is_422(client: TestClient, settings: Settings) -> None:
    shoes = _garment(client, settings, GarmentCategory.shoes)
    response = _post(client, garment_ids=[shoes])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "TRYON_NO_COMPATIBLE_GARMENTS"
    assert error["details"]["unsupported_garment_ids"] == [shoes]


def test_garment_without_cutout_is_422(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top, cutout=False)
    response = _post(client, garment_ids=[top])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "TRYON_GARMENT_NOT_READY"
    assert error["details"]["garment_ids"] == [top]


def test_unknown_garment_and_outfit_are_404(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    missing = str(uuid4())
    response = _post(client, garment_ids=[top, missing])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GARMENT_NOT_FOUND"
    response = _post(client, outfit_id=missing)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OUTFIT_NOT_FOUND"


def test_unknown_mannequin_is_422(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    for bad in ("nope", "../x"):
        response = _post(client, garment_ids=[top], mannequin_id=bad)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "TRYON_INVALID_MANNEQUIN"


@pytest.mark.parametrize(
    "body",
    [{}, {"garment_ids": [str(uuid4())], "outfit_id": str(uuid4())}, {"garment_ids": []}],
)
def test_exactly_one_source_is_required(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/tryon", json=body).status_code == 422


def test_create_plans_passes_and_is_idempotent(client: TestClient, settings: Settings) -> None:
    shoes = _garment(client, settings, GarmentCategory.shoes)
    top = _garment(client, settings, GarmentCategory.top)
    top2 = _garment(client, settings, GarmentCategory.top, color=9)
    bottom = _garment(client, settings, GarmentCategory.bottom)

    first = _post(client, garment_ids=[top, shoes, top2, bottom])
    assert first.status_code == 202
    body = first.json()
    assert body["status"] == "pending"
    assert body["step"] == "queued"
    assert body["progress"] == 0
    assert body["img"] is None
    assert body["garment_ids"] == [bottom, top]  # lower first, then upper
    assert body["skipped_garment_ids"] == [top2]
    assert body["unsupported_garment_ids"] == [shoes]
    params = _render(client, body["id"]).params
    assert params["cloth_types"] == ["lower", "upper"]
    assert params["width"] == settings.tryon_width

    again = _post(client, garment_ids=[top, shoes, top2, bottom])
    assert again.status_code == 202
    assert again.json()["id"] == body["id"]
    with _db(client) as session:
        assert len(session.exec(select(TryOnRender)).all()) == 1


def test_cache_hit_returns_200_and_refreshes_access(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    render_id = _post(client, garment_ids=[top]).json()["id"]
    old = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    _set_status(
        client,
        render_id,
        JobStatus.done,
        img_path=f"tryon/{render_id}.webp",
        last_accessed_at=old,
    )

    response = _post(client, garment_ids=[top])
    assert response.status_code == 200
    assert response.json()["id"] == render_id
    assert response.json()["img"] == f"tryon/{render_id}.webp"
    assert _render(client, render_id).last_accessed_at > old


def test_failed_render_is_reset_on_resubmit(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    render_id = _post(client, garment_ids=[top]).json()["id"]
    _set_status(
        client,
        render_id,
        JobStatus.failed,
        error="boom",
        step="dressing_1",
        progress=40,
        attempts=3,
        claimed_by="w1",
    )

    response = _post(client, garment_ids=[top])
    assert response.status_code == 202
    assert response.json()["id"] == render_id
    assert response.json()["status"] == "pending"
    assert response.json()["error"] is None
    render = _render(client, render_id)
    assert (render.step, render.progress, render.attempts) == ("queued", 0, 0)
    assert render.claimed_by is None


@pytest.mark.parametrize("status", [JobStatus.claimed, JobStatus.running])
def test_in_flight_render_is_not_duplicated(
    client: TestClient, settings: Settings, status: JobStatus
) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    render_id = _post(client, garment_ids=[top]).json()["id"]
    _set_status(client, render_id, status, step="dressing_1", progress=30)
    response = _post(client, garment_ids=[top])
    assert response.status_code == 202
    assert response.json()["id"] == render_id
    assert response.json()["step"] == "dressing_1"


def test_key_changes_with_cutout_and_category(client: TestClient, settings: Settings) -> None:
    assert settings.images_root is not None
    top = _garment(client, settings, GarmentCategory.top)
    first = _post(client, garment_ids=[top]).json()["id"]

    cutout = settings.images_root / f"cutout/{top}.png"
    Image.new("RGBA", (4, 4), (0, 200, 0, 255)).save(cutout)
    second = _post(client, garment_ids=[top]).json()["id"]
    assert second != first

    with _db(client) as session:
        garment = session.get(Garment, top)
        assert garment is not None
        garment.category = GarmentCategory.bottom
        session.add(garment)
        session.commit()
    third = _post(client, garment_ids=[top]).json()["id"]
    assert third not in {first, second}


def test_outfit_id_path(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    bottom = _garment(client, settings, GarmentCategory.bottom)
    shoes = _garment(client, settings, GarmentCategory.shoes)
    with _db(client) as session:
        outfit = Outfit(source=OutfitSource.manual)
        session.add(outfit)
        session.flush()
        session.add(OutfitItem(outfit_id=outfit.id, garment_id=top, slot=OutfitSlot.top, layer=1))
        session.add(
            OutfitItem(outfit_id=outfit.id, garment_id=bottom, slot=OutfitSlot.bottom, layer=0)
        )
        session.add(OutfitItem(outfit_id=outfit.id, garment_id=shoes, slot=OutfitSlot.shoes))
        outfit_id = outfit.id
        session.commit()

    response = _post(client, outfit_id=outfit_id)
    assert response.status_code == 202
    body = response.json()
    assert body["garment_ids"] == [bottom, top]
    assert body["unsupported_garment_ids"] == [shoes]
    assert _render(client, body["id"]).outfit_id == outfit_id


def test_get_render(client: TestClient, settings: Settings) -> None:
    top = _garment(client, settings, GarmentCategory.top)
    render_id = _post(client, garment_ids=[top]).json()["id"]

    body = client.get(f"/tryon/{render_id}").json()
    assert body["status"] == "pending"
    assert body["img"] is None

    _set_status(client, render_id, JobStatus.done, img_path=f"tryon/{render_id}.webp")
    assert client.get(f"/tryon/{render_id}").json()["img"] == f"tryon/{render_id}.webp"

    missing = client.get(f"/tryon/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TRYON_NOT_FOUND"
