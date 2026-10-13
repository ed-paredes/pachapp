"""API-side handling of a try-on request (09-virtual-tryon.md §5.2-§5.4, §6.5-§6.7).

Torch-free: resolves the garments, plans the passes, computes the cache key and finds or creates
the `TryOnRender`. It never runs the engine; the worker (V2c) picks up `pending` renders.

Outfit resolution: the items of an outfit are ordered by `layer` (NULL last), then by slot and
garment id, so the same outfit always plans the same passes.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.errors import (
    GARMENT_NOT_FOUND,
    OUTFIT_NOT_FOUND,
    TRYON_GARMENT_IMAGE_MISSING,
    TRYON_GARMENT_NOT_READY,
    TRYON_INVALID_MANNEQUIN,
    TRYON_NO_COMPATIBLE_GARMENTS,
    AppError,
)
from shared.enums import JobStatus, OutfitSlot
from shared.models import (
    MAX_RENDER_ATTEMPTS,
    Garment,
    Outfit,
    OutfitItem,
    Setting,
    TryOnRender,
)
from shared.settings import Settings
from tryon.cache import cache_key, hash_cutout, mannequin_version, model_version
from tryon.dummy import DUMMY_VERSION, NO_POSTPROCESS
from tryon.mannequin import MannequinError, validate_mannequin_id
from tryon.mapping import PassPlan, PlanGarment, plan_passes
from tryon.tones import DEFAULT_GENDER, Gender

logger = logging.getLogger(__name__)

# Failures a retry cannot fix (the codes of `tryon.service`/`worker.tryon_claim`): a resubmit
# returns them as they are. The others (`out_of_memory`, `engine_unavailable`, `engine_error`,
# `interrupted`) may be transient and can be retried. `blank_output` is permanent: the seed is
# part of the cache key, so a retry reruns the same inputs and gets the same blank image.
PERMANENT_ERRORS: Final = frozenset(
    {
        "invalid_garment",
        "invalid_params",
        "garment_missing",
        "garment_changed",
        "mannequin_unavailable",
        "blank_output",
    }
)
# A failed render that spent its `MAX_RENDER_ATTEMPTS` can start a new round of attempts, but
# only this long after it failed: a user mashing "Reintentar" cannot loop the GPU.
RETRY_COOLDOWN: Final = dt.timedelta(minutes=5)

_SLOT_ORDER: Final = {slot: index for index, slot in enumerate(OutfitSlot)}


@dataclass(frozen=True)
class RenderOutcome:
    render: TryOnRender
    created: bool  # True when this call inserted or re-queued the render


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _outfit_garment_ids(session: Session, outfit_id: str) -> list[str]:
    if session.get(Outfit, outfit_id) is None:
        raise AppError(
            OUTFIT_NOT_FOUND,
            f"La combinación {outfit_id} no existe.",
            404,
            {"outfit_id": outfit_id},
        )
    items = session.exec(select(OutfitItem).where(OutfitItem.outfit_id == outfit_id)).all()
    items = sorted(
        items,
        key=lambda i: (i.layer is None, i.layer or 0, _SLOT_ORDER[i.slot], i.garment_id),
    )
    return [item.garment_id for item in items]


def _load_garments(session: Session, garment_ids: list[str]) -> dict[str, Garment]:
    unique = list(dict.fromkeys(garment_ids))
    rows = session.exec(select(Garment).where(col(Garment.id).in_(unique)))
    found = {g.id: g for g in rows}
    missing = [gid for gid in unique if gid not in found]
    if missing:
        raise AppError(
            GARMENT_NOT_FOUND,
            "Alguna prenda no existe.",
            404,
            {"garment_ids": missing},
        )
    return found


def _plan(garments: dict[str, Garment], ordered_ids: list[str], max_passes: int) -> PassPlan:
    plan = plan_passes(
        (PlanGarment(gid, garments[gid].category) for gid in ordered_ids), max_passes
    )
    if plan.is_empty:
        raise AppError(
            TRYON_NO_COMPATIBLE_GARMENTS,
            "Ninguna prenda se puede probar en el maniquí.",
            422,
            {"unsupported_garment_ids": list(plan.unsupported_garment_ids)},
        )
    return plan


def configured_mannequin(settings: Settings, gender: Gender) -> str:
    return settings.tryon_mannequin_man if gender == "man" else settings.tryon_mannequin_woman


def default_mannequin(session: Session, settings: Settings) -> str:
    """The base mannequin for the owner's current `Setting.tryon_gender` (woman when unset)."""
    row = session.get(Setting, 1)
    gender = row.tryon_gender if row is not None else DEFAULT_GENDER
    return configured_mannequin(settings, "man" if gender == "man" else DEFAULT_GENDER)


