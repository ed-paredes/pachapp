"""Run one claimed try-on render in the worker (09-virtual-tryon.md §6.3, §6.4, §12).

Steps: `loading_model` (resident models released, CatVTON loaded on the first diffusion step),
`dressing_1..n` (one CatVTON pass per planned garment, each dressing the previous output over the
mannequin's own mask), `finalizing` (WebP written), then `done`. Progress grows across all
diffusion steps of all passes. A failure the engine reports is stored as a short error code
(`out_of_memory`, `blank_output`, ...) with the original message logged; anything unexpected
propagates so the worker loop can requeue the render.

Unlike `tryon.requests`/`mapping`/`cache`, this module may pull in the GPU stack: only the worker
imports it.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, col, select

from shared import storage
from shared.enums import JobStatus
from shared.imaging import encode_webp
from shared.models import Garment, TryOnRender
from shared.settings import Settings
from tryon.cache import cache_key
from tryon.engine import (
    TryOnBlankOutput,
    TryOnEngine,
    TryOnError,
    TryOnInvalidInput,
    TryOnOutOfMemory,
    TryOnParams,
    TryOnUnavailable,
)
from tryon.mannequin import Mannequin, MannequinError, load_mannequin

logger = logging.getLogger(__name__)

# Error codes stored in `tryon_renders.error` (the app maps them to copy).
ERROR_OUT_OF_MEMORY = "out_of_memory"
ERROR_BLANK_OUTPUT = "blank_output"
ERROR_INVALID_GARMENT = "invalid_garment"
ERROR_ENGINE_UNAVAILABLE = "engine_unavailable"
ERROR_GARMENT_MISSING = "garment_missing"
ERROR_GARMENT_CHANGED = "garment_changed"
ERROR_MANNEQUIN_UNAVAILABLE = "mannequin_unavailable"
ERROR_INVALID_PARAMS = "invalid_params"
ERROR_ENGINE_FAILED = "engine_error"

# Progress share (percent) of the model load before the first pass and of the final write.
_LOAD_PROGRESS = 5
_DRESS_PROGRESS = 92
_FINALIZING_PROGRESS = 97
# Progress writes during diffusion are at most this far apart (steps take ~0.5 s each).
PROGRESS_WRITE_INTERVAL_S = 1.0


class RenderFailure(Exception):
    """A render that cannot finish; `code` is stored in `tryon_renders.error`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _update(factory: sessionmaker[Session], render_id: str, **fields: Any) -> None:
    with factory() as session:
        render = session.get(TryOnRender, render_id)
        if render is None:
            return
        for name, value in fields.items():
            setattr(render, name, value)
        session.add(render)
        session.commit()


