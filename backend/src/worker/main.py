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
import time
from collections.abc import Mapping
from types import FrameType

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from ml.cache import configure_model_cache
from ml.garment_parse import GarmentParser, build_parser
from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStep
from shared.settings import Settings, get_settings
from tryon.cleanup import purge_stale_renders
from tryon.engine import TryOnEngine
from tryon.service import run_render
from worker.claim import claim_next_job, release_orphaned_job, requeue_stuck_jobs
from worker.runner import Pipeline, Step, build_pipeline, run_job
from worker.tryon_claim import claim_next_render, release_orphaned_render, requeue_stuck_renders

logger = logging.getLogger(__name__)

# How often an idle worker looks for stale try-on renders to delete.
RENDER_CLEANUP_INTERVAL_S = 3600.0

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


def _release_orphan_render(
    factory: sessionmaker[Session], render_id: str, stop_event: threading.Event
) -> None:
    """Same as `_release_orphan`, for a try-on render."""
    for delay in ORPHAN_RELEASE_BACKOFF_S:
        if delay:
            stop_event.wait(delay)
        try:
            with factory() as session:
                status = release_orphaned_render(session, render_id)
            logger.warning("render %s orphaned by a worker error, now %s", render_id, status)
            return
        except Exception:
            logger.exception("could not settle orphaned render %s, will retry", render_id)
    logger.error("giving up on orphaned render %s; it is recovered at next worker start", render_id)


def _build_tryon_engine(settings: Settings) -> TryOnEngine:
    # Imported here: the engine module pulls in the GPU stack only when a render needs it.
    from tryon.engine import CatVTONEngine

    assert settings.tryon_catvton_dir is not None
    return CatVTONEngine(
        settings.tryon_catvton_dir,
        base_revision=settings.tryon_base_revision,
        attn_revision=settings.tryon_attn_revision,
        dtype=settings.tryon_dtype,
        idle_unload_seconds=settings.tryon_idle_unload_seconds,
        converted_dir=settings.ml_cache_dir / "tryon" if settings.ml_cache_dir else None,
    )


def run(
    stop_event: threading.Event,
    settings: Settings | None = None,
    steps: Mapping[JobStep, Step] | None = None,
    engine: Engine | None = None,
    tryon_engine: TryOnEngine | None = None,
    dummy_parser: GarmentParser | None = None,
) -> None:
    """Requeue stuck jobs and renders, then claim and run one unit of work at a time until
    `stop_event` is set (VIS-REQ-025: single worker). Upload jobs always go first; a try-on
    render (only with `tryon_enabled`) runs when no job is pending.

    `steps`, `engine`, `tryon_engine` and `dummy_parser` are injectable for tests; production
    uses `build_pipeline(settings)`, an engine built from `settings` and, lazily on the first
    render, a `CatVTONEngine` and the SegFormer-b2 parser of the dummy post-processing (kept
    resident, on `tryon_dummy_device`, so CatVTON never has to unload for it).

    GPU hand-over (6 GB card): before CatVTON loads, the upload pipeline's models are released
    (they reload on the next upload); before an upload job runs, a loaded CatVTON is unloaded.
    """
    settings = settings or get_settings()
    # Settings._derive_paths_and_validate always fills this in; the field
    # type stays `Path | None` because it's an optional override on input.
    assert settings.ml_cache_dir is not None
    configure_model_cache(settings.ml_cache_dir)
    interval_s = settings.worker_poll_interval_ms / 1000
    engine = engine or create_db_engine(settings)
    factory = create_session_factory(engine)
    pipeline: Pipeline | None = None
    if steps is None:
        pipeline = build_pipeline(settings)
        steps = pipeline.steps
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("pachapp worker started (poll interval: %sms)", settings.worker_poll_interval_ms)

    try:
        with factory() as session:
            requeue_stuck_jobs(session)
    except Exception:
        logger.exception("could not requeue stuck jobs (is the database migrated?)")

    if settings.tryon_enabled:
        try:
            with factory() as session:
                requeue_stuck_renders(session)
        except Exception:
            logger.exception("could not requeue stuck renders (is the database migrated?)")

    def release_residents() -> None:
        if pipeline is not None:
            from tryon.memory import release_resident_models, resident_unloaders

            release_resident_models(resident_unloaders(pipeline.cutout, pipeline.models))

    def get_dummy_parser() -> GarmentParser:
        nonlocal dummy_parser
        if dummy_parser is None:
            dummy_parser = build_parser("segformer-b2", settings, settings.tryon_dummy_device)
        return dummy_parser

    next_cleanup = 0.0  # the first idle iteration cleans up
    while not stop_event.is_set():
        claimed = None
        render_id = None
        try:
            with factory() as session:
                claimed = claim_next_job(session, worker_id)
            if claimed is not None:
                if tryon_engine is not None and tryon_engine.loaded:
                    tryon_engine.unload()
                run_job(claimed, steps, settings, factory)
                continue
            if settings.tryon_enabled:
                with factory() as session:
                    render = claim_next_render(session, worker_id)
                if render is not None:
                    render_id = render.id
                    tryon_engine = tryon_engine or _build_tryon_engine(settings)
                    run_render(
                        render.id,
                        settings,
                        factory,
                        tryon_engine,
                        release_residents=release_residents,
                        get_parser=get_dummy_parser,
                    )
                    continue
                if tryon_engine is not None:
                    tryon_engine.unload_if_idle()
                if time.monotonic() >= next_cleanup:
                    next_cleanup = time.monotonic() + RENDER_CLEANUP_INTERVAL_S
                    _purge_stale_renders(factory, settings)
        except Exception:
            logger.exception("worker iteration failed")
            if claimed is not None:
                _release_orphan(factory, claimed.id, stop_event)
            if render_id is not None:
                _release_orphan_render(factory, render_id, stop_event)
        stop_event.wait(interval_s)

    logger.info("pachapp worker stopped")


def _purge_stale_renders(factory: sessionmaker[Session], settings: Settings) -> None:
    """Housekeeping: a failure is logged and retried at the next interval, never fatal."""
    assert settings.images_root is not None  # filled in by Settings
    try:
        with factory() as session:
            purge_stale_renders(session, settings.images_root, settings.tryon_cache_max_age_days)
    except Exception:
        logger.exception("could not clean up stale try-on renders")


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
