"""Atomic job claim and stuck-job recovery (DAT-REQ-009/010, ING-SCN-006).

Every function here runs one short transaction and commits before returning;
no transaction is ever held open while a pipeline step runs (DAT-REQ-010).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlmodel import Session, col

from shared.enums import JobStatus
from shared.models import Job

logger = logging.getLogger(__name__)

# Retry budget per job (ING-REQ-022): one retry in total, counted in `job.attempts`.
MAX_RETRIES = 1

MSG_INTERRUPTED = "El procesamiento se interrumpió repetidamente. Inténtalo de nuevo con otra foto."

# Column values that put a job back in the queue.
_PENDING_RESET = {
    "status": JobStatus.pending,
    "step": None,
    "progress": 0,
    "claimed_by": None,
    "claimed_at": None,
    "started_at": None,
}


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    garment_id: str
    attempts: int


def claim_next_job(session: Session, worker_id: str) -> ClaimedJob | None:
    """Claim the oldest `pending` job, or return None when there is none.

    One `UPDATE ... WHERE id = (SELECT ... LIMIT 1) AND status = 'pending'
    RETURNING ...` statement. SQLite serializes writers: the statement takes
    the write lock before evaluating the sub-select, so two racing workers can
    never claim the same row (the loser waits on `busy_timeout`, then sees the
    winner's row already `claimed` and picks the next one).
    """
    oldest_pending = (
        select(col(Job.id))
        .where(col(Job.status) == JobStatus.pending)
        .order_by(col(Job.created_at), col(Job.id))
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        update(Job)
        .where(col(Job.id) == oldest_pending, col(Job.status) == JobStatus.pending)
        .values(status=JobStatus.claimed, claimed_by=worker_id, claimed_at=datetime.now(UTC))
        .returning(col(Job.id), col(Job.garment_id), col(Job.attempts))
        .execution_options(synchronize_session=False)
    )
    row = session.exec(stmt).first()
    session.commit()
    if row is None:
        return None
    return ClaimedJob(id=row.id, garment_id=row.garment_id, attempts=row.attempts)


def _now() -> datetime:
    return datetime.now(UTC)


def requeue_stuck_jobs(session: Session) -> int:
    """Recover jobs a previous worker left `claimed`/`running`.

    Safe only because a single worker runs at a time (VIS-REQ-025); call it
    once at worker start. A requeue consumes the per-job retry budget
    (`attempts`, ING-REQ-022): a job that already used its budget (a poison job
    that keeps killing the worker) is marked `failed` instead of looping forever.
    Returns how many jobs were requeued.
    """
    stuck = col(Job.status).in_([JobStatus.claimed, JobStatus.running])
    failed = session.connection().execute(
        update(Job)
        .where(stuck, col(Job.attempts) >= MAX_RETRIES)
        .values(status=JobStatus.failed, error=MSG_INTERRUPTED, finished_at=_now())
        .execution_options(synchronize_session=False)
    )
    requeued = session.connection().execute(
        update(Job)
        .where(stuck)
        .values(attempts=col(Job.attempts) + 1, **_PENDING_RESET)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    logger.info(
        "recovered stuck jobs left by a previous worker: %d requeued, %d failed (budget spent)",
        requeued.rowcount,
        failed.rowcount,
    )
    return requeued.rowcount


def release_orphaned_job(session: Session, job_id: str) -> JobStatus | None:
    """Settle a job whose `run_job` raised after it was claimed, so it does not
    stay `claimed`/`running` inside a live worker.

    Same policy as `requeue_stuck_jobs`: requeue to `pending` while the retry
    budget lasts (consuming one attempt), otherwise mark it `failed` with a
    generic Spanish message. Returns the new status, or None when the job is
    gone or already settled (terminal/pending), so it is safe to call twice.
    """
    job = session.get(Job, job_id)
    if job is None or job.status not in (JobStatus.claimed, JobStatus.running):
        return None
    if job.attempts >= MAX_RETRIES:
        job.status = JobStatus.failed
        job.error = MSG_INTERRUPTED
        job.finished_at = _now()
    else:
        job.attempts += 1
        for key, value in _PENDING_RESET.items():
            setattr(job, key, value)
    session.add(job)
    session.commit()
    return job.status