def _mannequin_digest(settings: Settings, mannequin: str) -> str:
    validate_mannequin_id(mannequin)
    return mannequin_version(settings.tryon_assets_dir, mannequin)


def _resolve_mannequin(
    session: Session, settings: Settings, mannequin_id: str | None
) -> tuple[str, str]:
    """The mannequin id and its digest. An explicit id must be usable (422 otherwise); the
    gender default falls back to the woman base when the chosen base is unusable, so a broken
    or missing base asset never blocks every render."""
    candidates = [mannequin_id] if mannequin_id else [default_mannequin(session, settings)]
    fallback = configured_mannequin(settings, DEFAULT_GENDER)
    if mannequin_id is None and fallback not in candidates:
        candidates.append(fallback)
    for mannequin in candidates:
        try:
            return mannequin, _mannequin_digest(settings, mannequin)
        except MannequinError:
            logger.warning("try-on mannequin %r is unusable", mannequin, exc_info=True)
    raise AppError(
        TRYON_INVALID_MANNEQUIN,
        "El maniquí indicado no existe.",
        422,
        {"mannequin_id": candidates[0]},
    )


def find_or_create_render(
    session: Session,
    settings: Settings,
    *,
    garment_ids: list[str] | None,
    outfit_id: str | None,
    mannequin_id: str | None,
) -> RenderOutcome:
    """Resolve the request into a render: a cached/in-flight one, a re-queued failed one, or a
    new `pending` one. Raises `AppError` (404 unknown garment/outfit, 422 nothing to dress,
    garment without cutout or unknown mannequin)."""
    assert settings.images_root is not None
    ordered_ids = (
        _outfit_garment_ids(session, outfit_id)
        if outfit_id is not None
        else list(garment_ids or [])
    )
    garments = _load_garments(session, ordered_ids)
    plan = _plan(garments, ordered_ids, settings.tryon_max_passes)

    not_ready = [p.garment_id for p in plan.passes if not garments[p.garment_id].img_cutout]
    if not_ready:
        raise AppError(
            TRYON_GARMENT_NOT_READY,
            "Alguna prenda todavía se está procesando.",
            422,
            {"garment_ids": not_ready},
        )
    hashes: dict[str, str] = {}
    unreadable: list[str] = []
    for item in plan.passes:
        cutout = garments[item.garment_id].img_cutout
        assert cutout is not None
        try:
            hashes[item.garment_id] = hash_cutout(settings.images_root, cutout)
        except (OSError, ValueError):
            unreadable.append(item.garment_id)
    if unreadable:
        # Permanent (the file is gone or outside the images root), unlike "still processing".
        raise AppError(
            TRYON_GARMENT_IMAGE_MISSING,
            "No se encuentra la imagen de alguna prenda.",
            422,
            {"garment_ids": unreadable},
        )

    mannequin, mannequin_digest = _resolve_mannequin(session, settings, mannequin_id)
    model_tag = model_version(settings.tryon_base_revision, settings.tryon_attn_revision)
    postprocess = DUMMY_VERSION if settings.tryon_dummy_enabled else NO_POSTPROCESS
    key = cache_key(
        mannequin_id=mannequin,
        mannequin_digest=mannequin_digest,
        garments=[(p.garment_id, hashes[p.garment_id], p.cloth_type.value) for p in plan.passes],
        width=settings.tryon_width,
        height=settings.tryon_height,
        steps=settings.tryon_steps,
        guidance=settings.tryon_guidance,
        seed=settings.tryon_seed,
        model_tag=model_tag,
        postprocess=postprocess,
    )

    existing = session.exec(select(TryOnRender).where(TryOnRender.cache_key == key)).first()
    if existing is not None:
        return _reuse(session, existing, plan, outfit_id)

    render = TryOnRender(
        cache_key=key,
        mannequin_id=mannequin,
        garment_ids=list(plan.garment_ids),
        skipped_garment_ids=list(plan.skipped_garment_ids),
        unsupported_garment_ids=list(plan.unsupported_garment_ids),
        outfit_id=outfit_id,
        status=JobStatus.pending,
        step="queued",
        progress=0,
        params={
            "width": settings.tryon_width,
            "height": settings.tryon_height,
            "steps": settings.tryon_steps,
            "guidance": settings.tryon_guidance,
            "seed": settings.tryon_seed,
            "mannequin_version": mannequin_digest,
            "model_version": model_tag,
            "postprocess": postprocess,
            "cloth_types": [p.cloth_type.value for p in plan.passes],
        },
    )
    session.add(render)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent identical request inserted it first: return that one.
        session.rollback()
        winner = session.exec(select(TryOnRender).where(TryOnRender.cache_key == key)).one()
        return _reuse(session, winner, plan, outfit_id)
    session.refresh(render)
    return RenderOutcome(render, created=True)