class _Progress:
    """Writes `step`/`progress` in short transactions; diffusion ticks are throttled."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        render_id: str,
        passes: int,
        steps: int,
        clock: Callable[[], float],
    ) -> None:
        self._factory = factory
        self._render_id = render_id
        self._total = passes * steps
        self._steps = steps
        self._clock = clock
        self._pass = 0
        self._done_in_pass = 0
        self._step_name = "loading_model"
        self._written_step = "loading_model"
        self._written_progress = 0
        self._last_write = float("-inf")

    def begin_pass(self, index: int, *, write: bool = True) -> None:
        """Start pass `index` (0-based); `write=False` keeps the shown step until the first
        diffusion step (the model is still loading)."""
        self._pass = index
        self._done_in_pass = 0
        self._step_name = f"dressing_{index + 1}"
        if write:
            self._write(force=True)

    def retry(self) -> None:
        """The engine restarts the pass at a smaller size: its steps count from zero again."""
        self._done_in_pass = 0
        self._write(force=True)

    def tick(self) -> None:
        self._done_in_pass = min(self._done_in_pass + 1, self._steps)
        self._write(force=False)

    def finalizing(self) -> None:
        self._step_name = "finalizing"
        self._write(force=True, progress=_FINALIZING_PROGRESS)

    def _percent(self) -> int:
        finished = self._pass * self._steps + self._done_in_pass
        return _LOAD_PROGRESS + _DRESS_PROGRESS * finished // self._total

    def _write(self, *, force: bool, progress: int | None = None) -> None:
        percent = self._percent() if progress is None else progress
        step_changed = self._step_name != self._written_step
        if not (force or step_changed):
            now = self._clock()
            if percent == self._written_progress or now - self._last_write < (
                PROGRESS_WRITE_INTERVAL_S
            ):
                return
        _update(self._factory, self._render_id, step=self._step_name, progress=percent)
        self._written_step = self._step_name
        self._written_progress = percent
        self._last_write = self._clock()


def _cuda_peak_reset() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def _cuda_peak_mb() -> int | None:
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return round(torch.cuda.max_memory_allocated() / (1024 * 1024))


def _load_garments(
    factory: sessionmaker[Session], settings: Settings, render: TryOnRender
) -> list[tuple[str, str, Image.Image]]:
    """`(garment_id, sha256, RGBA cutout)` in pass order; a deleted garment or an unreadable
    cutout fails the render."""
    assert settings.images_root is not None
    with factory() as session:
        rows = session.exec(select(Garment).where(col(Garment.id).in_(render.garment_ids)))
        cutouts = {g.id: g.img_cutout for g in rows}
    loaded: list[tuple[str, str, Image.Image]] = []
    for garment_id in render.garment_ids:
        relative = cutouts.get(garment_id)
        if not relative:
            raise RenderFailure(ERROR_GARMENT_MISSING, f"garment {garment_id} has no cutout")
        try:
            data = storage.resolve_path(settings.images_root, relative).read_bytes()
            with Image.open(io.BytesIO(data)) as image:
                rgba = image.convert("RGBA")
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            raise RenderFailure(
                ERROR_GARMENT_MISSING, f"cutout of garment {garment_id} unreadable: {exc}"
            ) from exc
        loaded.append((garment_id, hashlib.sha256(data).hexdigest(), rgba))
    return loaded


def _check_unchanged(
    render: TryOnRender, mannequin_id: str, garments: list[tuple[str, str, Image.Image]]
) -> None:
    """The cache key hashes the cutouts: if the key rebuilt from the files now differs from the
    stored one, a cutout (or the category) changed after the request and the image would
    be filed under the wrong key."""
    p = render.params
    rebuilt = cache_key(
        mannequin_id=mannequin_id,
        mannequin_digest=p["mannequin_version"],
        garments=[
            (gid, digest, cloth)
            for (gid, digest, _), cloth in zip(garments, p["cloth_types"], strict=True)
        ],
        width=p["width"],
        height=p["height"],
        steps=p["steps"],
        guidance=p["guidance"],
        seed=p["seed"],
        model_tag=p["model_version"],
    )
    if rebuilt != render.cache_key:
        raise RenderFailure(ERROR_GARMENT_CHANGED, "a garment cutout changed after the request")


def _dress_all(
    render: TryOnRender,
    mannequin: Mannequin,
    garments: list[tuple[str, str, Image.Image]],
    engine: TryOnEngine,
    params: TryOnParams,
    progress: _Progress,
) -> Image.Image:
    image = mannequin.person
    for index, ((_, _, cutout), cloth) in enumerate(
        zip(garments, render.params["cloth_types"], strict=True)
    ):
        # The first pass of a cold engine shows `loading_model` until its first step.
        progress.begin_pass(index, write=index > 0 or engine.loaded)
        # The mask always comes from the base mannequin, the person from the previous pass.
        image = engine.dress(
            image,
            cutout,
            mannequin.masks[cloth],
            params=params,
            on_step=progress.tick,
            on_retry=progress.retry,
        )
    return image


def run_render(
    render_id: str,
    settings: Settings,
    factory: sessionmaker[Session],
    engine: TryOnEngine,
    *,
    release_residents: Callable[[], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> JobStatus:
    """Produce the image of a claimed render and store the outcome; returns the final status.

    `release_residents` frees the upload pipeline's GPU models (BiRefNet, FASHN, SigLIP) and
    runs only while CatVTON is not loaded; they reload lazily on the next upload."""
    assert settings.images_root is not None
    with factory() as session:
        render = session.get(TryOnRender, render_id)
        if render is None:
            logger.warning("try-on render %s disappeared before it ran", render_id)
            return JobStatus.failed
        session.expunge(render)
    started = clock()
    _update(
        factory,
        render_id,
        status=JobStatus.running,
        step="loading_model",
        progress=0,
        started_at=_now(),
    )
    try:
        mannequin = _load_mannequin(settings, render)
        garments = _load_garments(factory, settings, render)
        _check_unchanged(render, mannequin.id, garments)
        p = render.params
        try:
            params = TryOnParams(
                width=p["width"],
                height=p["height"],
                steps=p["steps"],
                guidance=p["guidance"],
                seed=p["seed"],
                oom_retry_width=settings.tryon_oom_retry_width,
                oom_retry_height=settings.tryon_oom_retry_height,
            )
        except (KeyError, ValueError) as exc:
            raise RenderFailure(ERROR_INVALID_PARAMS, f"bad render parameters: {exc}") from exc

        progress = _Progress(factory, render_id, len(garments), params.steps, clock)
        if release_residents is not None and not engine.loaded:
            release_residents()
        _cuda_peak_reset()
        image = _dress_all(render, mannequin, garments, engine, params, progress)

        progress.finalizing()
        relative = storage.tryon_path(render_id)
        storage.write_atomic(settings.images_root, relative, encode_webp(image))
        peak = _cuda_peak_mb()
    except RenderFailure as failure:
        return _fail(factory, render_id, failure.code, failure)
    except TryOnOutOfMemory as exc:
        return _fail(factory, render_id, ERROR_OUT_OF_MEMORY, exc)
    except TryOnBlankOutput as exc:
        return _fail(factory, render_id, ERROR_BLANK_OUTPUT, exc)
    except TryOnInvalidInput as exc:
        return _fail(factory, render_id, ERROR_INVALID_GARMENT, exc)
    except TryOnUnavailable as exc:
        return _fail(factory, render_id, ERROR_ENGINE_UNAVAILABLE, exc)
    except TryOnError as exc:
        return _fail(factory, render_id, ERROR_ENGINE_FAILED, exc)

    _update(
        factory,
        render_id,
        status=JobStatus.done,
        step="done",
        progress=100,
        img_path=relative,
        duration_ms=round((clock() - started) * 1000),
        peak_vram_mb=peak,
        finished_at=_now(),
        error=None,
    )
    return JobStatus.done


def _load_mannequin(settings: Settings, render: TryOnRender) -> Mannequin:
    try:
        return load_mannequin(settings.tryon_assets_dir, render.mannequin_id)
    except MannequinError as exc:
        raise RenderFailure(ERROR_MANNEQUIN_UNAVAILABLE, str(exc)) from exc


def _fail(
    factory: sessionmaker[Session], render_id: str, code: str, cause: BaseException
) -> JobStatus:
    # The user only sees the code: keep the original message (e.g. the CUDA OOM text) in the log.
    logger.error("try-on render %s failed (%s): %s", render_id, code, cause)
    _update(
        factory,
        render_id,
        status=JobStatus.failed,
        error=code,
        finished_at=_now(),
    )
    return JobStatus.failed
