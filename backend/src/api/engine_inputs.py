"""Builds the engine's plain inputs from the database (ENG-REQ-020).

The engine is pure (DEV-REQ-002), so everything it reads is fetched here:
active garments with their embeddings, the recent wear history inside the
no-repeat window, the liked/disliked garment pairs and the settings row.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations

import numpy as np
from sqlmodel import Session, col, select

from engine import (
    EngineColor,
    EngineGarment,
    EngineSettings,
    GenerationRequest,
    PreferencePair,
    WornOutfit,
)
from shared.enums import GarmentStatus
from shared.models import Garment, Outfit, OutfitItem, Setting, WearLog
from shared.schemas import ColorEntry


def _engine_garment(row: Garment) -> EngineGarment:
    embedding = None
    if row.embedding is not None and len(row.embedding) % 4 == 0:
        embedding = tuple(np.frombuffer(row.embedding, dtype=np.float32).tolist())
    return EngineGarment(
        id=row.id,
        category=row.category,
        subcategory=row.subcategory,
        colors=tuple(
            EngineColor(c.name, c.hex, c.lab, c.proportion)
            for c in (ColorEntry.model_validate(raw) for raw in row.colors or [])
        ),
        is_neutral=row.is_neutral,
        pattern=row.pattern,
        formality=row.formality,
        style_tags=tuple(row.style_tags or ()),
        embedding=embedding,
        embedding_model=row.embedding_model,
        last_worn_at=row.last_worn_at,
        status=row.status,
    )


def _items_by_outfit(session: Session, outfit_ids: set[str]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    if outfit_ids:
        rows = session.exec(
            select(OutfitItem.outfit_id, OutfitItem.garment_id).where(
                col(OutfitItem.outfit_id).in_(outfit_ids)
            )
        )
        for outfit_id, garment_id in rows:
            grouped[outfit_id].add(garment_id)
    return grouped


def _history(session: Session, today: date, no_repeat_days: int) -> tuple[WornOutfit, ...]:
    logs = session.exec(
        select(WearLog).where(
            WearLog.date > today - timedelta(days=max(no_repeat_days, 0)) - timedelta(days=1)
        )
    ).all()
    items = _items_by_outfit(session, {log.outfit_id for log in logs})
    return tuple(WornOutfit(log.date, frozenset(items[log.outfit_id])) for log in logs)


def _preferences(session: Session) -> tuple[PreferencePair, ...]:
    """Pair co-occurrence in favourite (`is_favorite` or `rating = 1`) versus
    disliked (`rating = -1`) outfits, for every garment pair (ENG-REQ-013)."""
    outfits = session.exec(
        select(Outfit).where((col(Outfit.is_favorite)) | (col(Outfit.rating) != 0))
    ).all()
    items = _items_by_outfit(session, {o.id for o in outfits})
    liked: dict[tuple[str, str], int] = defaultdict(int)
    disliked: dict[tuple[str, str], int] = defaultdict(int)
    for outfit in outfits:
        target = liked if outfit.is_favorite or outfit.rating == 1 else disliked
        for pair in combinations(sorted(items[outfit.id]), 2):
            target[pair] += 1
    return tuple(
        PreferencePair(a, b, liked[(a, b)], disliked[(a, b)]) for a, b in {*liked, *disliked}
    )


def build_generation_request(
    session: Session,
    setting: Setting,
    *,
    today: date,
    fixed_garment_ids: tuple[str, ...],
    replace_garment_id: str | None,
    seed: int,
) -> GenerationRequest:
    garments = session.exec(select(Garment).where(Garment.status == GarmentStatus.active)).all()
    return GenerationRequest(
        garments=tuple(_engine_garment(row) for row in garments),
        today=today,
        settings=EngineSettings(
            weight_color=setting.weight_color,
            weight_style=setting.weight_style,
            weight_novelty=setting.weight_novelty,
            weight_preference=setting.weight_preference,
            no_repeat_days=setting.no_repeat_days,
            max_accessories=setting.max_accessories,
        ),
        history=_history(session, today, setting.no_repeat_days),
        preferences=_preferences(session),
        fixed_garment_ids=fixed_garment_ids,
        replace_garment_id=replace_garment_id,
        seed=seed,
    )
