"""Worker steps preprocess/cutout/color/consolidate, driven through the A3 runner
(ING-REQ-008/009/010..014/022, ING-SCN-003/005, D19) and an end-to-end run with the
upload API and a fake background remover (no real model is ever loaded)."""

from __future__ import annotations

import io
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from api.deps import get_engine
from api.main import create_app
from ml.background import EmptyCutoutError
from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStatus, JobStep
from shared.models import Garment, Job, Setting
from shared.schemas import Colors
from shared.settings import Settings
from worker.claim import claim_next_job
from worker.main import run
from worker.runner import PermanentStepError, StepContext, default_steps, run_job
from worker.steps.consolidate import consolidate_step
from worker.steps.preprocess import preprocess_step

NAVY = (20, 30, 80)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        worker_poll_interval_ms=5,
        thumb_px=32,
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


class FakeRemover:
    """Returns a known RGBA crop, raises EmptyCutoutError, or a generic error."""

    def __init__(self, *, mode: str = "ok", color: tuple[int, int, int] = NAVY) -> None:
        self.mode = mode
        self.color = color
        self.calls = 0

    def remove(self, img: Image.Image) -> Image.Image:
        self.calls += 1
        if self.mode == "empty":
            raise EmptyCutoutError(0.0)
        if self.mode == "error":
            raise RuntimeError("onnx exploded")
        return Image.new("RGBA", (40, 20), (*self.color, 255))


