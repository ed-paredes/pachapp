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
from typing import TYPE_CHECKING, Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, col, select

from shared import storage
from shared.enums import JobStatus
from shared.imaging import encode_webp
from shared.models import Garment, TryOnRender
from shared.settings import Settings
from tryon.cache import cache_key
from tryon.dummy import DUMMY_VERSION, NO_POSTPROCESS, cut_out, dummy_meta, recolour
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
from tryon.tones import SKIN_TONES

if TYPE_CHECKING:
    from ml.garment_parse import GarmentParser

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
        # Never goes back (an OOM retry restarts the pass's steps at zero).
        percent = max(self._percent() if progress is None else progress, self._written_progress)
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
        postprocess=p["postprocess"],
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
    get_parser: Callable[[], GarmentParser] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> JobStatus:
    """Produce the image of a claimed render and store the outcome; returns the final status.

    `release_residents` frees the upload pipeline's GPU models (BiRefNet, FASHN, SigLIP) and
    runs only while CatVTON is not loaded; they reload lazily on the next upload.

    `get_parser` returns the (resident, lazily built) SegFormer parser of the dummy
    post-processing. A render whose `params.postprocess` is a dummy version gets the six
    tone variants after the raw image; CatVTON stays loaded meanwhile."""
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
        # Malformed stored parameters fail the render for good: first, so nothing else reads them.
        _validate_params(render)
        params = _parse_params(render, settings)
        mannequin = _load_mannequin(settings, render)
        unknown = [c for c in render.params["cloth_types"] if c not in mannequin.masks]
        if unknown:
            raise RenderFailure(ERROR_INVALID_PARAMS, f"unknown cloth types {unknown}")
        garments = _load_garments(factory, settings, render)
        _check_unchanged(render, mannequin.id, garments)
        progress = _Progress(factory, render_id, len(garments), params.steps, clock)
        if release_residents is not None and not engine.loaded:
            release_residents()
        _cuda_peak_reset()
        image = _dress_all(render, mannequin, garments, engine, params, progress)

        progress.finalizing()
        relative = storage.tryon_path(render_id)
        storage.write_atomic(settings.images_root, relative, encode_webp(image))
        peak = _cuda_peak_mb()
        dummy = (
            _write_dummy(settings, render_id, mannequin, image, get_parser)
            if render.params.get("postprocess") not in (None, NO_POSTPROCESS)
            else None
        )
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
        params={**render.params, "dummy": dummy} if dummy else render.params,
        duration_ms=round((clock() - started) * 1000),
        peak_vram_mb=peak,
        finished_at=_now(),
        error=None,
    )
    return JobStatus.done


def _write_dummy(
    settings: Settings,
    render_id: str,
    mannequin: Mannequin,
    image: Image.Image,
    get_parser: Callable[[], GarmentParser] | None,
) -> dict[str, Any] | None:
    """Cut the dummy out of the dressed `image` and write one WebP per skin tone; returns the
    `params.dummy` record, or None when the post-processing failed.

    A failure here never fails the render: the raw CatVTON image is already stored and is a
    usable result (a person, not a dummy), and CatVTON's minutes of work are not thrown away.
    The raw image is served meanwhile (`GET /tryon/{id}` returns it as non-transparent). A
    resubmit of the same request re-queues the render so the dummy is tried again, bounded by
    `MAX_RENDER_ATTEMPTS` (`tryon.requests._reuse`); once spent, the raw render stays for good.
    The variants written so far are removed (best effort, never raising) so no half set is
    served."""
    assert settings.images_root is not None
    try:
        if get_parser is None:
            raise RuntimeError("no parser available for the dummy post-processing")
        parse = get_parser().parse(image)
        prepared = cut_out(image, parse, dummy_meta(mannequin.meta))
        for tone_id, tone_hex in SKIN_TONES:
            data = encode_webp(recolour(prepared, tone_hex))
            storage.write_atomic(
                settings.images_root, storage.tryon_variant_path(render_id, tone_id), data
            )
    except Exception:
        logger.exception(
            "dummy post-processing of render %s failed; keeping the raw image", render_id
        )
        for tone_id, _ in SKIN_TONES:
            path = storage.tryon_variant_path(render_id, tone_id)
            try:
                storage.delete_file(settings.images_root, path)
            except OSError:
                logger.warning("could not delete %s of render %s", path, render_id)
        return None
    return {"version": DUMMY_VERSION, "tones": [tone_id for tone_id, _ in SKIN_TONES]}


_PARAM_KEYS = (
    "width",
    "height",
    "steps",
    "guidance",
    "seed",
    "mannequin_version",
    "model_version",
    "postprocess",
    "cloth_types",
)


def _validate_params(render: TryOnRender) -> None:
    """`params` must hold every key and one cloth type per garment, or the render can never run
    (retrying would fail the same way): fail it as `invalid_params`."""
    p = render.params
    missing = [key for key in _PARAM_KEYS if not isinstance(p, dict) or key not in p]
    if missing:
        raise RenderFailure(ERROR_INVALID_PARAMS, f"render parameters lack {missing}")
    cloth_types = p["cloth_types"]
    if not isinstance(cloth_types, list) or len(cloth_types) != len(render.garment_ids):
        raise RenderFailure(
            ERROR_INVALID_PARAMS,
            f"{len(render.garment_ids)} garments but cloth_types is {cloth_types!r}",
        )


def _parse_params(render: TryOnRender, settings: Settings) -> TryOnParams:
    p = render.params
    try:
        return TryOnParams(
            width=p["width"],
            height=p["height"],
            steps=p["steps"],
            guidance=p["guidance"],
            seed=p["seed"],
            oom_retry_width=settings.tryon_oom_retry_width,
            oom_retry_height=settings.tryon_oom_retry_height,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderFailure(ERROR_INVALID_PARAMS, f"bad render parameters: {exc}") from exc


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
