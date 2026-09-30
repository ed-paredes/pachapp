"""GET /garments and GET /garments/{id} (API-REQ-003..005, API-SCN-001)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from api.deps import get_engine
from api.main import create_app
from shared.enums import (
    GarmentCategory,
    GarmentStatus,
    JobStatus,
    JobStep,
    OutfitSlot,
    OutfitSource,
)
from shared.models import Garment, Job, Outfit, OutfitItem
from shared.settings import Settings

BASE = datetime(2026, 1, 1, tzinfo=UTC)


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


def _garment(index: int = 0, **fields) -> Garment:
    fields.setdefault("img_original", f"original/{index}.jpg")
    fields.setdefault("created_at", BASE + timedelta(minutes=index))
    return Garment(**fields)


def _add(client: TestClient, *garments: Garment) -> None:
    with _db(client) as session:
        session.add_all(garments)
        session.commit()


def test_api_scn_001_filtered_paginated_listing(client: TestClient) -> None:
    rows = [
        _garment(i, category=GarmentCategory.top, status=GarmentStatus.active) for i in range(50)
    ]
    rows += [
        _garment(50 + i, category=GarmentCategory.top, status=GarmentStatus.archived)
        for i in range(10)
    ]
    rows += [_garment(60, category=GarmentCategory.bottom, status=GarmentStatus.active)]
    _add(client, *rows)

    response = client.get("/garments?status=active&category=top&page=1&page_size=20")

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["page"], body["page_size"]) == (50, 1, 20)
    assert len(body["items"]) == 20
    assert {item["category"] for item in body["items"]} == {"top"}
    assert {item["status"] for item in body["items"]} == {"active"}
    last = client.get("/garments?status=active&category=top&page=3&page_size=20").json()
    assert len(last["items"]) == 10


def test_defaults_sort_created_desc_all_statuses_and_pagination_defaults(
    client: TestClient,
) -> None:
    statuses = list(GarmentStatus)
    _add(client, *[_garment(i, status=statuses[i % 3]) for i in range(6)])

    body = client.get("/garments").json()

    assert (body["total"], body["page"], body["page_size"]) == (6, 1, 50)
    created = [item["created_at"] for item in body["items"]]
    assert created == sorted(created, reverse=True)
    assert {item["status"] for item in body["items"]} == {"active", "laundry", "archived"}


def test_repeatable_status_filter(client: TestClient) -> None:
    statuses = list(GarmentStatus)
    _add(client, *[_garment(i, status=statuses[i % 3]) for i in range(6)])

    body = client.get("/garments?status=active&status=laundry").json()

    assert body["total"] == 4
    assert {item["status"] for item in body["items"]} == {"active", "laundry"}


def test_color_matches_any_entry_and_season_containment(client: TestClient) -> None:
    _add(
        client,
        _garment(0, colors=[_color("rojo", 0.6), _color("negro", 0.4)], seasons=["winter"]),
        _garment(1, colors=[_color("azul")], seasons=["summer", "spring"]),
        _garment(2, colors=None, seasons=None),
    )

    by_secondary_color = client.get("/garments?color=negro").json()
    assert by_secondary_color["total"] == 1
    assert by_secondary_color["items"][0]["colors"][1]["name"] == "negro"
    assert client.get("/garments?color=verde").json()["total"] == 0
    assert client.get("/garments?season=spring").json()["total"] == 1
    assert client.get("/garments?season=winter&color=rojo").json()["total"] == 1
    assert client.get("/garments?season=winter&color=azul").json()["total"] == 0


def test_needs_review_filter(client: TestClient) -> None:
    _add(client, _garment(0, needs_review=True), _garment(1), _garment(2))

    assert client.get("/garments?needs_review=true").json()["total"] == 1
    assert client.get("/garments?needs_review=false").json()["total"] == 2


def test_sorting_puts_null_last_and_breaks_ties_by_id(client: TestClient) -> None:
    _add(
        client,
        _garment(0, id="a", wear_count=2, last_worn_at=date(2026, 1, 5)),
        _garment(1, id="b", wear_count=2, last_worn_at=None),
        _garment(2, id="c", wear_count=9, last_worn_at=date(2026, 3, 1)),
    )

    def ids(query: str) -> list[str]:
        return [item["id"] for item in client.get(f"/garments?{query}").json()["items"]]

    assert ids("sort=wear_count&order=desc") == ["c", "a", "b"]
    assert ids("sort=wear_count&order=asc") == ["a", "b", "c"]
    assert ids("sort=last_worn_at&order=desc") == ["c", "a", "b"]
    assert ids("sort=last_worn_at&order=asc") == ["a", "c", "b"]
    assert ids("sort=created_at&order=asc") == ["a", "b", "c"]


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=0",
        "page_size=201",
        "sort=colors",
        "order=up",
        "category=hat",
        "status=gone",
        "season=monsoon",
        "needs_review=maybe",
    ],
)
def test_invalid_params_are_422(client: TestClient, query: str) -> None:
    assert client.get(f"/garments?{query}").status_code == 422


def test_list_item_shape_and_latest_job(client: TestClient) -> None:
    garment = _garment(
        0,
        category=GarmentCategory.top,
        colors=[_color("rojo")],
        is_neutral=False,
        img_thumb="thumb/x.webp",
        img_cutout="cutout/x.png",
    )
    _add(
        client,
        garment,
        Job(garment_id=garment.id, status=JobStatus.failed, error="x", created_at=BASE),
        Job(
            garment_id=garment.id,
            status=JobStatus.running,
            step=JobStep.color,
            progress=40,
            created_at=BASE + timedelta(minutes=1),
        ),
    )

    (item,) = client.get("/garments").json()["items"]

    assert set(item) == {
        "id", "category", "subcategory", "colors", "is_neutral", "pattern", "status",
        "needs_review", "user_verified", "img_thumb", "img_cutout", "wear_count",
        "last_worn_at", "created_at", "job",
    }  # fmt: skip
    assert item["img_thumb"] == "thumb/x.webp"
    assert item["job"]["status"] == "running"
    assert (item["job"]["step"], item["job"]["progress"]) == ("color", 40)


def test_list_item_without_job_has_null_job(client: TestClient) -> None:
    _add(client, _garment(0))

    assert client.get("/garments").json()["items"][0]["job"] is None


def test_get_garment_detail_includes_confidence_and_outfit_count(client: TestClient) -> None:
    garment = _garment(
        0,
        category=GarmentCategory.top,
        colors=[_color("rojo")],
        color_confidence=0.8,
        ai_confidence={"category": {"value": "top", "confidence": 0.6, "source": "zero_shot"}},
        formality=3,
        style_tags=["casual"],
        seasons=["winter"],
        warmth=4,
        material="lana",
        brand="X",
        notes="n",
    )
    outfits = [Outfit(source=OutfitSource.manual), Outfit(source=OutfitSource.manual)]
    _add(
        client,
        garment,
        *outfits,
    )
    _add(
        client,
        *[OutfitItem(outfit_id=o.id, garment_id=garment.id, slot=OutfitSlot.top) for o in outfits],
    )

    body = client.get(f"/garments/{garment.id}").json()

    assert body["id"] == garment.id
    assert body["img_original"] == garment.img_original
    assert body["color_confidence"] == 0.8
    assert body["ai_confidence"]["category"] == {
        "value": "top", "confidence": 0.6, "source": "zero_shot",
    }  # fmt: skip
    assert (body["formality"], body["warmth"], body["material"]) == (3, 4, "lana")
    assert (body["style_tags"], body["seasons"]) == (["casual"], ["winter"])
    assert (body["brand"], body["notes"]) == ("X", "n")
    assert body["outfit_count"] == 2


def test_get_garment_without_ai_data(client: TestClient) -> None:
    garment = _garment(0)
    _add(client, garment)

    body = client.get(f"/garments/{garment.id}").json()

    assert body["ai_confidence"] is None
    assert body["outfit_count"] == 0
    assert body["job"] is None


def test_get_garment_404_envelope(client: TestClient) -> None:
    response = client.get("/garments/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GARMENT_NOT_FOUND"
