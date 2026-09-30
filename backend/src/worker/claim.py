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


def requeue_stuck_jobs(session: Session) -> int:
    """Requeue jobs a previous worker left `claimed`/`running` back to `pending`.

    Safe only because a single worker runs at a time (VIS-REQ-025); call it
    once at worker start. Returns how many jobs were requeued.
    """
    stmt = (
        update(Job)
        .where(col(Job.status).in_([JobStatus.claimed, JobStatus.running]))
        .values(
            status=JobStatus.pending,
            step=None,
            progress=0,
            claimed_by=None,
            claimed_at=None,
            started_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    result = session.connection().execute(stmt)
    session.commit()
    count = result.rowcount
    logger.info("requeued %d stuck job(s) left by a previous worker", count)
    return count
