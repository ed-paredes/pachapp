"""Worker side of the virtual try-on: claiming, recovery, `run_render` and the loop
(09-virtual-tryon.md §6.3, §12). No GPU: `FakeTryOnEngine` stands in for CatVTON."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from shared.db import create_db_engine, create_session_factory
from shared.enums import GarmentCategory, JobStatus, JobStep
from shared.models import MAX_RENDER_ATTEMPTS, Garment, Job, TryOnRender
from shared.settings import Settings
from tryon.engine import (
    TryOnBlankOutput,
    TryOnError,
    TryOnInvalidInput,
    TryOnParams,
    TryOnUnavailable,
)
from tryon.fake_engine import FakeTryOnEngine
from tryon.requests import find_or_create_render
from tryon.service import run_render
from worker.main import run
from worker.runner import STEP_ORDER, Step
from worker.tryon_claim import (
    claim_next_render,
    release_orphaned_render,
    requeue_stuck_renders,
)

SIZE = 64
RETRY_SIZE = 32
STEPS = 4
# Mask values tell the passes apart: the service must hand each pass its cloth type's mask.
MASK_VALUE = {"lower": 150, "upper": 200, "overall": 255}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    folder = tmp_path / "assets" / "mannequins" / "m1"
    folder.mkdir(parents=True)
    Image.new("RGB", (SIZE, SIZE), (200, 200, 200)).save(folder / "person.png")
    for kind, value in MASK_VALUE.items():
        Image.new("L", (SIZE, SIZE), value).save(folder / f"mask_{kind}.png")
    (folder / "meta.json").write_text(json.dumps({"id": "m1"}), encoding="utf-8")
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        worker_poll_interval_ms=5,
        tryon_enabled=True,
        tryon_assets_dir=tmp_path / "assets",
        tryon_mannequin_woman="m1",
        tryon_width=SIZE,
        tryon_height=SIZE,
        tryon_steps=STEPS,
        tryon_oom_retry_width=RETRY_SIZE,
        tryon_oom_retry_height=RETRY_SIZE,
    )


@pytest.fixture(autouse=True)
def _no_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never touch the GPU, even on a machine that has one."""
    monkeypatch.setattr("tryon.service._cuda_peak_reset", lambda: None)
    monkeypatch.setattr("tryon.service._cuda_peak_mb", lambda: None)


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = create_db_engine(settings)
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def _garment(
    factory: sessionmaker[Session], settings: Settings, category: GarmentCategory, colour: int
) -> str:
    assert settings.images_root is not None
    garment = Garment(img_original="original/x.jpg", category=category)
    garment.img_cutout = f"cutout/{garment.id}.png"
    path = settings.images_root / garment.img_cutout
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (colour, 0, 0, 255)).save(path)
    garment_id = garment.id
    with factory() as session:
        session.add(garment)
        session.commit()
    return garment_id


def _render(factory: sessionmaker[Session], settings: Settings, *garment_ids: str) -> str:
    """A pending render created the way the API does."""
    with factory() as session:
        outcome = find_or_create_render(
            session, settings, garment_ids=list(garment_ids), outfit_id=None, mannequin_id=None
        )
        return outcome.render.id


def _outfit_render(factory: sessionmaker[Session], settings: Settings) -> str:
    top = _garment(factory, settings, GarmentCategory.top, 255)
    bottom = _garment(factory, settings, GarmentCategory.bottom, 60)
    return _render(factory, settings, top, bottom)


def _get(factory: sessionmaker[Session], render_id: str) -> TryOnRender:
    with factory() as session:
        render = session.get(TryOnRender, render_id)
        assert render is not None
        return render


def _set(factory: sessionmaker[Session], render_id: str, **fields: object) -> None:
    with factory() as session:
        render = session.get(TryOnRender, render_id)
        assert render is not None
        for name, value in fields.items():
            setattr(render, name, value)
        session.add(render)
        session.commit()


def _add_renders(factory: sessionmaker[Session], n: int) -> list[str]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ids = []
    with factory() as session:
        for i in range(n):
            render = TryOnRender(
                cache_key=f"key-{i}", mannequin_id="m1", created_at=base + timedelta(seconds=i)
            )
            session.add(render)
            ids.append(render.id)
        session.commit()
    return ids


# --- claim and recovery -----------------------------------------------------


def test_claim_returns_none_when_empty(factory) -> None:
    with factory() as session:
        assert claim_next_render(session, "w1") is None


