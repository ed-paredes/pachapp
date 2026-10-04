"""Worker claim + step runner (DAT-REQ-009/010, ING-REQ-004/005/006/022/025, ING-SCN-006)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStatus, JobStep
from shared.models import Garment, Job
from shared.settings import Settings
from worker.claim import claim_next_job, release_orphaned_job, requeue_stuck_jobs
from worker.main import run
from worker.runner import (
    STEP_ORDER,
    STEP_PROGRESS,
    PermanentStepError,
    RetryableStepError,
    Step,
    StepContext,
    default_steps,
    run_job,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        ml_embed_revision="test-revision",
        worker_poll_interval_ms=5,
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


def _add_jobs(factory: sessionmaker[Session], n: int, **job_kwargs) -> list[str]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ids: list[str] = []
    with factory() as session:
        for i in range(n):
            garment = Garment(img_original=f"original/{i}.jpg")
            session.add(garment)
            session.flush()
            job = Job(garment_id=garment.id, created_at=base + timedelta(seconds=i), **job_kwargs)
            session.add(job)
            ids.append(job.id)
        session.commit()
    return ids


def _job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def _noop_steps() -> dict[JobStep, Step]:
    return {step: (lambda _ctx: None) for step in STEP_ORDER}


def _run(factory, settings, job_id: str, steps: dict[JobStep, Step]) -> JobStatus:
    with factory() as session:
        claimed = claim_next_job(session, "w-test")
    assert claimed is not None and claimed.id == job_id
    return run_job(claimed, steps, settings, factory)


# --- claim ---------------------------------------------------------------


def test_claim_returns_none_when_empty(factory) -> None:
    with factory() as session:
        assert claim_next_job(session, "w1") is None


def test_claim_takes_oldest_pending_and_marks_claimed(factory) -> None:
    ids = _add_jobs(factory, 3)
    with factory() as session:
        claimed = claim_next_job(session, "w1")
    assert claimed is not None and claimed.id == ids[0]
    job = _job(factory, ids[0])
    assert job.status == JobStatus.claimed
    assert job.claimed_by == "w1"
    assert job.claimed_at is not None
    assert _job(factory, ids[1]).status == JobStatus.pending


def test_claim_skips_non_pending(factory) -> None:
    ids = _add_jobs(factory, 2)
    with factory() as session:
        first = claim_next_job(session, "w1")
        second = claim_next_job(session, "w1")
        third = claim_next_job(session, "w1")
    assert first is not None and second is not None
    assert [first.id, second.id] == ids
    assert third is None


def test_concurrent_claims_never_double_claim(factory) -> None:
    """ING-SCN-006: racing workers each claim a distinct job."""
    n_jobs = 24
    ids = _add_jobs(factory, n_jobs)
    claimed_ids: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def worker(name: str) -> None:
        barrier.wait()
        while True:
            with factory() as session:
                claimed = claim_next_job(session, name)
            if claimed is None:
                return
            with lock:
                claimed_ids.append(claimed.id)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(claimed_ids) == sorted(ids)
    assert len(set(claimed_ids)) == n_jobs


# --- stuck-job recovery -----------------------------------------------------


def test_requeue_stuck_jobs(factory) -> None:
    ids = _add_jobs(factory, 4)
    with factory() as session:
        claim_next_job(session, "old-worker")  # -> claimed
    with factory() as session:
        running = session.get(Job, ids[1])
        assert running is not None
        running.status = JobStatus.running
        running.step = JobStep.cutout
        running.progress = 30
        running.started_at = datetime.now(UTC)
        session.add(running)
        done = session.get(Job, ids[2])
        assert done is not None
        done.status = JobStatus.done
        session.add(done)
        session.commit()

    with factory() as session:
        assert requeue_stuck_jobs(session) == 2

    for job_id in ids[:2]:
        job = _job(factory, job_id)
        assert job.status == JobStatus.pending
        assert job.step is None and job.progress == 0
        assert job.claimed_by is None and job.started_at is None
    assert _job(factory, ids[2]).status == JobStatus.done
    assert _job(factory, ids[3]).status == JobStatus.pending
    assert [_job(factory, job_id).attempts for job_id in ids] == [1, 1, 0, 0]


def test_requeue_consumes_retry_budget_and_fails_poison_job(factory, caplog, monkeypatch) -> None:
    (job_id,) = _add_jobs(factory, 1, status=JobStatus.running, claimed_by="w1")
    # Earlier tests (alembic's fileConfig) can leave app loggers disabled.
    claim_logger = logging.getLogger("worker.claim")
    monkeypatch.setattr(claim_logger, "disabled", False)
    monkeypatch.setattr(claim_logger, "propagate", True)

    with caplog.at_level("INFO", logger="worker.claim"):
        with factory() as session:
            assert requeue_stuck_jobs(session) == 1
        assert _job(factory, job_id).status == JobStatus.pending
        assert _job(factory, job_id).attempts == 1
        assert "1 requeued, 0 failed" in caplog.text

        with factory() as session:  # the worker died again while running it
            claim_next_job(session, "w2")
        with factory() as session:
            assert requeue_stuck_jobs(session) == 0
        assert "0 requeued, 1 failed" in caplog.text

    job = _job(factory, job_id)
    assert job.status == JobStatus.failed
    assert job.error is not None and job.error.startswith("El procesamiento se interrumpió")
    assert job.finished_at is not None
    with factory() as session:
        assert claim_next_job(session, "w3") is None


# --- runner ---------------------------------------------------------------------


def test_pipeline_success_lifecycle_and_progress_table(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    seen: list[tuple[JobStep, JobStatus, JobStep | None, int]] = []

    def make(step: JobStep) -> Step:
        def fake(ctx: StepContext) -> None:
            # ING-REQ-004: step is already written when the step starts, and no
            # transaction is held open (we can read and even write the row).
            job = _job(ctx.session_factory, ctx.job_id)
            seen.append((step, job.status, job.step, job.progress))

        return fake

    steps = {step: make(step) for step in STEP_ORDER}
    assert _run(factory, settings, job_id, steps) == JobStatus.done

    assert [s[0] for s in seen] == list(STEP_ORDER)
    previous = 0
    for step, status, written_step, progress in seen:
        assert status == JobStatus.running
        assert written_step == step
        assert progress == previous  # progress of the step before it
        previous = STEP_PROGRESS[step]
    assert list(STEP_PROGRESS.values()) == [10, 30, 45, 75, 90, 100]

    job = _job(factory, job_id)
    assert job.status == JobStatus.done
    assert job.progress == 100
    assert job.error is None
    assert job.started_at is not None and job.finished_at is not None
    assert job.attempts == 0


def test_progress_is_monotonic_and_matches_table(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    progress: list[int] = []

    def probe(ctx: StepContext) -> None:
        progress.append(_job(ctx.session_factory, ctx.job_id).progress)

    steps = {step: probe for step in STEP_ORDER}
    _run(factory, settings, job_id, steps)
    assert progress == [0, 10, 30, 45, 75, 90]


def test_steps_share_context_data_bag(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    steps = _noop_steps()

    def cutout(ctx: StepContext) -> None:
        ctx.data["cutout_soft_failure"] = True

    def consolidate(ctx: StepContext) -> None:
        assert ctx.data["cutout_soft_failure"] is True

    steps[JobStep.cutout] = cutout
    steps[JobStep.consolidate] = consolidate
    assert _run(factory, settings, job_id, steps) == JobStatus.done


def test_default_steps_register_real_steps_and_defer_embedding(settings) -> None:
    from worker.runner import deferred_step

    steps = default_steps(settings, remover_factory=lambda: None)  # type: ignore[arg-type]

    assert list(steps) == list(STEP_ORDER)
    assert steps[JobStep.embedding] is deferred_step
    for real in (
        JobStep.preprocess,
        JobStep.cutout,
        JobStep.color,
        JobStep.ai_attributes,
        JobStep.consolidate,
    ):
        assert steps[real] is not deferred_step


def test_retryable_error_is_retried_once_then_succeeds(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    calls: list[JobStep] = []
    steps = _noop_steps()

    def flaky(ctx: StepContext) -> None:
        calls.append(JobStep.cutout)
        if len(calls) == 1:
            raise RetryableStepError("io hiccup")

    steps[JobStep.cutout] = flaky
    assert _run(factory, settings, job_id, steps) == JobStatus.done
    assert len(calls) == 2
    job = _job(factory, job_id)
    assert job.attempts == 1
    assert job.status == JobStatus.done


def test_retryable_error_twice_fails_with_spanish_error(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    calls = 0
    steps = _noop_steps()

    def always(ctx: StepContext) -> None:
        nonlocal calls
        calls += 1
        raise RetryableStepError("disk full", user_message="No se pudo guardar la imagen.")

    steps[JobStep.cutout] = always
    assert _run(factory, settings, job_id, steps) == JobStatus.failed
    assert calls == 2
    job = _job(factory, job_id)
    assert job.status == JobStatus.failed
    assert job.error == "No se pudo guardar la imagen."
    assert job.step == JobStep.cutout
    assert job.progress == STEP_PROGRESS[JobStep.preprocess]
    assert job.finished_at is not None


def test_unexpected_exception_is_treated_as_retryable(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    calls = 0
    steps = _noop_steps()

    def boom(ctx: StepContext) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("secret internal detail")

    steps[JobStep.color] = boom
    assert _run(factory, settings, job_id, steps) == JobStatus.failed
    assert calls == 2
    job = _job(factory, job_id)
    assert job.error is not None and "secret" not in job.error
    assert job.error.startswith("No se pudo")


def test_permanent_error_fails_immediately(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    calls = 0
    steps = _noop_steps()

    def undecodable(ctx: StepContext) -> None:
        nonlocal calls
        calls += 1
        raise PermanentStepError("cannot decode", user_message="La imagen no es válida.")

    steps[JobStep.preprocess] = undecodable
    assert _run(factory, settings, job_id, steps) == JobStatus.failed
    assert calls == 1
    job = _job(factory, job_id)
    assert job.error == "La imagen no es válida."
    assert job.attempts == 0
    assert job.progress == 0


def test_retry_budget_is_per_job_not_per_step(factory, settings) -> None:
    (job_id,) = _add_jobs(factory, 1)
    seen: dict[JobStep, int] = {}
    steps = _noop_steps()

    def flaky(step: JobStep) -> Callable[[StepContext], None]:
        def fn(ctx: StepContext) -> None:
            seen[step] = seen.get(step, 0) + 1
            if seen[step] == 1:
                raise RetryableStepError("transient")

        return fn

    steps[JobStep.preprocess] = flaky(JobStep.preprocess)
    steps[JobStep.cutout] = flaky(JobStep.cutout)
    assert _run(factory, settings, job_id, steps) == JobStatus.failed
    assert seen == {JobStep.preprocess: 2, JobStep.cutout: 1}
    assert _job(factory, job_id).attempts == 1


# --- run loop -----------------------------------------------------------------------


def test_run_loop_processes_pending_jobs_then_stops(engine, factory, settings) -> None:
    ids = _add_jobs(factory, 3)
    stop = threading.Event()
    order: list[str] = []
    steps = _noop_steps()

    def consolidate(ctx: StepContext) -> None:
        order.append(ctx.job_id)
        if len(order) == 3:
            stop.set()

    steps[JobStep.consolidate] = consolidate
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine))
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert order == ids
    for job_id in ids:
        assert _job(factory, job_id).status == JobStatus.done


def test_run_loop_requeues_stuck_jobs_at_start_and_picks_up_new_ones(
    engine, factory, settings
) -> None:
    (stuck_id,) = _add_jobs(factory, 1, status=JobStatus.running, claimed_by="dead-worker")
    stop = threading.Event()
    done: list[str] = []
    steps = _noop_steps()

    def consolidate(ctx: StepContext) -> None:
        done.append(ctx.job_id)
        if len(done) == 2:
            stop.set()

    steps[JobStep.consolidate] = consolidate
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine))
    thread.start()
    (late_id,) = _add_jobs(factory, 1)  # arrives while the worker is idle/polling
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert set(done) == {stuck_id, late_id}
    assert all(j.status == JobStatus.done for j in _all_jobs(factory))


def _all_jobs(factory) -> list[Job]:
    with factory() as session:
        return list(session.exec(select(Job)).all())


# --- orphaned jobs (run_job raised after the claim) ---------------------------------


def _run_loop_until(engine, settings, steps, done: Callable[[], bool]) -> None:
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(stop, settings, steps, engine))
    thread.start()
    deadline = time.monotonic() + 10
    while not done() and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_bookkeeping_error_requeues_orphan_and_job_then_completes(
    engine, factory, settings, monkeypatch
) -> None:
    """A bookkeeping write fails once ("database is locked"): the job must not
    stay claimed/running; it goes back to pending (budget left) and finishes."""
    from sqlalchemy.exc import OperationalError

    from worker import runner

    (job_id,) = _add_jobs(factory, 1)
    real_mark_done = runner._mark_done
    calls = {"n": 0}

    def flaky_mark_done(*args, **kwargs) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("UPDATE job", {}, Exception("database is locked"))
        real_mark_done(*args, **kwargs)

    monkeypatch.setattr(runner, "_mark_done", flaky_mark_done)
    monkeypatch.setattr("worker.main.ORPHAN_RELEASE_BACKOFF_S", (0.0, 0.0))

    _run_loop_until(
        engine, settings, _noop_steps(), lambda: _job(factory, job_id).status == JobStatus.done
    )

    job = _job(factory, job_id)
    assert job.status == JobStatus.done
    assert job.attempts == 1  # the orphan release consumed the retry budget


def test_orphan_with_spent_budget_is_failed_in_spanish(
    engine, factory, settings, monkeypatch
) -> None:
    (job_id,) = _add_jobs(factory, 1, attempts=1)

    def boom(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr("worker.main.run_job", boom)
    monkeypatch.setattr("worker.main.ORPHAN_RELEASE_BACKOFF_S", (0.0,))

    _run_loop_until(
        engine, settings, _noop_steps(), lambda: _job(factory, job_id).status == JobStatus.failed
    )

    job = _job(factory, job_id)
    assert job.status == JobStatus.failed
    assert job.error is not None and "interrumpió" in job.error


def test_orphan_release_is_retried_with_backoff(engine, factory, settings, monkeypatch) -> None:
    (job_id,) = _add_jobs(factory, 1, attempts=1)
    real_release = release_orphaned_job
    calls = {"n": 0}

    def flaky_release(session, jid):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("database is locked")
        return real_release(session, jid)

    monkeypatch.setattr("worker.main.run_job", lambda *a, **k: 1 / 0)
    monkeypatch.setattr("worker.main.release_orphaned_job", flaky_release)
    monkeypatch.setattr("worker.main.ORPHAN_RELEASE_BACKOFF_S", (0.0, 0.0, 0.0, 0.0))

    _run_loop_until(
        engine, settings, _noop_steps(), lambda: _job(factory, job_id).status == JobStatus.failed
    )

    assert calls["n"] == 3
    assert _job(factory, job_id).status == JobStatus.failed


def test_release_orphaned_job_ignores_settled_jobs(factory) -> None:
    (job_id,) = _add_jobs(factory, 1, status=JobStatus.done)
    with factory() as session:
        assert release_orphaned_job(session, job_id) is None
        assert release_orphaned_job(session, "missing") is None
    assert _job(factory, job_id).status == JobStatus.done
