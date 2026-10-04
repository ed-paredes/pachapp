"""`/wear-log` endpoints and the derived garment counters (FBH-REQ-007..010)."""

from __future__ import annotations

from conftest import TODAY, add_garment, basic_wardrobe, days_ago, db
from fastapi.testclient import TestClient
from sqlmodel import select

from shared.enums import GarmentCategory as Cat
from shared.models import Garment, WearLog


def _outfit(client: TestClient, ids: list[str]) -> str:
    with db(client) as session:
        slots = {g: session.get(Garment, g).category.value for g in ids}  # type: ignore[union-attr]
    response = client.post(
        "/outfits",
        json={
            "source": "manual",
            "items": [{"garment_id": g, "slot": slots[g]} for g in ids],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _stats(client: TestClient, garment_id: str):
    with db(client) as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment.wear_count, garment.last_worn_at


def _wardrobe(client: TestClient) -> tuple[dict[str, str], str, str]:
    ids = basic_wardrobe(client)
    x = _outfit(client, [ids["t1"], ids["b1"], ids["s1"]])
    y = _outfit(client, [ids["t2"], ids["b1"], ids["s2"]])  # shares b1 with x
    return ids, x, y


def test_post_defaults_to_today_and_updates_every_garment_of_the_outfit(client: TestClient) -> None:
    ids, x, _ = _wardrobe(client)

    response = client.post("/wear-log", json={"outfit_id": x})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "date", "outfit_id", "created_at"}
    assert body["date"] == TODAY.isoformat() and body["outfit_id"] == x
    for key in ("t1", "b1", "s1"):
        assert _stats(client, ids[key]) == (1, TODAY)
    assert _stats(client, ids["t2"]) == (0, None)  # not in the outfit


def test_post_with_an_explicit_date_keeps_the_latest_as_last_worn(client: TestClient) -> None:
    ids, x, y = _wardrobe(client)

    client.post("/wear-log", json={"outfit_id": x, "date": days_ago(10).isoformat()})
    client.post("/wear-log", json={"outfit_id": y, "date": days_ago(3).isoformat()})
    client.post("/wear-log", json={"outfit_id": x, "date": days_ago(20).isoformat()})

    assert _stats(client, ids["b1"]) == (3, days_ago(3))  # in x, y and x again
    assert _stats(client, ids["t1"]) == (2, days_ago(10))
    assert _stats(client, ids["t2"]) == (1, days_ago(3))


def test_post_for_a_logged_day_is_a_409_with_the_existing_entry(client: TestClient) -> None:
    ids, x, y = _wardrobe(client)
    client.post("/wear-log", json={"outfit_id": x})

    response = client.post("/wear-log", json={"outfit_id": y})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "WEAR_LOG_CONFLICT"
    assert error["message"] == "Ya registraste un outfit para este día."
    assert error["details"]["outfit_id"] == x and error["details"]["date"] == TODAY.isoformat()
    assert _stats(client, ids["t2"]) == (0, None)  # nothing changed
    with db(client) as session:
        assert len(session.exec(select(WearLog)).all()) == 1


def test_post_with_an_unknown_outfit_is_a_404(client: TestClient) -> None:
    response = client.post("/wear-log", json={"outfit_id": "3b7e0f0e-6a54-4e3b-9d1c-0a6a2f0a9c11"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OUTFIT_NOT_FOUND"
    assert client.post("/wear-log", json={"outfit_id": "nope"}).status_code == 422
    assert client.post("/wear-log", json={}).status_code == 422


def test_put_replaces_the_day_and_recomputes_both_outfits(client: TestClient) -> None:
    ids, x, y = _wardrobe(client)
    client.post("/wear-log", json={"outfit_id": x, "date": days_ago(9).isoformat()})
    client.post("/wear-log", json={"outfit_id": x})  # a second day for x

    response = client.put(f"/wear-log/{TODAY.isoformat()}", json={"outfit_id": y})

    assert response.status_code == 200
    assert response.json()["date"] == TODAY.isoformat() and response.json()["outfit_id"] == y
    # old outfit loses today, keeps its older day; new outfit gains today
    assert _stats(client, ids["t1"]) == (1, days_ago(9))
    assert _stats(client, ids["s1"]) == (1, days_ago(9))
    assert _stats(client, ids["t2"]) == (1, TODAY)
    assert _stats(client, ids["s2"]) == (1, TODAY)
    assert _stats(client, ids["b1"]) == (2, TODAY)  # in both outfits: x on day -9, y today
    with db(client) as session:
        assert len(session.exec(select(WearLog)).all()) == 2


def test_put_to_the_same_outfit_changes_nothing(client: TestClient) -> None:
    ids, x, _ = _wardrobe(client)
    client.post("/wear-log", json={"outfit_id": x})

    assert client.put(f"/wear-log/{TODAY.isoformat()}", json={"outfit_id": x}).status_code == 200

    assert _stats(client, ids["t1"]) == (1, TODAY)


def test_put_errors(client: TestClient) -> None:
    _, x, _ = _wardrobe(client)

    missing_day = client.put("/wear-log/2026-01-01", json={"outfit_id": x})
    client.post("/wear-log", json={"outfit_id": x})
    unknown_outfit = client.put(
        f"/wear-log/{TODAY.isoformat()}", json={"outfit_id": "3b7e0f0e-6a54-4e3b-9d1c-0a6a2f0a9c11"}
    )

    assert missing_day.status_code == 404
    assert missing_day.json()["error"]["code"] == "WEAR_LOG_NOT_FOUND"
    assert (
        missing_day.json()["error"]["message"] == "No hay ningún outfit registrado para este día."
    )
    assert unknown_outfit.status_code == 404
    assert unknown_outfit.json()["error"]["code"] == "OUTFIT_NOT_FOUND"
    assert client.put("/wear-log/not-a-date", json={"outfit_id": x}).status_code == 422


def test_delete_removes_the_day_and_recomputes_the_counters(client: TestClient) -> None:
    ids, x, y = _wardrobe(client)
    client.post("/wear-log", json={"outfit_id": y, "date": days_ago(4).isoformat()})
    client.post("/wear-log", json={"outfit_id": x})

    response = client.delete(f"/wear-log/{TODAY.isoformat()}")

    assert response.status_code == 204 and response.content == b""
    assert _stats(client, ids["t1"]) == (0, None)
    assert _stats(client, ids["b1"]) == (1, days_ago(4))  # still worn on the earlier day
    assert client.delete(f"/wear-log/{TODAY.isoformat()}").status_code == 404
    # the day is free again
    assert client.post("/wear-log", json={"outfit_id": x}).status_code == 201


def test_counters_are_visible_through_the_garment_endpoints(client: TestClient) -> None:
    top = add_garment(client, Cat.top)
    bottom = add_garment(client, Cat.bottom)
    outfit = _outfit(client, [top, bottom])

    client.post("/wear-log", json={"outfit_id": outfit})

    detail = client.get(f"/garments/{top}").json()
    assert detail["wear_count"] == 1 and detail["last_worn_at"] == TODAY.isoformat()
    assert detail["outfit_count"] == 1


def test_wear_log_endpoints_are_tagged_in_the_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/wear-log"]["post"]["tags"] == ["wear-log"]
    assert schema["paths"]["/wear-log/{date}"]["put"]["tags"] == ["wear-log"]
    assert schema["paths"]["/outfits/generate"]["post"]["tags"] == ["outfits"]
    assert schema["paths"]["/outfits"]["post"]["tags"] == ["outfits"]


def test_a_lost_race_for_the_same_day_is_still_a_clean_409(client: TestClient, monkeypatch) -> None:
    from api.routers import wear_log

    ids, x, y = _wardrobe(client)
    client.post("/wear-log", json={"outfit_id": x})
    real = wear_log._log_for
    calls = {"n": 0}

    def stale(session, day):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(session, day)  # the first look-up misses

    monkeypatch.setattr(wear_log, "_log_for", stale)

    response = client.post("/wear-log", json={"outfit_id": y})

    assert response.status_code == 409
    assert response.json()["error"]["details"]["outfit_id"] == x
    assert _stats(client, ids["t2"]) == (0, None)
