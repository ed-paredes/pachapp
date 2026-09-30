"""Archive / reactivate / retry / delete (API-REQ-010..012, API-SCN-003/004)."""

from __future__ import annotations

import io
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, select

from api.deps import get_engine
from api.main import create_app
from shared.db import create_session_factory
from shared.enums import GarmentStatus, JobStatus, JobStep, OutfitSlot, OutfitSource
from shared.models import AiCorrection, Garment, Job, Outfit, OutfitItem
from shared.settings import Settings
from worker.main import run
from worker.runner import StepContext, default_steps
from worker.steps.color import color_step


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        ml_embed_revision="test-revision",
        worker_poll_interval_ms=5,
        thumb_px=32,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as test_client:
        yield test_client


def _db(client: TestClient) -> Session:
    return Session(get_engine(client.app), expire_on_commit=False)  # type: ignore[arg-type]


def _color(name: str) -> dict:
    return {"name": name, "hex": "#112233", "lab": [1.0, 2.0, 3.0], "proportion": 1.0}


def _seed(client: TestClient, **fields) -> str:
    fields.setdefault("img_original", "original/x.jpg")
    garment = Garment(**fields)
    with _db(client) as session:
        session.add(garment)
        session.commit()
    return garment.id


def _add_job(client: TestClient, garment_id: str, **fields) -> str:
    job = Job(garment_id=garment_id, **fields)
    with _db(client) as session:
        session.add(job)
        session.commit()
    return job.id


def _job(client: TestClient, job_id: str) -> Job:
    with _db(client) as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def _write(settings: Settings, relative: str, data: bytes = b"x") -> Path:
    assert settings.images_root is not None
    path = settings.images_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --- archive / reactivate -----------------------------------------------------


