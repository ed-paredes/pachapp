"""Atomic claim and stuck-render recovery for try-on renders (09-virtual-tryon.md §6.3, §12.3).

Mirrors `worker.claim` for the `tryon_renders` table. `attempts` counts claims and is cumulative
across API resubmits, so `MAX_RENDER_ATTEMPTS` bounds the total tries of a render, whether it
failed or killed the worker. Every function runs one short transaction and commits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlmodel import Session, col

from shared.enums import JobStatus
from shared.models import MAX_RENDER_ATTEMPTS, TryOnRender

logger = logging.getLogger(__name__)

ERROR_INTERRUPTED = "interrupted"

# Column values that put a render back in the queue.
_PENDING_RESET = {
    "status": JobStatus.pending,
    "step": "queued",
    "progress": 0,
    "claimed_by": None,
    "claimed_at": None,
    "started_at": None,
}


@dataclass(frozen=True)
class ClaimedRender:
    id: str
    attempts: int


def _now() -> datetime:
    return datetime.now(UTC)


def claim_next_render(session: Session, worker_id: str) -> ClaimedRender | None:
    """Claim the oldest `pending` render (one atomic `UPDATE ... RETURNING`, as for jobs) and
    count the attempt; None when there is none."""
    oldest_pending = (
        select(col(TryOnRender.id))
        .where(col(TryOnRender.status) == JobStatus.pending)
        .order_by(col(TryOnRender.created_at), col(TryOnRender.id))
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        update(TryOnRender)
        .where(col(TryOnRender.id) == oldest_pending, col(TryOnRender.status) == JobStatus.pending)
        .values(
            status=JobStatus.claimed,
            claimed_by=worker_id,
            claimed_at=_now(),
            attempts=col(TryOnRender.attempts) + 1,
        )
        .returning(col(TryOnRender.id), col(TryOnRender.attempts))
        .execution_options(synchronize_session=False)
    )
    row = session.exec(stmt).first()
    session.commit()
    if row is None:
        return None
    return ClaimedRender(id=row.id, attempts=row.attempts)


def requeue_stuck_renders(session: Session) -> int:
    """Recover renders a previous worker left `claimed`/`running` (call once at worker start;
    safe because a single worker runs). A render whose attempts are spent becomes `failed`
    (`interrupted`) instead of looping. Returns how many were requeued."""
    stuck = col(TryOnRender.status).in_([JobStatus.claimed, JobStatus.running])
    failed = session.connection().execute(
        update(TryOnRender)
        .where(stuck, col(TryOnRender.attempts) >= MAX_RENDER_ATTEMPTS)
        .values(status=JobStatus.failed, error=ERROR_INTERRUPTED, finished_at=_now())
        .execution_options(synchronize_session=False)
    )
    requeued = session.connection().execute(
        update(TryOnRender)
        .where(stuck)
        .values(**_PENDING_RESET)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    logger.info(
        "recovered stuck renders: %d requeued, %d failed (attempts spent)",
        requeued.rowcount,
        failed.rowcount,
    )
    return requeued.rowcount


def release_orphaned_render(session: Session, render_id: str) -> JobStatus | None:
    """Settle a render whose `run_render` raised unexpectedly after the claim: back to
    `pending` while attempts remain, else `failed`. None when it is gone or already settled."""
    render = session.get(TryOnRender, render_id)
    if render is None or render.status not in (JobStatus.claimed, JobStatus.running):
        return None
    if render.attempts >= MAX_RENDER_ATTEMPTS:
        render.status = JobStatus.failed
        render.error = ERROR_INTERRUPTED
        render.finished_at = _now()
    else:
        for key, value in _PENDING_RESET.items():
            setattr(render, key, value)
    session.add(render)
    session.commit()
    return render.status
