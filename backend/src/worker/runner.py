"""Step pipeline for one claimed job (03-garment-ingestion.md).

Fixed order `preprocess -> cutout -> color -> ai_attributes -> embedding ->
consolidate` (ING-REQ-006) with the progress table of ING-REQ-025. `job.step`
is written at the START of each step (ING-REQ-004), each in its own short
transaction; a step runs with no transaction open.

Steps are plain callables `(StepContext) -> None` injected as an ordered
mapping, so tests use fakes and A4/A5 plug in the real ones through
`default_steps`. Error policy (ING-REQ-005/022): a `RetryableStepError` (or any
unexpected exception) is retried once per job, then the job is `failed`; a
`PermanentStepError` fails the job immediately. `job.error` is a short Spanish
message; details go to the log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from shared.enums import JobStatus, JobStep
from shared.models import Job
from shared.settings import Settings
from worker.claim import MAX_RETRIES, ClaimedJob

logger = logging.getLogger(__name__)

# ING-REQ-025 (default values, adjustable).
STEP_PROGRESS: dict[JobStep, int] = {
    JobStep.preprocess: 10,
    JobStep.cutout: 30,
    JobStep.color: 45,
    JobStep.ai_attributes: 75,
    JobStep.embedding: 90,
    JobStep.consolidate: 100,
}
STEP_ORDER: tuple[JobStep, ...] = tuple(STEP_PROGRESS)

DEFAULT_ERROR = "No se pudo procesar la foto. Inténtalo de nuevo."


class StepError(Exception):
    """Base for step failures. `user_message` (Spanish) becomes `job.error`."""

    def __init__(self, message: str, *, user_message: str = DEFAULT_ERROR) -> None:
        super().__init__(message)
        self.user_message = user_message


class RetryableStepError(StepError):
    """Transient failure (I/O, model): the step is retried once."""


class PermanentStepError(StepError):
    """Unrecoverable failure (e.g. undecodable original): fail without retry."""


@dataclass
class StepContext:
    """What a step receives. `data` is a per-job bag for cross-step values
    (e.g. `cutout_soft_failure`, loaded images); it is discarded with the job."""

    job_id: str
    garment_id: str
    settings: Settings
    session_factory: sessionmaker[Session]
    data: dict[str, Any] = field(default_factory=dict)


Step = Callable[[StepContext], None]


def deferred_step(_ctx: StepContext) -> None:
    """No-op placeholder for a step without an implementation yet: progress
    still advances so the table stays monotonic."""


def default_steps(
    settings: Settings,
    remover_factory: Callable[[], Any] | None = None,
    models_factory: Callable[[], Any] | None = None,
    parser_factory: Callable[[], Any] | None = None,
) -> Mapping[JobStep, Step]:
    """Production step registry. `remover_factory` builds the `BackgroundRemover`
    and `models_factory` the embedder + zero-shot classifier (`worker.ai.AiModels`),
    both lazily on the first job; `parser_factory` builds the garment parser (FASHN)
    used by the cutout step when `ml_garment_parse` is on. Tests inject fakes, production
    uses BiRefNet, FASHN and SigLIP."""
    # Imported here: the step modules import this module for errors/StepContext.
    from worker.ai import LazyModels, production_models_factory
    from worker.steps.ai_attributes import make_ai_attributes_step
    from worker.steps.color import color_step
    from worker.steps.consolidate import consolidate_step
    from worker.steps.cutout import (
        make_cutout_step,
        production_parser_factory,
        production_remover_factory,
    )
    from worker.steps.embedding import make_embedding_step
    from worker.steps.preprocess import preprocess_step

    steps: dict[JobStep, Step] = {step: deferred_step for step in STEP_ORDER}
    steps[JobStep.preprocess] = preprocess_step
    steps[JobStep.cutout] = make_cutout_step(
        remover_factory or production_remover_factory(settings),
        parser_factory or production_parser_factory(settings),
    )
    steps[JobStep.color] = color_step
    models = LazyModels(models_factory or production_models_factory(settings))
    steps[JobStep.ai_attributes] = make_ai_attributes_step(models)
    steps[JobStep.embedding] = make_embedding_step(models)
    steps[JobStep.consolidate] = consolidate_step
    return steps


def _now() -> datetime:
    return datetime.now(UTC)


def _begin_step(factory: sessionmaker[Session], job_id: str, step: JobStep) -> None:
    with factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise PermanentStepError(f"job {job_id} disappeared", user_message=DEFAULT_ERROR)
        job.status = JobStatus.running
        job.step = step
        if job.started_at is None:
            job.started_at = _now()
        session.add(job)
        session.commit()


def _finish_step(factory: sessionmaker[Session], job_id: str, progress: int) -> None:
    with factory() as session:
        job = session.get(Job, job_id)
        if job is not None:
            job.progress = max(job.progress, progress)
            session.add(job)
            session.commit()


def _bump_attempts(factory: sessionmaker[Session], job_id: str) -> int:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.attempts += 1
        session.add(job)
        session.commit()
        return job.attempts


def _mark_done(factory: sessionmaker[Session], job_id: str) -> None:
    with factory() as session:
        job = session.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.done
            job.progress = 100
            job.error = None
            job.finished_at = _now()
            session.add(job)
            session.commit()


def _mark_failed(factory: sessionmaker[Session], job_id: str, message: str) -> None:
    with factory() as session:
        job = session.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.failed
            job.error = message
            job.finished_at = _now()
            session.add(job)
            session.commit()


def run_job(
    claimed: ClaimedJob,
    steps: Mapping[JobStep, Step],
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> JobStatus:
    """Run the pipeline for one claimed job; returns the final status."""
    ctx = StepContext(
        job_id=claimed.id,
        garment_id=claimed.garment_id,
        settings=settings,
        session_factory=session_factory,
    )
    attempts = claimed.attempts
    for step in STEP_ORDER:
        while True:
            try:
                _begin_step(session_factory, claimed.id, step)
                steps[step](ctx)
                break
            except PermanentStepError as exc:
                logger.error("job %s: step %s failed permanently: %s", claimed.id, step, exc)
                _mark_failed(session_factory, claimed.id, exc.user_message)
                return JobStatus.failed
            except Exception as exc:  # noqa: BLE001 - unexpected errors are treated as transient
                user_message = exc.user_message if isinstance(exc, StepError) else DEFAULT_ERROR
                if attempts >= MAX_RETRIES:
                    logger.error(
                        "job %s: step %s failed after retry: %s",
                        claimed.id,
                        step,
                        exc,
                        exc_info=True,
                    )
                    _mark_failed(session_factory, claimed.id, user_message)
                    return JobStatus.failed
                logger.warning("job %s: step %s failed, retrying once: %s", claimed.id, step, exc)
                attempts = _bump_attempts(session_factory, claimed.id)
        _finish_step(session_factory, claimed.id, STEP_PROGRESS[step])
    _mark_done(session_factory, claimed.id)
    return JobStatus.done