def test_archive_then_reactivate_returns_detail(client: TestClient) -> None:
    garment_id = _seed(client)

    archived = client.post(f"/garments/{garment_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived" and archived.json()["id"] == garment_id

    reactivated = client.post(f"/garments/{garment_id}/reactivate")
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    assert client.post(f"/garments/{garment_id}/reactivate").json()["status"] == "active"


def test_reactivate_takes_a_laundry_garment_to_active(client: TestClient) -> None:
    garment_id = _seed(client, status=GarmentStatus.laundry)

    assert client.post(f"/garments/{garment_id}/reactivate").json()["status"] == "active"


@pytest.mark.parametrize("action", ["archive", "reactivate", "retry"])
def test_unknown_garment_is_404(client: TestClient, action: str) -> None:
    response = client.post(f"/garments/missing/{action}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GARMENT_NOT_FOUND"


def test_delete_unknown_garment_is_404(client: TestClient) -> None:
    response = client.delete("/garments/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GARMENT_NOT_FOUND"


# --- retry ---------------------------------------------------------------------


def test_retry_resets_failed_job_to_pending(client: TestClient) -> None:
    garment_id = _seed(client)
    job_id = _add_job(
        client,
        garment_id,
        status=JobStatus.failed,
        step=JobStep.cutout,
        progress=30,
        attempts=1,
        error="No se pudo procesar la foto.",
        claimed_by="w",
    )

    response = client.post(f"/garments/{garment_id}/retry")

    assert response.status_code == 200
    assert response.json() == {
        "status": "pending",
        "step": None,
        "progress": 0,
        "error": None,
        "result": None,
    }
    job = _job(client, job_id)
    assert (job.status, job.attempts, job.step, job.progress) == (JobStatus.pending, 0, None, 0)
    assert job.error is None and job.claimed_by is None and job.claimed_at is None
    assert job.started_at is None and job.finished_at is None


def test_api_scn_004_retry_without_failed_job_is_409_and_changes_nothing(
    client: TestClient,
) -> None:
    garment_id = _seed(client)
    job_id = _add_job(client, garment_id, status=JobStatus.done, progress=100, attempts=1)

    response = client.post(f"/garments/{garment_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_FAILED"
    job = _job(client, job_id)
    assert (job.status, job.progress, job.attempts) == (JobStatus.done, 100, 1)


def test_retry_without_any_job_is_409(client: TestClient) -> None:
    garment_id = _seed(client)

    assert client.post(f"/garments/{garment_id}/retry").status_code == 409


def test_retry_only_considers_the_latest_job(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    garment_id = _seed(client)
    now = datetime.now(UTC)
    _add_job(client, garment_id, status=JobStatus.failed, created_at=now - timedelta(hours=1))
    latest = _add_job(client, garment_id, status=JobStatus.done, created_at=now)

    assert client.post(f"/garments/{garment_id}/retry").status_code == 409
    assert _job(client, latest).status == JobStatus.done


# --- worker colour guard --------------------------------------------------------


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (40, 20), (*color, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_color_step_keeps_user_corrected_colors(client: TestClient, settings: Settings) -> None:
    garment_id = _seed(
        client,
        img_cutout="cutout/c.png",
        colors=[_color("rojo")],
        is_neutral=False,
        color_confidence=1.0,
    )
    _write(settings, "cutout/c.png", _png((20, 30, 80)))
    with _db(client) as session:
        session.add(
            AiCorrection(
                garment_id=garment_id,
                field="colors",
                ai_value=[_color("marino")],
                corrected_value=[_color("rojo")],
            )
        )
        session.commit()
    factory = create_session_factory(get_engine(client.app))  # type: ignore[arg-type]

    color_step(
        StepContext(job_id="j", garment_id=garment_id, settings=settings, session_factory=factory)
    )

    with _db(client) as session:
        garment = session.get(Garment, garment_id)
    assert garment is not None
    assert garment.colors is not None and garment.colors[0]["name"] == "rojo"
    assert (garment.is_neutral, garment.color_confidence) == (False, 1.0)


def test_first_colour_edit_on_null_colours_survives_a_pipeline_rerun(
    client: TestClient, settings: Settings
) -> None:
    garment_id = _seed(client, img_cutout="cutout/c.png")  # colours are NULL
    _write(settings, "cutout/c.png", _png((20, 30, 80)))
    edited = client.patch(f"/garments/{garment_id}", json={"colors": [_color("rojo")]})
    assert edited.status_code == 200
    factory = create_session_factory(get_engine(client.app))  # type: ignore[arg-type]

    color_step(
        StepContext(job_id="j", garment_id=garment_id, settings=settings, session_factory=factory)
    )

    body = client.get(f"/garments/{garment_id}").json()
    assert body["colors"][0]["name"] == "rojo"  # not overwritten by the pipeline's "marino"
    assert (body["is_neutral"], body["color_confidence"]) == (False, 1.0)


def test_color_step_overwrites_pipeline_colors(client: TestClient, settings: Settings) -> None:
    garment_id = _seed(client, img_cutout="cutout/c.png", colors=[_color("rojo")], is_neutral=False)
    _write(settings, "cutout/c.png", _png((20, 30, 80)))
    factory = create_session_factory(get_engine(client.app))  # type: ignore[arg-type]

    color_step(
        StepContext(job_id="j", garment_id=garment_id, settings=settings, session_factory=factory)
    )

    with _db(client) as session:
        garment = session.get(Garment, garment_id)
    assert garment is not None and garment.colors is not None
    assert garment.colors[0]["name"] == "marino" and garment.is_neutral is True


class _FakeRemover:
    def remove(self, img: Image.Image) -> Image.Image:
        return Image.new("RGBA", (40, 20), (20, 30, 80, 255))


def test_retry_then_worker_run_preserves_user_corrected_colors(
    client: TestClient, settings: Settings
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 90), (200, 200, 200)).save(buffer, format="JPEG")
    garment_id = _seed(
        client,
        img_original="original/g.jpg",
        colors=[_color("rojo")],
        is_neutral=False,
        color_confidence=1.0,
    )
    _write(settings, "original/g.jpg", buffer.getvalue())
    job_id = _add_job(client, garment_id, status=JobStatus.failed, error="x", attempts=1)
    with _db(client) as session:
        session.add(
            AiCorrection(
                garment_id=garment_id,
                field="colors",
                ai_value=[_color("marino")],
                corrected_value=[_color("rojo")],
            )
        )
        session.commit()
    assert client.post(f"/garments/{garment_id}/retry").status_code == 200

    stop = threading.Event()
    steps = default_steps(settings, remover_factory=_FakeRemover)
    engine = get_engine(client.app)  # type: ignore[arg-type]
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if client.get(f"/jobs/{job_id}").json()["status"] in ("done", "failed"):
                break
            time.sleep(0.02)
    finally:
        stop.set()
        thread.join(timeout=5)

    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"
    body = client.get(f"/garments/{garment_id}").json()
    assert body["colors"][0]["name"] == "rojo"  # not overwritten by the pipeline's "marino"
    assert (body["is_neutral"], body["color_confidence"]) == (False, 1.0)
    assert body["img_cutout"] is not None and body["img_thumb"] is not None  # images were redone


# --- delete ----------------------------------------------------------------------


def test_delete_removes_rows_and_files(client: TestClient, settings: Settings) -> None:
    garment_id = _seed(
        client,
        img_original="original/d.jpg",
        img_cutout="cutout/d.png",
        img_thumb="thumb/d.webp",
    )
    _add_job(client, garment_id, status=JobStatus.done)
    with _db(client) as session:
        session.add(
            AiCorrection(
                garment_id=garment_id, field="category", ai_value="top", corrected_value="x"
            )
        )
        session.commit()
    paths = [
        _write(settings, "original/d.jpg"),
        _write(settings, "cutout/d.png"),
        _write(settings, "thumb/d.webp"),
    ]

    response = client.delete(f"/garments/{garment_id}")

    assert response.status_code == 204 and response.content == b""
    assert client.get(f"/garments/{garment_id}").status_code == 404
    with _db(client) as session:
        assert session.exec(select(Job).where(Job.garment_id == garment_id)).all() == []
        assert session.exec(select(AiCorrection)).all() == []
    assert not any(path.exists() for path in paths)


def test_delete_tolerates_missing_files(client: TestClient) -> None:
    garment_id = _seed(client, img_cutout="cutout/none.png")  # no files on disk

    assert client.delete(f"/garments/{garment_id}").status_code == 204


def test_api_scn_003_delete_with_outfit_history_is_409_and_keeps_everything(
    client: TestClient, settings: Settings
) -> None:
    garment_id = _seed(client, img_original="original/h.jpg")
    original = _write(settings, "original/h.jpg")
    with _db(client) as session:
        outfit = Outfit(source=OutfitSource.manual)
        session.add(outfit)
        session.flush()
        session.add(OutfitItem(outfit_id=outfit.id, garment_id=garment_id, slot=OutfitSlot.top))
        session.commit()

    response = client.delete(f"/garments/{garment_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GARMENT_HAS_HISTORY"
    assert client.get(f"/garments/{garment_id}").status_code == 200
    assert original.exists()


@pytest.mark.parametrize("job_status", [JobStatus.claimed, JobStatus.running])
def test_delete_while_processing_is_409(
    client: TestClient, settings: Settings, job_status: JobStatus
) -> None:
    garment_id = _seed(client, img_original="original/p.jpg")
    original = _write(settings, "original/p.jpg")
    job_id = _add_job(client, garment_id, status=job_status)

    response = client.delete(f"/garments/{garment_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GARMENT_PROCESSING"
    assert original.exists() and _job(client, job_id).status == job_status


def test_delete_pending_job_is_allowed(client: TestClient) -> None:
    garment_id = _seed(client)
    _add_job(client, garment_id, status=JobStatus.pending)

    assert client.delete(f"/garments/{garment_id}").status_code == 204


def test_delete_claimed_between_check_and_delete_is_409_and_keeps_everything(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.routers import garment_lifecycle

    garment_id = _seed(client, img_original="original/r.jpg")
    original = _write(settings, "original/r.jpg")
    job_id = _add_job(client, garment_id, status=JobStatus.pending)
    real_drop = garment_lifecycle._drop_pending_jobs

    def worker_claims_first(session: Session, target: str) -> None:
        with _db(client) as other:  # the worker wins the race just before the delete
            job = other.get(Job, job_id)
            assert job is not None
            job.status = JobStatus.claimed
            other.add(job)
            other.commit()
        real_drop(session, target)

    monkeypatch.setattr(garment_lifecycle, "_drop_pending_jobs", worker_claims_first)

    response = client.delete(f"/garments/{garment_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GARMENT_PROCESSING"
    assert client.get(f"/garments/{garment_id}").status_code == 200
    assert original.exists() and _job(client, job_id).status == JobStatus.claimed


def test_delete_on_a_busy_database_is_409_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import OperationalError

    from api.routers import garment_lifecycle

    garment_id = _seed(client)

    def busy(session: Session, target: str) -> None:
        raise OperationalError("DELETE", {}, Exception("database is locked"))

    monkeypatch.setattr(garment_lifecycle, "_drop_pending_jobs", busy)

    response = client.delete(f"/garments/{garment_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GARMENT_PROCESSING"
    assert client.get(f"/garments/{garment_id}").status_code == 200


def test_worker_treats_a_vanished_job_as_a_permanent_failure(
    client: TestClient, settings: Settings
) -> None:
    from worker.claim import ClaimedJob
    from worker.runner import run_job

    garment_id = _seed(client)
    factory = create_session_factory(get_engine(client.app))  # type: ignore[arg-type]
    gone = ClaimedJob(id="vanished-job", garment_id=garment_id, attempts=0)

    result = run_job(gone, default_steps(settings, remover_factory=_FakeRemover), settings, factory)

    assert result == JobStatus.failed