def test_claim_takes_oldest_pending_once_and_counts_the_attempt(factory) -> None:
    ids = _add_renders(factory, 3)
    with factory() as session:
        first = claim_next_render(session, "w1")
        second = claim_next_render(session, "w2")
    assert first is not None and first.id == ids[0] and first.attempts == 1
    assert second is not None and second.id == ids[1]  # never the same render twice
    render = _get(factory, ids[0])
    assert (render.status, render.claimed_by) == (JobStatus.claimed, "w1")
    assert render.claimed_at is not None
    assert _get(factory, ids[2]).status == JobStatus.pending


def test_claim_skips_renders_that_are_not_pending(factory) -> None:
    ids = _add_renders(factory, 3)
    _set(factory, ids[0], status=JobStatus.done)
    _set(factory, ids[1], status=JobStatus.failed)
    with factory() as session:
        claimed = claim_next_render(session, "w1")
    assert claimed is not None and claimed.id == ids[2]


def test_stuck_renders_are_requeued_or_failed_when_attempts_are_spent(factory) -> None:
    claimed, running, spent = _add_renders(factory, 3)
    _set(factory, claimed, status=JobStatus.claimed, attempts=1, claimed_by="dead")
    _set(factory, running, status=JobStatus.running, attempts=2, step="dressing_1", progress=40)
    _set(factory, spent, status=JobStatus.running, attempts=MAX_RENDER_ATTEMPTS)

    with factory() as session:
        assert requeue_stuck_renders(session) == 2

    for render_id in (claimed, running):
        render = _get(factory, render_id)
        assert (render.status, render.step, render.progress) == (JobStatus.pending, "queued", 0)
        assert render.claimed_by is None
    assert _get(factory, running).attempts == 2  # the claim already counted the attempt
    gone = _get(factory, spent)
    assert (gone.status, gone.error) == (JobStatus.failed, "interrupted")
    assert gone.finished_at is not None


def test_orphaned_render_is_requeued_then_failed(factory) -> None:
    (render_id,) = _add_renders(factory, 1)
    with factory() as session:
        claim_next_render(session, "w1")
        assert release_orphaned_render(session, render_id) == JobStatus.pending
        assert release_orphaned_render(session, render_id) is None  # already settled
        claim_next_render(session, "w1")  # a render that keeps failing runs out of attempts
        assert release_orphaned_render(session, render_id) == JobStatus.pending
        claim_next_render(session, "w1")
        assert _get(factory, render_id).attempts == MAX_RENDER_ATTEMPTS
        assert release_orphaned_render(session, render_id) == JobStatus.failed
        assert release_orphaned_render(session, "missing") is None


# --- run_render ---------------------------------------------------------------