def _requeue_values(plan: PassPlan, outfit_id: str | None, now: dt.datetime) -> dict[str, Any]:
    """The columns that put a settled render back in the queue (shared by both re-queue paths)."""
    return {
        "status": JobStatus.pending,
        "step": "queued",
        "progress": 0,
        "error": None,
        "claimed_by": None,
        "claimed_at": None,
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "peak_vram_mb": None,
        "skipped_garment_ids": list(plan.skipped_garment_ids),
        "unsupported_garment_ids": list(plan.unsupported_garment_ids),
        "outfit_id": outfit_id,
        "last_accessed_at": now,
    }


def _dummy_retry_due(render: TryOnRender) -> bool:
    """A `done` render asked for the dummy but has none (its post-processing failed, so only
    the raw image exists) and still has attempts left."""
    if render.status != JobStatus.done or render.attempts >= MAX_RENDER_ATTEMPTS:
        return False
    postprocess = render.params.get("postprocess")
    return postprocess not in (None, NO_POSTPROCESS) and "dummy" not in render.params


def _reuse(
    session: Session, render: TryOnRender, plan: PassPlan, outfit_id: str | None
) -> RenderOutcome:
    """Cache hit: refresh `last_accessed_at`; a `failed` render is reset to `pending` (retry on
    resubmit, same id) so the user does not need a separate retry endpoint.

    A `done` render whose dummy post-processing failed (dummy version requested, no
    `params.dummy`) is re-queued the same way on resubmit, so a transient parser failure is not
    cached for good. It is bounded by the same cumulative `attempts` budget (each run counts one
    claim) and, once spent, the raw render is returned as it is, with no cooldown round. Until
    the new run finishes, the raw image stays in place and the render answers 202.

    Retry rule: a permanent failure (`PERMANENT_ERRORS`) stays failed. Any other failure is
    re-queued while `attempts` (cumulative across resubmits) is below `MAX_RENDER_ATTEMPTS`; once
    the cap is reached it is re-queued only `RETRY_COOLDOWN` after it failed, starting a new
    round (`attempts` back to 0). So tries are bounded to `MAX_RENDER_ATTEMPTS` per cooldown. A
    capped failure without `finished_at` (a legacy row) has its cooldown start now, so it is
    not retried at once and not stuck either.

    The reset is a conditional `UPDATE ... WHERE status = 'failed'`: if the worker or another
    request changed the row meanwhile, nothing is overwritten and the fresh row is returned."""
    now = _utcnow()
    requeued = False
    if render.status == JobStatus.failed and render.error not in PERMANENT_ERRORS:
        capped = render.attempts >= MAX_RENDER_ATTEMPTS
        conditions = [
            col(TryOnRender.id) == render.id,
            col(TryOnRender.status) == JobStatus.failed,
        ]
        if capped:
            session.connection().execute(
                update(TryOnRender)
                .where(*conditions, col(TryOnRender.finished_at).is_(None))
                .values(finished_at=now)
                .execution_options(synchronize_session=False)
            )
            conditions += [
                col(TryOnRender.attempts) >= MAX_RENDER_ATTEMPTS,
                col(TryOnRender.finished_at) <= now - RETRY_COOLDOWN,
            ]
        else:
            conditions.append(col(TryOnRender.attempts) < MAX_RENDER_ATTEMPTS)
        result = session.connection().execute(
            update(TryOnRender)
            .where(*conditions)
            .values(
                **_requeue_values(plan, outfit_id, now),
                attempts=0 if capped else col(TryOnRender.attempts),
                img_path=None,
            )
            .execution_options(synchronize_session=False)
        )
        requeued = result.rowcount == 1
    elif _dummy_retry_due(render):
        # The raw image keeps being served (and its file stays) until the new run replaces it.
        result = session.connection().execute(
            update(TryOnRender)
            .where(
                col(TryOnRender.id) == render.id,
                col(TryOnRender.status) == JobStatus.done,
                col(TryOnRender.attempts) < MAX_RENDER_ATTEMPTS,
            )
            .values(**_requeue_values(plan, outfit_id, now))
            .execution_options(synchronize_session=False)
        )
        requeued = result.rowcount == 1
    if not requeued:
        session.connection().execute(
            update(TryOnRender)
            .where(col(TryOnRender.id) == render.id)
            .values(last_accessed_at=now)
            .execution_options(synchronize_session=False)
        )
    session.commit()
    session.refresh(render)
    return RenderOutcome(render, created=requeued)