def _jpeg(size: tuple[int, int] = (60, 90), color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _add_garment_job(
    factory: sessionmaker[Session], settings: Settings, original: bytes | None = None
) -> tuple[str, str]:
    assert settings.images_root is not None
    with factory() as session:
        garment = Garment(img_original="")
        garment.img_original = f"original/{garment.id}.jpg"
        job = Job(garment_id=garment.id)
        session.add(garment)
        session.add(job)
        session.commit()
        ids = (garment.id, job.id)
    if original is not None:
        target = settings.images_root / f"original/{ids[0]}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
    return ids


def _run(factory, settings, remover: FakeRemover) -> JobStatus:
    with factory() as session:
        claimed = claim_next_job(session, "w-test")
    assert claimed is not None
    steps = default_steps(settings, remover_factory=lambda: remover)
    return run_job(claimed, steps, settings, factory)


def _garment(factory, garment_id: str) -> Garment:
    with factory() as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None
        return garment


def _job(factory, job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def _ctx(factory, settings, garment_id: str, **data) -> StepContext:
    return StepContext(
        job_id="j", garment_id=garment_id, settings=settings, session_factory=factory, data=data
    )


# --- preprocess ---------------------------------------------------------


def test_preprocess_puts_rgb_image_in_context(factory, settings) -> None:
    garment_id, _ = _add_garment_job(factory, settings, _jpeg((60, 90)))
    ctx = _ctx(factory, settings, garment_id)

    preprocess_step(ctx)

    assert ctx.data["image"].mode == "RGB"
    assert ctx.data["image"].size == (60, 90)


def test_preprocess_missing_original_is_permanent(factory, settings) -> None:
    garment_id, _ = _add_garment_job(factory, settings, None)

    with pytest.raises(PermanentStepError) as info:
        preprocess_step(_ctx(factory, settings, garment_id))

    assert "foto" in info.value.user_message


def test_preprocess_undecodable_original_fails_job_without_retry(factory, settings) -> None:
    garment_id, job_id = _add_garment_job(factory, settings, b"not an image")

    assert _run(factory, settings, FakeRemover()) == JobStatus.failed

    job = _job(factory, job_id)
    assert job.attempts == 0
    assert job.step == JobStep.preprocess
    assert job.error == "No se pudo leer la foto original. Súbela de nuevo."
    assert _garment(factory, garment_id).img_cutout is None


def test_preprocess_io_error_is_retried_once(factory, settings) -> None:
    assert settings.images_root is not None
    garment_id, job_id = _add_garment_job(factory, settings, None)
    # A directory where the file should be: reading it raises IsADirectoryError (OSError).
    (settings.images_root / f"original/{garment_id}.jpg").mkdir(parents=True)

    assert _run(factory, settings, FakeRemover()) == JobStatus.failed

    job = _job(factory, job_id)
    assert job.attempts == 1  # retried once (ING-REQ-022), then failed
    assert job.error == "No se pudo acceder a la foto. Inténtalo de nuevo."


# --- cutout -------------------------------------------------------------


def test_cutout_writes_files_and_relative_paths(factory, settings) -> None:
    assert settings.images_root is not None
    garment_id, job_id = _add_garment_job(factory, settings, _jpeg())
    remover = FakeRemover()

    assert _run(factory, settings, remover) == JobStatus.done

    garment = _garment(factory, garment_id)
    assert garment.img_cutout == f"cutout/{garment_id}.png"
    assert garment.img_thumb == f"thumb/{garment_id}.webp"
    cutout = Image.open(settings.images_root / garment.img_cutout)
    assert cutout.mode == "RGBA" and cutout.size == (40, 20)
    thumb = Image.open(settings.images_root / garment.img_thumb)
    assert thumb.format == "WEBP"
    assert max(thumb.size) == settings.thumb_px
    assert not list(settings.images_root.rglob("*.tmp"))
    assert _job(factory, job_id).progress == 100


def test_cutout_empty_mask_falls_back_to_full_image(factory, settings) -> None:
    assert settings.images_root is not None
    garment_id, job_id = _add_garment_job(factory, settings, _jpeg((60, 90)))
    captured: dict[str, object] = {}

    with factory() as session:
        claimed = claim_next_job(session, "w")
    assert claimed is not None
    steps = dict(default_steps(settings, remover_factory=lambda: FakeRemover(mode="empty")))
    real_consolidate = steps[JobStep.consolidate]

    def spy(ctx: StepContext) -> None:
        captured["flag"] = ctx.data.get("cutout_soft_failure")
        real_consolidate(ctx)

    steps[JobStep.consolidate] = spy

    assert run_job(claimed, steps, settings, factory) == JobStatus.done

    garment = _garment(factory, garment_id)
    cutout = Image.open(settings.images_root / f"cutout/{garment_id}.png")
    assert cutout.mode == "RGBA" and cutout.size == (60, 90)
    assert cutout.getchannel("A").getextrema() == (255, 255)  # fully opaque
    assert Image.open(settings.images_root / f"thumb/{garment_id}.webp").format == "WEBP"
    assert captured["flag"] is True
    assert garment.needs_review is True  # ING-SCN-005
    assert _job(factory, job_id).status == JobStatus.done


def test_cutout_generic_error_is_retried_then_fails(factory, settings) -> None:
    assert settings.images_root is not None
    garment_id, job_id = _add_garment_job(factory, settings, _jpeg())
    remover = FakeRemover(mode="error")

    assert _run(factory, settings, remover) == JobStatus.failed

    job = _job(factory, job_id)
    assert remover.calls == 2 and job.attempts == 1
    assert job.step == JobStep.cutout
    assert job.error == "No se pudo recortar la prenda. Inténtalo de nuevo."
    assert _garment(factory, garment_id).img_cutout is None
    assert not (settings.images_root / f"cutout/{garment_id}.png").exists()


def test_remover_is_built_lazily_and_only_once(factory, settings) -> None:
    built: list[FakeRemover] = []

    def build() -> FakeRemover:
        built.append(FakeRemover())
        return built[-1]

    steps = default_steps(settings, remover_factory=build)
    assert built == []  # nothing built at registry time

    for _ in range(2):
        _add_garment_job(factory, settings, _jpeg())
        with factory() as session:
            claimed = claim_next_job(session, "w")
        assert claimed is not None
        assert run_job(claimed, steps, settings, factory) == JobStatus.done
    assert len(built) == 1


def test_remover_factory_failure_is_retryable(factory, settings) -> None:
    _, job_id = _add_garment_job(factory, settings, _jpeg())
    calls = 0

    def broken() -> FakeRemover:
        nonlocal calls
        calls += 1
        raise RuntimeError("cannot load model")

    with factory() as session:
        claimed = claim_next_job(session, "w")
    assert claimed is not None
    steps = default_steps(settings, remover_factory=broken)

    assert run_job(claimed, steps, settings, factory) == JobStatus.failed
    assert calls == 2 and _job(factory, job_id).attempts == 1


# --- colour + consolidate through the pipeline --------------------------


def test_pipeline_stores_colours_and_leaves_needs_review_false(factory, settings) -> None:
    garment_id, _ = _add_garment_job(factory, settings, _jpeg())

    assert _run(factory, settings, FakeRemover(color=NAVY)) == JobStatus.done

    garment = _garment(factory, garment_id)
    colors = Colors.model_validate(garment.colors)
    assert [c.name for c in colors.root] == ["marino"]
    assert garment.is_neutral is True
    assert garment.color_confidence == pytest.approx(1.0)
    assert garment.needs_review is False


def _consolidate(factory, settings, garment_id: str, **data) -> bool:
    consolidate_step(_ctx(factory, settings, garment_id, **data))
    return _garment(factory, garment_id).needs_review


def _garment_with_confidence(factory, confidence: float | None, needs_review: bool = False) -> str:
    with factory() as session:
        garment = Garment(
            img_original="original/x.jpg", color_confidence=confidence, needs_review=needs_review
        )
        session.add(garment)
        session.commit()
        return garment.id


def test_consolidate_flags_low_colour_confidence_only(factory, settings) -> None:  # ING-SCN-003
    garment_id = _garment_with_confidence(factory, 0.5)
    assert _consolidate(factory, settings, garment_id) is True


def test_consolidate_flags_cutout_soft_failure(factory, settings) -> None:
    garment_id = _garment_with_confidence(factory, 0.95)
    assert _consolidate(factory, settings, garment_id, cutout_soft_failure=True) is True


def test_consolidate_leaves_clean_garment_unflagged(factory, settings) -> None:
    garment_id = _garment_with_confidence(factory, 0.95)
    assert _consolidate(factory, settings, garment_id, cutout_soft_failure=False) is False


def test_consolidate_never_clears_needs_review(factory, settings) -> None:  # D19 / DAT-REQ-018
    garment_id = _garment_with_confidence(factory, 0.99, needs_review=True)
    assert _consolidate(factory, settings, garment_id) is True


def test_consolidate_reads_threshold_from_setting_row(factory, settings) -> None:
    with factory() as session:
        session.add(Setting(id=1, color_review_threshold=0.3))
        session.commit()
    garment_id = _garment_with_confidence(factory, 0.5)
    assert _consolidate(factory, settings, garment_id) is False

    with factory() as session:
        row = session.get(Setting, 1)
        assert row is not None
        row.color_review_threshold = 0.9
        session.add(row)
        session.commit()
    assert _consolidate(factory, settings, garment_id) is True


def test_consolidate_treats_missing_confidence_as_review(factory, settings) -> None:
    garment_id = _garment_with_confidence(factory, None)
    assert _consolidate(factory, settings, garment_id) is True


# --- end to end: upload API -> worker loop -> GET /jobs -----------------


def _upload(client: TestClient, payload: bytes) -> dict[str, str]:
    response = client.post("/garments", files={"file": ("p.jpg", payload, "image/jpeg")})
    assert response.status_code == 202
    return response.json()


def _run_worker_until_done(client: TestClient, settings: Settings, remover, job_id: str) -> dict:
    engine = get_engine(client.app)  # type: ignore[arg-type]
    stop = threading.Event()
    steps = default_steps(settings, remover_factory=lambda: remover)
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            body = client.get(f"/jobs/{job_id}").json()
            if body["status"] in ("done", "failed"):
                return body
            time.sleep(0.02)
        raise AssertionError("worker did not finish the job in time")
    finally:
        stop.set()
        thread.join(timeout=5)


@pytest.fixture
def api_client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with TestClient(app) as client:
        yield client


def test_end_to_end_upload_worker_and_job_status(api_client, settings) -> None:
    assert settings.images_root is not None
    ids = _upload(api_client, _jpeg((80, 60)))

    job = _run_worker_until_done(api_client, settings, FakeRemover(color=NAVY), ids["job_id"])

    assert job == {
        "status": "done",
        "step": "consolidate",
        "progress": 100,
        "error": None,
        "result": None,
    }
    factory = create_session_factory(get_engine(api_client.app))  # type: ignore[arg-type]
    garment = _garment(factory, ids["garment_id"])
    assert (settings.images_root / (garment.img_cutout or "missing")).is_file()
    assert (settings.images_root / (garment.img_thumb or "missing")).is_file()
    assert [c["name"] for c in garment.colors or []] == ["marino"]
    assert garment.is_neutral is True
    assert garment.color_confidence == pytest.approx(1.0)
    assert garment.needs_review is False
    served = api_client.get(f"/images/{garment.img_cutout}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"


def test_end_to_end_soft_failure_marks_needs_review(api_client, settings) -> None:
    ids = _upload(api_client, _jpeg((80, 60), color=(240, 240, 240)))

    job = _run_worker_until_done(api_client, settings, FakeRemover(mode="empty"), ids["job_id"])

    assert job["status"] == "done" and job["progress"] == 100
    factory = create_session_factory(get_engine(api_client.app))  # type: ignore[arg-type]
    garment = _garment(factory, ids["garment_id"])
    assert garment.needs_review is True
    assert garment.img_cutout is not None and garment.colors
