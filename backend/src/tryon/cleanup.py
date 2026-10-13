"""Cache cleanup for try-on renders (09-virtual-tryon.md §6.5).

A render nobody has looked at for `tryon_cache_max_age_days` is deleted: its row, its WebP and
the dummy's tone variants.
`last_accessed_at` is refreshed by every resubmit (`tryon.requests._reuse`) and by every read of
a `done` render (`GET /tryon/{id}`), so a look the user keeps opening stays.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from sqlalchemy import delete, select
from sqlmodel import Session, col

from shared.enums import JobStatus
from shared.models import TryOnRender
from shared.storage import delete_file, tryon_variant_path
from tryon.tones import SKIN_TONES

logger = logging.getLogger(__name__)

# Only settled renders go: a `pending`, `claimed` or `running` one is queued or in flight.
_SETTLED = (JobStatus.done, JobStatus.failed)


def purge_stale_renders(
    session: Session, images_root: Path, max_age_days: int, now: dt.datetime | None = None
) -> int:
    """Delete the settled renders not accessed for `max_age_days` (0 = keep everything).
    Returns how many were removed.

    The row goes first, in a conditional `DELETE` that re-checks the status and the access time,
    so a render a request just touched or re-queued survives; its file is deleted only for the
    rows that really went (a crash in between leaves an orphan file, never a row without its
    image). A file that is already gone is not an error."""
    if max_age_days <= 0:
        return 0
    cutoff = (now or dt.datetime.now(dt.UTC)) - dt.timedelta(days=max_age_days)
    stale = (
        session.connection()
        .execute(
            select(col(TryOnRender.id), col(TryOnRender.img_path)).where(
                col(TryOnRender.status).in_(_SETTLED), col(TryOnRender.last_accessed_at) < cutoff
            )
        )
        .all()
    )
    removed = 0
    for render_id, img_path in stale:
        result = session.connection().execute(
            delete(TryOnRender)
            .where(
                col(TryOnRender.id) == render_id,
                col(TryOnRender.status).in_(_SETTLED),
                col(TryOnRender.last_accessed_at) < cutoff,
            )
            .execution_options(synchronize_session=False)
        )
        session.commit()
        if result.rowcount != 1:
            continue
        removed += 1
        if img_path:
            # The dummy's tone variants live and die with the raw render.
            paths = [img_path, *(tryon_variant_path(render_id, tone) for tone, _ in SKIN_TONES)]
            for path in paths:
                try:
                    delete_file(images_root, path)
                except OSError:
                    logger.warning("could not delete %s of render %s", path, render_id)
    if removed:
        logger.info("removed %d try-on renders not accessed for %d days", removed, max_age_days)
    return removed
