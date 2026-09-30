"""POST /garments, GET /jobs/{id} and /images (ING-REQ-001..003/008/009/026,
API-REQ-013/016/017)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, select

from api.deps import get_engine
from api.main import create_app
from shared.enums import GarmentStatus, JobStatus
from shared.models import Garment, Job
from shared.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        upload_max_px=100,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as test_client:
        yield test_client


def _session(client: TestClient) -> Session:
    return Session(get_engine(client.app))  # type: ignore[arg-type]


def _jpeg(size: tuple[int, int], *, orientation: int | None = None) -> bytes:
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _upload(client: TestClient, payload: bytes, name: str = "photo.jpg"):
    return client.post("/garments", files={"file": (name, payload, "image/jpeg")})


def test_upload_creates_garment_job_and_original(client: TestClient, settings: Settings) -> None:
    response = _upload(client, _jpeg((60, 30), orientation=6))

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"garment_id", "job_id"}
    with _session(client) as session:
        garment = session.get(Garment, body["garment_id"])
        job = session.get(Job, body["job_id"])
        assert garment is not None and job is not None
        assert garment.status == GarmentStatus.active
        assert garment.img_original == f"original/{garment.id}.jpg"
        assert garment.img_cutout is None and garment.img_thumb is None
        assert garment.category is None and garment.colors is None
        assert job.status == JobStatus.pending
        assert job.garment_id == garment.id
    assert settings.images_root is not None
    stored = Image.open(settings.images_root / garment.img_original)
    assert stored.format == "JPEG"
    assert stored.size == (30, 60)  # EXIF-corrected (ING-REQ-003)


def test_upload_corrupt_image_returns_400_envelope(client: TestClient) -> None:
    response = _upload(client, b"definitely not an image")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_IMAGE"
    assert error["details"] is None
    with _session(client) as session:
        assert session.exec(select(Garment)).all() == []


def test_upload_oversized_image_returns_400(client: TestClient, settings: Settings) -> None:
    response = _upload(client, _jpeg((201, 10)))  # cap is 2 * upload_max_px = 200

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"
    assert settings.images_root is not None
    assert not list(settings.images_root.rglob("*.jpg"))


def test_upload_accepts_exactly_the_hard_cap(client: TestClient) -> None:
    assert _upload(client, _jpeg((200, 10))).status_code == 202


def test_upload_without_file_field_is_422(client: TestClient) -> None:
    response = client.post("/garments", files={"other": ("a.jpg", _jpeg((10, 10)), "image/jpeg")})

    assert response.status_code == 422
    assert "detail" in response.json()


def test_db_failure_removes_written_original(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: Session, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(Session, "commit", fail)
    failing = TestClient(client.app, raise_server_exceptions=False)

    response = _upload(failing, _jpeg((20, 20)))

    assert response.status_code == 500
    assert settings.images_root is not None
    assert not list(settings.images_root.rglob("*.jpg"))


def test_get_job_returns_status_fields(client: TestClient) -> None:
    job_id = _upload(client, _jpeg((20, 20))).json()["job_id"]

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "pending",
        "step": None,
        "progress": 0,
        "error": None,
        "result": None,
    }


def test_get_job_unknown_id_is_404_envelope(client: TestClient) -> None:
    response = client.get("/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_images_are_served_statically(client: TestClient) -> None:
    garment_id = _upload(client, _jpeg((20, 20))).json()["garment_id"]

    response = client.get(f"/images/original/{garment_id}.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(response.content)).size == (20, 20)


def test_webp_thumbnails_are_served_as_image_webp(client: TestClient, settings: Settings) -> None:
    assert settings.images_root is not None
    thumb = settings.images_root / "thumb" / "t.webp"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4)).save(thumb, format="WEBP")

    response = client.get("/images/thumb/t.webp")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"


def test_images_root_is_created_at_startup(settings: Settings) -> None:
    assert settings.images_root is not None
    assert not settings.images_root.exists()

    with TestClient(create_app(settings)) as test_client:
        assert settings.images_root.is_dir()
        assert test_client.get("/health").status_code == 200


def test_openapi_declares_response_models(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()

    post = spec["paths"]["/garments"]["post"]
    assert "202" in post["responses"]
    assert post["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GarmentCreated"
    }
    assert "JobRead" in spec["components"]["schemas"]


def test_upload_over_byte_cap_returns_400_before_decoding(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3-002: the byte cap is enforced while reading, before any decode.

    The cap bounds the handler's in-memory copy of the body only: Starlette has
    already spooled the multipart upload (network and temp disk) before the
    handler runs, so this does not test that reading stops early on the wire."""
    from api.routers import garments as garments_router

    monkeypatch.setattr(garments_router, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(garments_router, "_READ_CHUNK_BYTES", 256)

    response = _upload(client, b"\x00" * 2048)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "IMAGE_TOO_LARGE"
    assert error["details"] == {"max_bytes": 1024}
    assert settings.images_root is not None
    assert not list(settings.images_root.rglob("*.jpg"))


def test_upload_at_byte_cap_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.routers import garments as garments_router

    payload = _jpeg((20, 20))
    monkeypatch.setattr(garments_router, "MAX_UPLOAD_BYTES", len(payload))

    assert _upload(client, payload).status_code == 202


def test_upload_handler_is_a_sync_def() -> None:
    """R3-001: a plain `def` runs in the threadpool, not on the event loop."""
    import inspect

    from api.routers import garments as garments_router

    assert not inspect.iscoroutinefunction(garments_router.upload_garment)


def test_get_engine_is_created_once_under_concurrency(settings: Settings) -> None:
    """R3-003: racing first requests share a single engine."""
    from concurrent.futures import ThreadPoolExecutor

    app = create_app(settings)
    with ThreadPoolExecutor(max_workers=8) as pool:
        engines = list(pool.map(lambda _: get_engine(app), range(32)))

    assert len({id(engine) for engine in engines}) == 1
    engines[0].dispose()
