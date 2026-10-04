"""Outfit generation and persistence (ENG-REQ-020/021, FBH-REQ-017/018)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session, col, select

from api import clock
from api.deps import get_session
from api.engine_inputs import build_generation_request
from api.errors import (
    GARMENT_NOT_FOUND,
    INVALID_FIXED_GARMENTS,
    INVALID_OUTFIT,
    AppError,
    ErrorResponse,
)
from api.routers.settings import _get_or_create as get_setting_row
from api.schemas_outfits import (
    CreateOutfitRequest,
    GenerateOutfitsRequest,
    GenerateOutfitsResponse,
    OutfitItemProposal,
    OutfitItemResponse,
    OutfitProposal,
    OutfitResponse,
)
from engine import InvalidRequest, generate_outfits
from engine.constants import LAYER_BY_SLOT
from shared.enums import OutfitSource
from shared.models import Garment, Outfit, OutfitItem
from shared.schemas import ScoreBreakdown

router = APIRouter(tags=["outfits"])

# FBH-REQ-018: a retry or double tap within this window returns the same outfit.
DEDUPE_WINDOW = timedelta(minutes=5)


@router.post(
    "/outfits/generate",
    response_model=GenerateOutfitsResponse,
    responses={400: {"model": ErrorResponse}},
)
def generate(
    body: GenerateOutfitsRequest, session: Annotated[Session, Depends(get_session)]
) -> GenerateOutfitsResponse:
    """Up to 5 scored proposals; nothing is persisted (ENG-REQ-021, D6). A small
    or empty wardrobe is a normal `200` with fewer or no proposals (ENG-REQ-022)."""
    request = build_generation_request(
        session,
        get_setting_row(session),
        today=clock.local_today(),
        fixed_garment_ids=tuple(str(i) for i in body.fixed_garment_ids or ()),
        replace_garment_id=None
        if body.replace_garment_id is None
        else str(body.replace_garment_id),
        seed=body.seed or 0,
        exclude_sets=tuple(frozenset(str(i) for i in ids) for ids in body.exclude_sets or ()),
    )
    try:
        proposals = generate_outfits(request)
    except InvalidRequest as exc:
        raise AppError(INVALID_FIXED_GARMENTS, str(exc), 400) from exc
    return GenerateOutfitsResponse(
        proposals=[
            OutfitProposal(
                items=[
                    OutfitItemProposal(garment_id=i.garment_id, slot=i.slot, layer=i.layer)
                    for i in p.items
                ],  # type: ignore[arg-type]
                score=p.score,
                score_breakdown=ScoreBreakdown(
                    color=p.breakdown.color,
                    style=p.breakdown.style,
                    novelty=p.breakdown.novelty,
                    preference=p.breakdown.preference,
                    total=p.breakdown.total,
                ),
                explanation=p.explanation,
            )
            for p in proposals
        ],
        generated_at=datetime.now(UTC),
    )


def outfit_response(outfit: Outfit, items: list[OutfitItem]) -> OutfitResponse:
    return OutfitResponse(
        id=outfit.id,
        created_at=outfit.created_at,
        source=outfit.source,
        items=[
            OutfitItemResponse(garment_id=i.garment_id, slot=i.slot, layer=i.layer) for i in items
        ],
        score=outfit.score,
        score_breakdown=(
            None
            if outfit.score_breakdown is None
            else ScoreBreakdown.model_validate(outfit.score_breakdown)
        ),
        explanation=outfit.explanation,
        is_favorite=outfit.is_favorite,
        rating=outfit.rating,
        name=outfit.name,
    )


def _items(session: Session, outfit_id: str) -> list[OutfitItem]:
    return list(session.exec(select(OutfitItem).where(OutfitItem.outfit_id == outfit_id)).all())


def _recent_duplicate(session: Session, garment_ids: set[str]) -> Outfit | None:
    """A generated outfit with exactly this garment set created inside the window."""
    cutoff = datetime.now(UTC) - DEDUPE_WINDOW
    recent = session.exec(
        select(Outfit)
        .where(Outfit.source == OutfitSource.generated, col(Outfit.created_at) >= cutoff)
        .order_by(col(Outfit.created_at).desc())
    ).all()
    for outfit in recent:
        if {i.garment_id for i in _items(session, outfit.id)} == garment_ids:
            return outfit
    return None


@router.post(
    "/outfits",
    response_model=OutfitResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": OutfitResponse, "description": "Same generated outfit within 5 minutes"},
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def create_outfit(
    body: CreateOutfitRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> OutfitResponse:
    """Persist a proposal the first time the owner interacts with it (D6).

    A generated outfit with the same garment set created in the last 5 minutes
    is returned as is with `200` (FBH-REQ-018); its rating and favourite flag
    are not overwritten."""
    garment_ids = {str(item.garment_id) for item in body.items}
    found = set(session.exec(select(Garment.id).where(col(Garment.id).in_(garment_ids))).all())
    if found != garment_ids:
        raise AppError(
            GARMENT_NOT_FOUND,
            "Alguna prenda del outfit no existe.",
            404,
            {"missing": sorted(garment_ids - found)},
        )
    categories = dict(
        session.exec(
            select(Garment.id, Garment.category).where(col(Garment.id).in_(garment_ids))
        ).all()
    )
    for item in body.items:
        if categories[str(item.garment_id)] != item.slot:
            raise AppError(
                INVALID_OUTFIT,
                "El hueco de una prenda no coincide con su categoría.",
                400,
                {"garment_id": str(item.garment_id), "slot": item.slot},
            )

    if body.source == OutfitSource.generated:
        existing = _recent_duplicate(session, garment_ids)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return outfit_response(existing, _items(session, existing.id))

    outfit = Outfit(
        source=body.source,
        score=body.score,
        score_breakdown=None if body.score_breakdown is None else body.score_breakdown.model_dump(),
        explanation=body.explanation,
        rating=body.rating,
        is_favorite=body.is_favorite,
    )
    items = [
        OutfitItem(
            outfit_id=outfit.id,
            garment_id=str(item.garment_id),
            slot=item.slot,
            layer=LAYER_BY_SLOT[item.slot.value],
        )
        for item in body.items
    ]
    session.add(outfit)
    session.add_all(items)
    session.commit()
    return outfit_response(outfit, items)
