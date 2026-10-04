"""Precomputed per-call arrays: everything the vectorised stages look up.

Garments are sorted by id so the result never depends on input order, and a
seeded RNG assigns each garment a tie-break key (ENG-REQ-019: the seed is only
ever used to break exact ties).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from engine import constants as C
from engine.types import EngineGarment, GenerationRequest, InvalidRequest
from shared.enums import GarmentCategory, GarmentPattern, GarmentStatus

Array = NDArray[Any]

LOUD_PATTERNS = frozenset({GarmentPattern.striped, GarmentPattern.plaid, GarmentPattern.printed})

# Channels of `Context.pair`, gathered together for each garment pair.
CH_JACCARD, CH_JACCARD_OK, CH_COSINE, CH_COSINE_OK, CH_WORN_TOGETHER, CH_PREFERENCE = range(6)


@dataclass
class Context:
    garments: list[EngineGarment]  # eligible garments, sorted by id
    index: dict[str, int]
    today: date
    weights: Array  # (4,) color, style, novelty, preference
    formality: Array  # (n,)
    ckey: Array  # (n,) colour id of non-neutral clothing, 0 otherwise
    ghue: Array  # (n,) hue angle in degrees of the dominant colour (non-neutral clothing)
    loud: Array  # (n,) bool, loud pattern on a clothing garment
    subcat: Array  # (n,) accessory subtype code, -1 for clothing
    item_novelty: Array  # (n,) 1 - exp(-days / 7)
    forgotten: Array  # (n,) 1.0 when unused for >= 60 days
    days_since: Array  # (n,) days since last worn (NEVER_WORN_DAYS if never)
    pair: Array  # (n, n, 6)
    tiebreak: Array  # (n,) seeded random keys
    recent_sets: frozenset[frozenset[str]]
    excluded_sets: frozenset[frozenset[str]]  # sets the caller already showed
    slot: list[str]  # category value per garment


def hue_degrees(garment: EngineGarment) -> float:
    _lightness, a, b = garment.colors[0].lab
    return math.degrees(math.atan2(b, a)) % 360.0


def _is_non_neutral(garment: EngineGarment) -> bool:
    return bool(garment.colors) and garment.is_neutral is False


def build_context(request: GenerationRequest, garments: list[EngineGarment]) -> Context:
    garments = sorted(garments, key=lambda g: g.id)
    n = len(garments)
    index = {g.id: i for i, g in enumerate(garments)}
    settings = request.settings

    if not 0 <= request.seed <= C.SEED_MAX:
        raise InvalidRequest(f"La semilla debe ser un número entre 0 y {C.SEED_MAX}.")
    rng = np.random.default_rng(request.seed)
    tiebreak = rng.random(n)

    formality = np.array(
        [C.DEFAULT_FORMALITY if g.formality is None else g.formality for g in garments], dtype=float
    )

    ckey = np.zeros(n, dtype=np.int16)
    loud = np.zeros(n, dtype=bool)
    subcat = np.full(n, -1, dtype=np.int32)
    key_ids: dict[str, int] = {}
    ghue = np.zeros(n)
    subcat_ids: dict[str, int] = {}
    for i, g in enumerate(garments):
        clothing = g.category != GarmentCategory.accessory
        if clothing and _is_non_neutral(g):
            name = g.colors[0].name
            if name not in key_ids:
                key_ids[name] = len(key_ids) + 1
            ckey[i] = key_ids[name]
            ghue[i] = hue_degrees(g)
        loud[i] = clothing and g.pattern in LOUD_PATTERNS
        if not clothing:
            if g.subcategory and g.subcategory.strip():
                code = subcat_ids.setdefault(g.subcategory.strip().casefold(), len(subcat_ids))
            else:  # unknown subtype: never the same as another garment's
                code = 1_000_000 + i
            subcat[i] = code

    days = np.array(
        [
            C.NEVER_WORN_DAYS
            if g.last_worn_at is None
            else max(0, (request.today - g.last_worn_at).days)
            for g in garments
        ],
        dtype=float,
    )
    item_novelty = 1.0 - np.exp(-days / C.NOVELTY_DECAY_DAYS)
    forgotten = (days >= C.FORGOTTEN_AFTER_DAYS).astype(float)

    pair = np.zeros((n, n, 6))
    _fill_tags(pair, garments)
    _fill_embeddings(pair, garments)
    recent_sets = _fill_history(pair, request, index)
    for p in request.preferences:
        ia, ib = index.get(p.garment_a), index.get(p.garment_b)
        if ia is not None and ib is not None and ia != ib:
            pair[ia, ib, CH_PREFERENCE] += p.liked - p.disliked
            pair[ib, ia, CH_PREFERENCE] += p.liked - p.disliked

    return Context(
        garments=garments,
        index=index,
        today=request.today,
        weights=np.array(
            [
                settings.weight_color,
                settings.weight_style,
                settings.weight_novelty,
                settings.weight_preference,
            ]
        ),
        formality=formality,
        ckey=ckey,
        ghue=ghue,
        loud=loud,
        subcat=subcat,
        item_novelty=item_novelty,
        forgotten=forgotten,
        days_since=days,
        pair=pair,
        tiebreak=tiebreak,
        recent_sets=recent_sets,
        excluded_sets=frozenset(request.exclude_sets),
        slot=[str(g.category.value) if g.category else "" for g in garments],
    )


def _fill_tags(pair: Array, garments: list[EngineGarment]) -> None:
    vocab: dict[str, int] = {}
    for g in garments:
        for tag in g.style_tags:
            vocab.setdefault(tag, len(vocab))
    if not vocab:
        return
    multi_hot = np.zeros((len(garments), len(vocab)))
    for i, g in enumerate(garments):
        for tag in g.style_tags:
            multi_hot[i, vocab[tag]] = 1.0
    sizes = multi_hot.sum(axis=1)
    has = sizes > 0
    inter = multi_hot @ multi_hot.T
    union = sizes[:, None] + sizes[None, :] - inter
    ok = has[:, None] & has[None, :]
    pair[:, :, CH_JACCARD_OK] = ok
    pair[:, :, CH_JACCARD] = np.where(ok, inter / np.where(union > 0, union, 1.0), 0.0)


def _fill_embeddings(pair: Array, garments: list[EngineGarment]) -> None:
    """Pairwise cosine, only between vectors of the same `embedding_model`
    (VIS-REQ-023); a garment without a usable vector contributes no pair."""
    groups: dict[str, list[int]] = {}
    for i, g in enumerate(garments):
        if g.embedding is not None and g.embedding_model:
            groups.setdefault(g.embedding_model, []).append(i)
    for rows in groups.values():
        dim = len(garments[rows[0]].embedding or ())
        rows = [i for i in rows if len(garments[i].embedding or ()) == dim and dim > 0]
        if len(rows) < 2:
            continue
        mat = np.array([garments[i].embedding for i in rows], dtype=float)
        norms = np.linalg.norm(mat, axis=1)
        usable = norms > 0
        rows = [r for r, u in zip(rows, usable, strict=True) if u]
        if len(rows) < 2:
            continue
        mat = mat[usable] / norms[usable][:, None]
        cos = np.clip(mat @ mat.T, 0.0, 1.0)
        grid = np.ix_(rows, rows)
        pair[:, :, CH_COSINE][grid] = cos
        pair[:, :, CH_COSINE_OK][grid] = 1.0


def _fill_history(
    pair: Array, request: GenerationRequest, index: dict[str, int]
) -> frozenset[frozenset[str]]:
    """The no-repeat window (ENG-REQ-005): worn on a day with
    `0 <= days_ago < no_repeat_days`. Returns the exact garment-id sets worn
    in it and marks garment pairs worn together (C_novelty pair penalty)."""
    recent: set[frozenset[str]] = set()
    window = request.settings.no_repeat_days
    for entry in request.history:
        days_ago = (request.today - entry.day).days
        if not 0 <= days_ago < window:
            continue
        recent.add(frozenset(entry.garment_ids))
        members = [index[g] for g in entry.garment_ids if g in index]
        for a in members:
            for b in members:
                if a != b:
                    pair[a, b, CH_WORN_TOGETHER] = 1.0
    return frozenset(recent)


def eligible(garment: EngineGarment) -> bool:
    """ENG-REQ-002: only active garments with a slot can be proposed."""
    return garment.status == GarmentStatus.active and garment.category is not None
