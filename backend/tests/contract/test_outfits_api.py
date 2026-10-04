"""`POST /outfits/generate` and `POST /outfits` (ENG-REQ-020..022, FBH-REQ-017/018)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import add_garment, basic_wardrobe, days_ago, db
from fastapi.testclient import TestClient
from sqlmodel import select

from shared.enums import GarmentCategory as Cat
from shared.enums import GarmentStatus
from shared.models import Garment, Outfit, OutfitItem


def _generate(client: TestClient, **body):
    return client.post("/outfits/generate", json=body)


def test_generate_returns_the_documented_shape(client: TestClient) -> None:
    ids = basic_wardrobe(client)

    response = _generate(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"proposals", "generated_at"}
    assert 1 <= len(body["proposals"]) <= 5
    datetime.fromisoformat(body["generated_at"])
    proposal = body["proposals"][0]
    assert set(proposal) == {"items", "score", "score_breakdown", "explanation"}
    assert set(proposal["score_breakdown"]) == {"color", "style", "novelty", "preference", "total"}
    assert proposal["score"] == proposal["score_breakdown"]["total"]
    assert proposal["explanation"].endswith(".")
    assert [(i["slot"], i["layer"]) for i in proposal["items"]] == [
        ("top", 2),
        ("bottom", 1),
        ("shoes", 0),
    ]
    assert {i["garment_id"] for i in proposal["items"]} <= set(ids.values())


def test_generate_persists_nothing(client: TestClient) -> None:
    basic_wardrobe(client)

    _generate(client)

    with db(client) as session:
        assert session.exec(select(Outfit)).all() == []
        assert session.exec(select(OutfitItem)).all() == []


def test_generate_with_an_empty_or_tiny_wardrobe_is_a_normal_200(client: TestClient) -> None:
    empty = _generate(client)
    assert empty.status_code == 200 and empty.json()["proposals"] == []

    for category in (Cat.top, Cat.bottom, Cat.shoes):
        add_garment(client, category, status=GarmentStatus.laundry)
    add_garment(client, Cat.top)
    tiny = _generate(client)
    assert tiny.status_code == 200 and tiny.json()["proposals"] == []


def test_generate_skips_garments_that_are_not_active(client: TestClient) -> None:
    ids = basic_wardrobe(client)
    benched = add_garment(client, Cat.top, status=GarmentStatus.archived)

    body = _generate(client).json()

    used = {i["garment_id"] for p in body["proposals"] for i in p["items"]}
    assert benched not in used and used <= set(ids.values())


def test_generate_fixed_and_replace_garments(client: TestClient) -> None:
    ids = basic_wardrobe(client)

    fixed = _generate(client, fixed_garment_ids=[ids["t1"]], replace_garment_id=ids["s1"]).json()

    assert fixed["proposals"]
    for p in fixed["proposals"]:
        garments = {i["garment_id"] for i in p["items"]}
        assert ids["t1"] in garments and ids["s1"] not in garments


def test_generate_rejects_invalid_fixed_garments_with_400(client: TestClient) -> None:
    ids = basic_wardrobe(client)

    two_tops = _generate(client, fixed_garment_ids=[ids["t1"], ids["t2"]])
    unknown = _generate(client, fixed_garment_ids=["3b7e0f0e-6a54-4e3b-9d1c-0a6a2f0a9c11"])

    assert two_tops.status_code == 400
    assert two_tops.json()["error"]["code"] == "INVALID_FIXED_GARMENTS"
    assert "hueco" in two_tops.json()["error"]["message"]
    assert unknown.status_code == 400
    assert unknown.json()["error"]["message"] == "Una prenda fijada no existe o no está activa."
    assert _generate(client, fixed_garment_ids=["not-a-uuid"]).status_code == 422


def test_generate_uses_the_wear_history_window(client: TestClient) -> None:
    cat = Cat
    only = [
        add_garment(client, cat.top),
        add_garment(client, cat.bottom),
        add_garment(client, cat.shoes),
    ]
    assert len(_generate(client).json()["proposals"]) == 1
    outfit = _persist(client, only).json()
    client.post("/wear-log", json={"outfit_id": outfit["id"], "date": days_ago(5).isoformat()})

    assert _generate(client).json()["proposals"] == []  # the exact set was worn 5 days ago


def test_generate_reads_embeddings_and_stays_deterministic(client: TestClient) -> None:
    basic_wardrobe(client)

    first = _generate(client, seed=3).json()["proposals"]
    second = _generate(client, seed=3).json()["proposals"]

    assert first == second


def test_feedback_moves_the_preference_of_the_pairs_involved(client: TestClient) -> None:
    ids = basic_wardrobe(client)
    trio = [ids["t1"], ids["b1"], ids["s1"]]

    def preference() -> float:
        proposals = _generate(client, fixed_garment_ids=trio).json()["proposals"]
        assert len(proposals) == 1
        return proposals[0]["score_breakdown"]["preference"]

    assert preference() == 0.5
    _persist(client, trio, rating=-1)
    assert preference() < 0.5
    _persist(client, trio, source="manual", is_favorite=True)
    _persist(client, trio, source="manual", is_favorite=True)
    _persist(client, trio, source="manual", is_favorite=True)
    assert preference() > 0.5


# --- POST /outfits -------------------------------------------------------------


def _persist(client: TestClient, garment_ids: list[str], **fields):
    with db(client) as session:
        slots = {g: session.get(Garment, g).category.value for g in garment_ids}  # type: ignore[union-attr]
    body = {
        "source": "generated",
        "items": [{"garment_id": g, "slot": slots[g], "layer": None} for g in garment_ids],
        **fields,
    }
    return client.post("/outfits", json=body)


def test_post_outfit_persists_items_score_and_flags(client: TestClient) -> None:
    ids = basic_wardrobe(client)
    proposal = _generate(client).json()["proposals"][0]
    body = {
        "source": "generated",
        "items": proposal["items"],
        "score": proposal["score"],
        "score_breakdown": proposal["score_breakdown"],
        "explanation": proposal["explanation"],
        "rating": 1,
        "is_favorite": True,
    }

    response = client.post("/outfits", json=body)

    assert response.status_code == 201
    created = response.json()
    assert created["source"] == "generated" and created["rating"] == 1 and created["is_favorite"]
    assert created["score"] == proposal["score"]
    assert created["score_breakdown"] == proposal["score_breakdown"]
    assert created["explanation"] == proposal["explanation"]
    assert created["name"] is None
    assert [(i["garment_id"], i["slot"], i["layer"]) for i in created["items"]] == [
        (i["garment_id"], i["slot"], i["layer"]) for i in proposal["items"]
    ]
    assert {i["garment_id"] for i in created["items"]} <= set(ids.values())
    with db(client) as session:
        assert len(session.exec(select(Outfit)).all()) == 1
        assert len(session.exec(select(OutfitItem)).all()) == 3


def test_post_outfit_stores_the_canonical_layer_of_each_slot(client: TestClient) -> None:
    top = add_garment(client, Cat.top)
    coat = add_garment(client, Cat.outerwear)
    watch = add_garment(client, Cat.accessory, subcategory="reloj")
    body = {
        "source": "manual",
        "items": [
            {"garment_id": top, "slot": "top", "layer": 99},
            {"garment_id": coat, "slot": "outerwear", "layer": None},
            {"garment_id": watch, "slot": "accessory", "layer": 7},
        ],
    }

    created = client.post("/outfits", json=body).json()

    assert {i["slot"]: i["layer"] for i in created["items"]} == {
        "top": 2,
        "outerwear": 4,
        "accessory": None,
    }


def test_post_outfit_dedupes_a_generated_set_within_five_minutes(client: TestClient) -> None:
    ids = list(basic_wardrobe(client).values())
    trio = [ids[0], ids[2], ids[4]]

    first = _persist(client, trio, rating=-1)
    again = _persist(client, list(reversed(trio)), is_favorite=True)

    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["rating"] == -1 and again.json()["is_favorite"] is False  # not overwritten
    with db(client) as session:
        assert len(session.exec(select(Outfit)).all()) == 1


def test_post_outfit_creates_a_new_row_outside_the_window_or_for_other_sets(
    client: TestClient,
) -> None:
    ids = list(basic_wardrobe(client).values())
    trio = [ids[0], ids[2], ids[4]]
    first = _persist(client, trio).json()
    with db(client) as session:
        outfit = session.get(Outfit, first["id"])
        assert outfit is not None
        outfit.created_at = datetime.now(UTC) - timedelta(minutes=6)
        session.add(outfit)
        session.commit()

    later = _persist(client, trio)
    other = _persist(client, [ids[1], ids[2], ids[4]])

    assert later.status_code == 201 and later.json()["id"] != first["id"]
    assert other.status_code == 201


def test_manual_outfits_are_never_deduplicated(client: TestClient) -> None:
    ids = list(basic_wardrobe(client).values())
    trio = [ids[0], ids[2], ids[4]]

    first = _persist(client, trio, source="manual")
    second = _persist(client, trio, source="manual")

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_post_outfit_validation_errors(client: TestClient) -> None:
    ids = basic_wardrobe(client)
    top, bottom = ids["t1"], ids["b1"]

    unknown = client.post(
        "/outfits",
        json={
            "source": "manual",
            "items": [{"garment_id": "3b7e0f0e-6a54-4e3b-9d1c-0a6a2f0a9c11", "slot": "top"}],
        },
    )
    wrong_slot = client.post(
        "/outfits", json={"source": "manual", "items": [{"garment_id": top, "slot": "bottom"}]}
    )
    empty = client.post("/outfits", json={"source": "manual", "items": []})
    bad_rating = client.post(
        "/outfits",
        json={"source": "manual", "rating": 2, "items": [{"garment_id": top, "slot": "top"}]},
    )
    repeated = client.post(
        "/outfits",
        json={"source": "manual", "items": [{"garment_id": bottom, "slot": "bottom"}] * 2},
    )

    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "GARMENT_NOT_FOUND"
    assert unknown.json()["error"]["message"] == "Alguna prenda del outfit no existe."
    assert wrong_slot.status_code == 400 and wrong_slot.json()["error"]["code"] == "INVALID_OUTFIT"
    assert empty.status_code == bad_rating.status_code == repeated.status_code == 422


def test_generate_rejects_a_negative_or_oversized_seed_with_422(client: TestClient) -> None:
    basic_wardrobe(client)

    assert _generate(client, seed=-1).status_code == 422
    assert _generate(client, seed=2**32).status_code == 422
    assert _generate(client, seed=2**32 - 1).status_code == 200
    assert _generate(client, seed=0).status_code == 200


def _only_set(client: TestClient) -> list[str]:
    cat = Cat
    return [
        add_garment(client, cat.top),
        add_garment(client, cat.bottom),
        add_garment(client, cat.shoes),
    ]


def _log_directly(client: TestClient, outfit_id: str, day) -> None:
    from shared.models import WearLog

    with db(client) as session:
        session.add(WearLog(date=day, outfit_id=outfit_id))
        session.commit()


def test_the_wear_window_excludes_exactly_no_repeat_days_ago(client: TestClient) -> None:
    outfit = _persist(client, _only_set(client)).json()  # default no_repeat_days = 14
    _log_directly(client, outfit["id"], days_ago(14))

    assert len(_generate(client).json()["proposals"]) == 1  # 14 days ago is outside the window


def test_the_wear_window_includes_the_day_before_the_limit(client: TestClient) -> None:
    outfit = _persist(client, _only_set(client)).json()
    _log_directly(client, outfit["id"], days_ago(13))

    assert _generate(client).json()["proposals"] == []


def test_a_wear_log_in_the_future_never_blocks_a_set(client: TestClient) -> None:
    outfit = _persist(client, _only_set(client)).json()
    _log_directly(client, outfit["id"], days_ago(-1))  # tomorrow, written straight to the table

    assert len(_generate(client).json()["proposals"]) == 1


def test_an_embedding_blob_that_does_not_match_its_dimension_is_ignored(caplog) -> None:
    import logging

    import numpy as np

    from api.engine_inputs import _engine_garment

    good = np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes()

    def row(blob: bytes | None, dim: int | None) -> Garment:
        return Garment(
            img_original="x",
            category=Cat.top,
            embedding=blob,
            embedding_model="m",
            embedding_dim=dim,
        )

    assert _engine_garment(row(good, 3)).embedding == (1.0, 0.0, 0.0)
    with caplog.at_level(logging.WARNING, logger="api.engine_inputs"):
        assert _engine_garment(row(good, 4)).embedding is None  # wrong dimension
        assert _engine_garment(row(good + b"\x00", 3)).embedding is None  # not a multiple of 4
        assert _engine_garment(row(None, None)).embedding is None
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_the_history_window_matches_the_engine_rule_exactly(client: TestClient) -> None:
    """The engine ignores out-of-window entries anyway; the query must not even load them."""

    from api.engine_inputs import _history
    from shared.models import WearLog

    outfit = _persist(client, _only_set(client)).json()
    for offset in (-1, 0, 13, 14, 15):
        _log_directly(client, outfit["id"], days_ago(offset))

    today = days_ago(0)
    with db(client) as session:
        days = sorted((today - entry.day).days for entry in _history(session, today, 14))
        assert session.exec(select(WearLog)).all()

    assert days == [0, 13]