class _RecordingEngine(FakeTryOnEngine):
    """Snapshots the row at every diffusion step and the inputs of every pass."""

    def __init__(self, factory: sessionmaker[Session], render_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.factory = factory
        self.render_id = render_id
        self.snapshots: list[tuple[str | None, int]] = []
        self.persons: list[tuple[int, ...]] = []
        self.masks: list[int] = []

    def dress(self, person, garment, mask, *, params, on_step=None, on_retry=None):
        self.persons.append(person.getpixel((0, 0)))
        self.masks.append(mask.getpixel((0, 0)))

        def snapshot() -> None:
            if on_step is not None:
                on_step()
            row = _get(self.factory, self.render_id)
            assert row.status == JobStatus.running
            self.snapshots.append((row.step, row.progress))

        return super().dress(
            person, garment, mask, params=params, on_step=snapshot, on_retry=on_retry
        )


class _Clock:
    """Advances one progress interval per read, so no progress write is throttled."""

    def __init__(self, step: float = 2.0) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def _run(settings, factory, render_id, fake, **kwargs) -> JobStatus:
    with factory() as session:
        claimed = claim_next_render(session, "w1")
    assert claimed is not None and claimed.id == render_id
    return run_render(render_id, settings, factory, fake, **kwargs)


def test_full_render_walks_the_steps_and_stores_the_webp(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = _RecordingEngine(factory, render_id)
    events = fake.load_events
    clock = _Clock()

    status = _run(
        settings,
        factory,
        render_id,
        fake,
        release_residents=lambda: events.append("release"),
        clock=clock,
    )

    assert status == JobStatus.done
    assert events == ["release", "load"]  # residents out before CatVTON loads
    # Lower garment first, then the upper one, each with its own mask from the base mannequin.
    assert fake.masks == [MASK_VALUE["lower"], MASK_VALUE["upper"]]
    # Pass 2 dresses the output of pass 1 (the lower garment's colour), not the mannequin.
    assert fake.persons[0] == (200, 200, 200)
    assert fake.persons[1] != (200, 200, 200)
    steps = [s for s, _ in fake.snapshots]
    assert steps == ["dressing_1"] * STEPS + ["dressing_2"] * STEPS  # no loading_model leaks
    progress = [p for _, p in fake.snapshots]
    assert progress == sorted(progress) and len(set(progress)) == len(progress)
    assert 5 < progress[0] < progress[-1] < 100
    row = _get(factory, render_id)
    assert (row.status, row.step, row.progress, row.error) == (JobStatus.done, "done", 100, None)
    assert row.img_path == f"tryon/{render_id}.webp"
    assert row.duration_ms is not None and row.duration_ms > 0
    assert row.peak_vram_mb is None  # no CUDA peak to report
    assert row.started_at is not None and row.finished_at is not None
    assert settings.images_root is not None
    with Image.open(settings.images_root / row.img_path) as webp:
        assert webp.format == "WEBP" and webp.size == (SIZE, SIZE)


def test_peak_vram_is_recorded_when_cuda_reports_it(settings, factory, monkeypatch) -> None:
    render_id = _outfit_render(factory, settings)
    monkeypatch.setattr("tryon.service._cuda_peak_mb", lambda: 2858)

    _run(settings, factory, render_id, FakeTryOnEngine())

    assert _get(factory, render_id).peak_vram_mb == 2858


def test_a_warm_engine_skips_the_loading_step_and_the_release(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = _RecordingEngine(factory, render_id)
    fake.loaded = True
    released: list[str] = []

    _run(settings, factory, render_id, fake, release_residents=lambda: released.append("x"))

    assert released == []  # CatVTON already holds the GPU
    assert fake.snapshots[0][0] == "dressing_1"


def test_progress_writes_are_throttled(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = _RecordingEngine(factory, render_id)

    _run(settings, factory, render_id, fake, clock=lambda: 0.0)  # time never passes

    # One write per pass (the step change); the other ticks of a pass are skipped.
    assert fake.snapshots == [("dressing_1", 16)] * STEPS + [("dressing_2", 51)] * STEPS


def test_oom_retries_smaller_and_still_succeeds(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = _RecordingEngine(factory, render_id, oom_calls=2)

    status = _run(settings, factory, render_id, fake, clock=_Clock())

    assert status == JobStatus.done
    assert fake.retries == 2  # one per pass
    row = _get(factory, render_id)
    assert settings.images_root is not None and row.img_path is not None
    with Image.open(settings.images_root / row.img_path) as webp:
        assert webp.size == (RETRY_SIZE, RETRY_SIZE)  # the size the last pass used


def test_progress_never_goes_back_on_an_oom_retry(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = _RecordingEngine(factory, render_id, oom_calls=2)
    seen: list[int] = []
    original = fake.dress

    def spy(*args, **kwargs):
        on_step = kwargs["on_step"]
        kwargs["on_step"] = lambda: (on_step(), seen.append(_get(factory, render_id).progress))
        return original(*args, **kwargs)

    fake.dress = spy  # type: ignore[method-assign]

    assert _run(settings, factory, render_id, fake, clock=_Clock()) == JobStatus.done

    assert fake.retries == 2
    assert seen == sorted(seen)
    assert fake.snapshots == sorted(fake.snapshots, key=lambda s: s[1])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("cloth_types"),
        lambda p: p.pop("width"),
        lambda p: p.pop("mannequin_version"),
        lambda p: p.update(cloth_types=["upper"]),  # two garments, one cloth type
        lambda p: p.update(cloth_types=["upper", "sleeves"]),  # no such mask
        lambda p: p.update(steps=0),
    ],
)
def test_malformed_params_fail_as_invalid_params(settings, factory, mutate) -> None:
    render_id = _outfit_render(factory, settings)
    with factory() as session:
        render = session.get(TryOnRender, render_id)
        assert render is not None
        params = dict(render.params)
        mutate(params)
        render.params = params
        session.add(render)
        session.commit()
    fake = FakeTryOnEngine()

    assert _run(settings, factory, render_id, fake) == JobStatus.failed

    row = _get(factory, render_id)
    assert (row.status, row.error) == (JobStatus.failed, "invalid_params")
    assert fake.calls == []


def test_oom_at_the_retry_size_fails_with_out_of_memory(settings, factory, monkeypatch) -> None:
    render_id = _outfit_render(factory, settings)
    fake = FakeTryOnEngine(oom_calls=1)
    fake.oom_at_retry_size = True

    logged: list[str] = []
    monkeypatch.setattr(
        "tryon.service.logger.error", lambda msg, *args: logged.append(msg % args)
    )  # not caplog: other tests reconfigure logging

    status = _run(settings, factory, render_id, fake)

    assert status == JobStatus.failed
    row = _get(factory, render_id)
    assert (row.status, row.error, row.img_path) == (JobStatus.failed, "out_of_memory", None)
    assert row.finished_at is not None
    assert "out of memory at 64x64 and 32x32" in logged[0]  # the original message is logged


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TryOnBlankOutput("flat"), "blank_output"),
        (TryOnInvalidInput("transparent"), "invalid_garment"),
        (TryOnUnavailable("no weights"), "engine_unavailable"),
        (TryOnError("other"), "engine_error"),
    ],
)
def test_engine_errors_fail_with_a_code(settings, factory, error: TryOnError, code: str) -> None:
    render_id = _outfit_render(factory, settings)

    assert _run(settings, factory, render_id, FakeTryOnEngine(error=error)) == JobStatus.failed

    row = _get(factory, render_id)
    assert (row.status, row.error) == (JobStatus.failed, code)


def _cutout_file(settings: Settings, factory: sessionmaker[Session], garment_id: str) -> Path:
    assert settings.images_root is not None
    with factory() as session:
        garment = session.get(Garment, garment_id)
        assert garment is not None and garment.img_cutout is not None
        return settings.images_root / garment.img_cutout


def test_missing_cutout_file_fails_cleanly(settings, factory) -> None:
    top = _garment(factory, settings, GarmentCategory.top, 255)
    render_id = _render(factory, settings, top)
    _cutout_file(settings, factory, top).unlink()
    fake = FakeTryOnEngine()

    assert _run(settings, factory, render_id, fake) == JobStatus.failed

    assert _get(factory, render_id).error == "garment_missing"
    assert fake.calls == []


def test_deleted_garment_fails_cleanly(settings, factory) -> None:
    top = _garment(factory, settings, GarmentCategory.top, 255)
    render_id = _render(factory, settings, top)
    with factory() as session:
        session.delete(session.get(Garment, top))
        session.commit()

    assert _run(settings, factory, render_id, FakeTryOnEngine()) == JobStatus.failed

    assert _get(factory, render_id).error == "garment_missing"


def test_cutout_changed_after_the_request_fails(settings, factory) -> None:
    top = _garment(factory, settings, GarmentCategory.top, 255)
    render_id = _render(factory, settings, top)
    Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(_cutout_file(settings, factory, top))

    assert _run(settings, factory, render_id, FakeTryOnEngine()) == JobStatus.failed

    assert _get(factory, render_id).error == "garment_changed"


def test_missing_mannequin_fails_cleanly(settings, factory, tmp_path: Path) -> None:
    render_id = _outfit_render(factory, settings)
    (settings.tryon_assets_dir / "mannequins" / "m1" / "person.png").unlink()

    assert _run(settings, factory, render_id, FakeTryOnEngine()) == JobStatus.failed

    assert _get(factory, render_id).error == "mannequin_unavailable"


def test_unexpected_errors_propagate_for_the_loop_to_requeue(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)

    class Broken(FakeTryOnEngine):
        def dress(self, *args, **kwargs):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        _run(settings, factory, render_id, Broken())

    assert _get(factory, render_id).status == JobStatus.running  # settled by the orphan release


def test_params_use_the_stored_render_parameters(settings, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = FakeTryOnEngine()

    _run(settings, factory, render_id, fake)

    assert fake.calls[0] == TryOnParams(
        width=SIZE,
        height=SIZE,
        steps=STEPS,
        guidance=settings.tryon_guidance,
        seed=settings.tryon_seed,
        oom_retry_width=RETRY_SIZE,
        oom_retry_height=RETRY_SIZE,
    )


# --- the worker loop -----------------------------------------------------------


def _wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the worker"
        time.sleep(0.01)


def _run_loop(settings, engine, steps, fake, done: Callable[[], bool]) -> None:
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine, fake))
    thread.start()
    try:
        _wait_for(done)
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


