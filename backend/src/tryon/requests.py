"""API-side handling of a try-on request (09-virtual-tryon.md §5.2-§5.4, §6.5-§6.7).

Torch-free: resolves the garments, plans the passes, computes the cache key and finds or creates
the `TryOnRender`. It never runs the engine; the worker (V2c) picks up `pending` renders.

Outfit resolution: the items of an outfit are ordered by `layer` (NULL last), then by slot and
garment id, so the same outfit always plans the same passes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from api.errors import (
    GARMENT_NOT_FOUND,
    OUTFIT_NOT_FOUND,
    TRYON_GARMENT_NOT_READY,
    TRYON_INVALID_MANNEQUIN,
    TRYON_NO_COMPATIBLE_GARMENTS,
    AppError,
)
from shared.enums import JobStatus, OutfitSlot
from shared.models import Garment, Outfit, OutfitItem, TryOnRender
from shared.settings import Settings
from tryon.cache import cache_key, hash_cutout, mannequin_version, model_version
from tryon.mannequin import MannequinError, validate_mannequin_id
from tryon.mapping import PassPlan, PlanGarment, plan_passes

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
    hashes: dict[str, str] = {}
    for item in plan.passes:
        cutout = garments[item.garment_id].img_cutout
        if cutout is None:
            continue
        try:
            hashes[item.garment_id] = hash_cutout(settings.images_root, cutout)
        except (OSError, ValueError):
            not_ready.append(item.garment_id)
    if not_ready:
        raise AppError(
            TRYON_GARMENT_NOT_READY,
            "Alguna prenda todavía se está procesando.",
            422,
            {"garment_ids": not_ready},
        )

    mannequin = mannequin_id or settings.tryon_mannequin
    try:
        validate_mannequin_id(mannequin)
        mannequin_digest = mannequin_version(settings.tryon_assets_dir, mannequin)
    except MannequinError as exc:
        raise AppError(
            TRYON_INVALID_MANNEQUIN,
            "El maniquí indicado no existe.",
            422,
            {"mannequin_id": mannequin},
        ) from exc
    model_tag = model_version(settings.tryon_base_revision, settings.tryon_attn_revision)
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


def _reuse(
    session: Session, render: TryOnRender, plan: PassPlan, outfit_id: str | None
) -> RenderOutcome:
    """Cache hit: refresh `last_accessed_at`; a `failed` render is reset to `pending` (retry on
    resubmit, same id) so the user does not need a separate retry endpoint."""
    render.last_accessed_at = _utcnow()
    requeued = render.status == JobStatus.failed
    if requeued:
        render.status = JobStatus.pending
        render.step = "queued"
        render.progress = 0
        render.attempts = 0
        render.error = None
        render.claimed_by = None
        render.claimed_at = None
        render.started_at = None
        render.finished_at = None
        render.img_path = None
        render.duration_ms = None
        render.peak_vram_mb = None
        render.skipped_garment_ids = list(plan.skipped_garment_ids)
        render.unsupported_garment_ids = list(plan.unsupported_garment_ids)
        render.outfit_id = outfit_id
    session.add(render)
    session.commit()
    session.refresh(render)
    return RenderOutcome(render, created=requeued)
