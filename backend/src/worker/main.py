"""Worker process entrypoint for pachapp.

The loop claims one job at a time (`worker.claim`) and runs it through the
step pipeline (`worker.runner`). `run()` is factored out from `main()` so the loop is testable
without touching real signal handlers.

08-local-vision.md, VIS-REQ-008: the worker fixes `HF_HOME`/`U2NET_HOME`
(derived from `PACHAPP_ML_CACHE_DIR`) at process start, before anything else
touches `ml`. No models are loaded here yet (that's step 4 of the plan) —
loading stays lazy in `ml.registry`, triggered by actual pipeline steps.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
from collections.abc import Mapping
from types import FrameType

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from ml.cache import configure_model_cache
from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStep
from shared.settings import Settings, get_settings
from worker.claim import claim_next_job, release_orphaned_job, requeue_stuck_jobs
from worker.runner import Step, default_steps, run_job

logger = logging.getLogger(__name__)

# Delays between best-effort attempts to settle an orphaned job (e.g. while the
# database is still "locked"); bounded so a dead database cannot wedge the loop.
ORPHAN_RELEASE_BACKOFF_S: tuple[float, ...] = (0.0, 0.2, 0.5, 1.0)


def _release_orphan(
    factory: sessionmaker[Session], job_id: str, stop_event: threading.Event
) -> None:
    """Best-effort: requeue or fail a job whose `run_job` raised, so it never
    stays `claimed`/`running` in a live worker. If every attempt fails, the job
    is recovered by `requeue_stuck_jobs` at the next worker start."""
    for delay in ORPHAN_RELEASE_BACKOFF_S:
        if delay:
            stop_event.wait(delay)
        try:
            with factory() as session:
                status = release_orphaned_job(session, job_id)
            logger.warning("job %s orphaned by a worker error, now %s", job_id, status)
            return
        except Exception:
            logger.exception("could not settle orphaned job %s, will retry", job_id)
    logger.error("giving up on orphaned job %s; it is recovered at next worker start", job_id)


def run(
    stop_event: threading.Event,
    settings: Settings | None = None,
    steps: Mapping[JobStep, Step] | None = None,
    engine: Engine | None = None,
) -> None:
    """Requeue stuck jobs, then claim and run one job at a time until
    `stop_event` is set (VIS-REQ-025: single worker, one job at a time).

    `steps` and `engine` are injectable for tests; production uses
    `default_steps(settings)` and an engine built from `settings`.
    """
    settings = settings or get_settings()
    # Settings._derive_paths_and_validate always fills this in; the field
    # type stays `Path | None` because it's an optional override on input.
    assert settings.ml_cache_dir is not None
    configure_model_cache(settings.ml_cache_dir)
    interval_s = settings.worker_poll_interval_ms / 1000
    engine = engine or create_db_engine(settings)
    factory = create_session_factory(engine)
    steps = steps if steps is not None else default_steps(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("pachapp worker started (poll interval: %sms)", settings.worker_poll_interval_ms)

    try:
        with factory() as session:
            requeue_stuck_jobs(session)
    except Exception:
        logger.exception("could not requeue stuck jobs (is the database migrated?)")

    while not stop_event.is_set():
        claimed = None
        try:
            with factory() as session:
                claimed = claim_next_job(session, worker_id)
            if claimed is not None:
                run_job(claimed, steps, settings, factory)
                continue
        except Exception:
            logger.exception("worker iteration failed")
            if claimed is not None:
                _release_orphan(factory, claimed.id, stop_event)
        stop_event.wait(interval_s)

    logger.info("pachapp worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    run(stop_event)


if __name__ == "__main__":
    main()