def _add_job(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        garment = Garment(img_original="original/j.jpg")
        session.add(garment)
        session.flush()
        job = Job(garment_id=garment.id)
        session.add(job)
        session.commit()
        return job.id


def test_loop_runs_a_pending_render(settings, engine, factory) -> None:
    render_id = _outfit_render(factory, settings)
    fake = FakeTryOnEngine()

    _run_loop(
        settings,
        engine,
        {step: (lambda _ctx: None) for step in STEP_ORDER},
        fake,
        lambda: _get(factory, render_id).status == JobStatus.done,
    )

    assert len(fake.calls) == 2


def test_uploads_go_before_renders(settings, engine, factory) -> None:
    render_id = _outfit_render(factory, settings)
    job_id = _add_job(factory)
    order: list[str] = []
    fake = FakeTryOnEngine()
    steps: dict[JobStep, Step] = {step: (lambda _ctx: None) for step in STEP_ORDER}
    steps[JobStep.preprocess] = lambda _ctx: order.append("job")
    real_dress = fake.dress

    def dress(*args, **kwargs):
        order.append("render")
        return real_dress(*args, **kwargs)

    fake.dress = dress  # ty: ignore[invalid-assignment]

    _run_loop(
        settings,
        engine,
        steps,
        fake,
        lambda: _get(factory, render_id).status == JobStatus.done,
    )

    assert order[0] == "job"
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.status == JobStatus.done


def test_a_loaded_engine_is_unloaded_before_an_upload_runs(settings, engine, factory) -> None:
    fake = FakeTryOnEngine()
    fake.loaded = True
    job_id = _add_job(factory)
    seen: list[bool] = []
    steps: dict[JobStep, Step] = {step: (lambda _ctx: None) for step in STEP_ORDER}
    steps[JobStep.preprocess] = lambda _ctx: seen.append(fake.loaded)

    _run_loop(
        settings,
        engine,
        steps,
        fake,
        lambda: _get_job(factory, job_id).status == JobStatus.done,
    )

    assert seen == [False]
    assert fake.unloads == 1


def _get_job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def test_renders_are_left_alone_when_tryon_is_disabled(settings, engine, factory) -> None:
    render_id = _outfit_render(factory, settings)
    disabled = settings.model_copy(update={"tryon_enabled": False})
    fake = FakeTryOnEngine()
    job_id = _add_job(factory)  # a processed job proves the loop ran

    _run_loop(
        disabled,
        engine,
        {step: (lambda _ctx: None) for step in STEP_ORDER},
        fake,
        lambda: _get_job(factory, job_id).status == JobStatus.done,
    )
    time.sleep(0.05)

    assert _get(factory, render_id).status == JobStatus.pending
    assert fake.calls == []


def test_idle_iterations_poll_unload_if_idle(settings, engine, factory) -> None:
    fake = FakeTryOnEngine()
    polled = threading.Event()
    real = fake.unload_if_idle

    def unload_if_idle() -> bool:
        polled.set()
        return real()

    fake.unload_if_idle = unload_if_idle  # ty: ignore[invalid-assignment]

    _run_loop(
        settings, engine, {step: (lambda _ctx: None) for step in STEP_ORDER}, fake, polled.is_set
    )


def test_idle_loop_removes_stale_renders_and_their_files(settings, engine, factory) -> None:
    old = datetime.now(UTC) - timedelta(days=settings.tryon_cache_max_age_days + 1)
    stale = _outfit_render(factory, settings)
    _set(
        factory, stale, status=JobStatus.done, img_path=f"tryon/{stale}.webp", last_accessed_at=old
    )
    assert settings.images_root is not None
    image = settings.images_root / f"tryon/{stale}.webp"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"webp")

    def gone() -> bool:
        with factory() as session:
            return session.get(TryOnRender, stale) is None

    _run_loop(
        settings,
        engine,
        {step: (lambda _ctx: None) for step in STEP_ORDER},
        FakeTryOnEngine(),
        gone,
    )

    assert not image.exists()


def test_stuck_renders_are_recovered_at_start(settings, engine, factory) -> None:
    render_id = _outfit_render(factory, settings)
    _set(factory, render_id, status=JobStatus.running, attempts=1, step="dressing_1")

    _run_loop(
        settings,
        engine,
        {step: (lambda _ctx: None) for step in STEP_ORDER},
        FakeTryOnEngine(),
        lambda: _get(factory, render_id).status == JobStatus.done,
    )

    assert _get(factory, render_id).attempts == 2


def test_an_unexpected_render_error_requeues_then_fails(settings, engine, factory) -> None:
    render_id = _outfit_render(factory, settings)

    class Broken(FakeTryOnEngine):
        def dress(self, *args, **kwargs):
            raise RuntimeError("boom")

    _run_loop(
        settings,
        engine,
        {step: (lambda _ctx: None) for step in STEP_ORDER},
        Broken(),
        lambda: _get(factory, render_id).status == JobStatus.failed,
    )

    row = _get(factory, render_id)
    assert (row.attempts, row.error) == (MAX_RENDER_ATTEMPTS, "interrupted")
