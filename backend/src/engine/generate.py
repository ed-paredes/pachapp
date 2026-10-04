"""Two-stage outfit generation with MMR diversity (D1, ENG-REQ-001..026).

Stage 1 enumerates the base templates (A: top+bottom+shoes, B: one_piece+shoes)
as numpy blocks, filters and scores them, and keeps the best K. Stage 2 extends
every kept base greedily with mid_layer, outerwear and accessories, batched
across bases. MMR then picks the final proposals.

Pure: no I/O. The only randomness is a seeded tie-break key per garment.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from engine import constants as C
from engine.context import Array, Context, build_context, eligible
from engine.explain import explain
from engine.scoring import SetView, components, total_score, valid_mask
from engine.types import (
    GenerationRequest,
    InvalidRequest,
    Proposal,
    ProposalItem,
    ScoreBreakdown,
)

_BASE_SLOTS = ("top", "bottom", "one_piece", "shoes")
_SINGLE_SLOTS = ("top", "bottom", "one_piece", "mid_layer", "outerwear", "shoes")
_MID_COL, _OUTER_COL, _ACC_COL = 3, 4, 5
_STACK_ORDER = {"outerwear": 0, "mid_layer": 1, "top": 2, "one_piece": 2, "bottom": 3, "shoes": 4}


def generate_outfits(request: GenerationRequest) -> list[Proposal]:
    """Up to 5 scored, diverse proposals; fewer (or none) for a small wardrobe."""
    pool = [g for g in request.garments if eligible(g) and g.id != request.replace_garment_id]
    ctx = build_context(request, pool)
    by_slot = _group_by_slot(ctx)
    fixed = _validate_fixed(request, ctx)
    max_acc = _accessory_capacity(request, ctx, fixed)

    bases, base_scores = _stage1(ctx, by_slot, fixed)
    if len(bases) == 0:
        return []

    k = C.BASE_TOP_K
    while True:
        members, comps, totals = _stage2(ctx, bases[:k], by_slot, fixed, max_acc)
        picks = _mmr(ctx, members, totals, fixed_idx=_flatten(fixed))
        if len(picks) >= C.PROPOSAL_COUNT or k >= len(bases) or k >= C.BASE_TOP_K_MAX:
            break
        k = min(k * C.BASE_TOP_K_GROWTH, C.BASE_TOP_K_MAX)
    return [_proposal(ctx, members[p], comps[p], float(totals[p])) for p in picks]


# --- request validation --------------------------------------------------------


def _group_by_slot(ctx: Context) -> dict[str, Array]:
    slots: dict[str, list[int]] = {}
    for i, slot in enumerate(ctx.slot):
        slots.setdefault(slot, []).append(i)
    return {s: np.array(v, dtype=np.int64) for s, v in slots.items()}


def _flatten(fixed: dict[str, list[int]]) -> list[int]:
    return [i for ids in fixed.values() for i in ids]


def _validate_fixed(request: GenerationRequest, ctx: Context) -> dict[str, list[int]]:
    """ENG-REQ-026: fixed garments by slot, or `InvalidRequest` (HTTP 400)."""
    fixed: dict[str, list[int]] = {}
    for garment_id in dict.fromkeys(request.fixed_garment_ids):
        if garment_id == request.replace_garment_id:
            raise InvalidRequest("La prenda a cambiar no puede estar entre las prendas fijadas.")
        index = ctx.index.get(garment_id)
        if index is None:
            raise InvalidRequest("Una prenda fijada no existe o no está activa.")
        fixed.setdefault(ctx.slot[index], []).append(index)
    for slot in _SINGLE_SLOTS:
        if len(fixed.get(slot, [])) > 1:
            raise InvalidRequest(f"Solo se puede fijar una prenda en el hueco «{slot}».")
    accessories = fixed.get("accessory", [])
    if len(accessories) > request.settings.max_accessories:
        raise InvalidRequest(
            f"No se pueden fijar más de {request.settings.max_accessories} complementos."
        )
    subtypes = [int(ctx.subcat[i]) for i in accessories]
    if len(set(subtypes)) != len(subtypes):
        raise InvalidRequest("No se pueden fijar dos complementos del mismo tipo.")
    return fixed


def _accessory_capacity(
    request: GenerationRequest, ctx: Context, fixed: dict[str, list[int]]
) -> int:
    available = int((np.array(ctx.slot) == "accessory").sum())
    return max(
        len(fixed.get("accessory", [])),
        min(request.settings.max_accessories, available, C.MAX_ACCESSORIES_CAP),
    )


# --- stage 1: bases ----------------------------------------------------------


def _blocks(groups: list[Array]) -> Iterator[Array]:
    """Cartesian product of index groups, in blocks of bounded size."""
    rest = int(np.prod([len(g) for g in groups[1:]], dtype=np.int64)) if len(groups) > 1 else 1
    step = max(1, C.STAGE1_CHUNK_ROWS // max(rest, 1))
    for start in range(0, len(groups[0]), step):
        grids = np.meshgrid(groups[0][start : start + step], *groups[1:], indexing="ij")
        yield np.stack([g.ravel() for g in grids], axis=1)


def _tie_key(ctx: Context, rows: Array) -> Array:
    return np.where(rows >= 0, ctx.tiebreak[np.maximum(rows, 0)], 0.0).sum(axis=1)


def _order(ctx: Context, rows: Array, scores: Array) -> Array:
    """Best first; exact ties fall back to the seeded tie-break key."""
    return np.lexsort((_tie_key(ctx, rows), -np.round(scores, 12)))


def _stage1(
    ctx: Context, by_slot: dict[str, Array], fixed: dict[str, list[int]]
) -> tuple[Array, Array]:
    """Filtered, scored, ordered bases as `(N, 3)` rows padded with -1."""

    def group(slot: str) -> Array:
        if slot in fixed:  # ENG-REQ-006: a fixed base garment pins its slot
            return np.array(fixed[slot], dtype=np.int64)
        return by_slot.get(slot, np.empty(0, dtype=np.int64))

    # Fixed mid_layer / outerwear / accessory (ENG-REQ-024): the base must stay
    # compatible with them (formality, colour count) so stage 2 can force them.
    fixed_layers = [
        i for slot in ("mid_layer", "outerwear", "accessory") for i in fixed.get(slot, [])
    ]

    # A fixed one_piece rules out template A; a fixed top or bottom rules out B.
    templates = []
    if "one_piece" not in fixed:
        templates.append([group("top"), group("bottom"), group("shoes")])
    if "top" not in fixed and "bottom" not in fixed:
        templates.append([group("one_piece"), group("shoes")])
    kept_rows = np.empty((0, 3), dtype=np.int64)
    kept_scores = np.empty(0)
    for groups in templates:
        if any(len(g) == 0 for g in groups):
            continue
        for rows in _blocks(groups):
            if rows.shape[1] < 3:
                rows = np.hstack([rows, np.full((len(rows), 3 - rows.shape[1]), -1)])
            check = rows
            if fixed_layers:
                check = np.hstack([rows, np.tile(np.array(fixed_layers), (len(rows), 1))])
            view = SetView(ctx, check)
            ok = valid_mask(view)
            if not ok.any():
                continue
            rows = rows[ok]
            base_view = view.subset(ok) if not fixed_layers else SetView(ctx, rows)
            scores = total_score(ctx, components(base_view))
            kept_rows = np.vstack([kept_rows, rows])
            kept_scores = np.concatenate([kept_scores, scores])
            kept_rows, kept_scores = _trim(ctx, kept_rows, kept_scores)
    order = _order(ctx, kept_rows, kept_scores)
    return kept_rows[order], kept_scores[order]


def _trim(ctx: Context, rows: Array, scores: Array) -> tuple[Array, Array]:
    """Keep the best `BASE_TOP_K_MAX` bases (every tie at the cut-off included)."""
    limit = C.BASE_TOP_K_MAX
    if len(rows) <= limit:
        return rows, scores
    rounded = np.round(scores, 12)
    cutoff = np.partition(rounded, len(rounded) - limit)[len(rounded) - limit]
    keep = rounded >= cutoff
    rows, scores = rows[keep], scores[keep]
    order = _order(ctx, rows, scores)[:limit]
    return rows[order], scores[order]


# --- stage 2: layers and accessories ------------------------------------------


def _stage2(
    ctx: Context,
    bases: Array,
    by_slot: dict[str, Array],
    fixed: dict[str, list[int]],
    max_acc: int,
) -> tuple[Array, Array, Array]:
    """Extended outfits `(P, M)`, their components `(P, 4)` and totals `(P,)`."""
    fixed_acc = fixed.get("accessory", [])
    members = np.full((len(bases), _ACC_COL + max_acc), -1, dtype=np.int64)
    members[:, :3] = bases
    for slot, col in (("mid_layer", _MID_COL), ("outerwear", _OUTER_COL)):
        if slot in fixed:
            members[:, col] = fixed[slot][0]
    for offset, garment in enumerate(fixed_acc):
        members[:, _ACC_COL + offset] = garment

    members = members[valid_mask(SetView(ctx, members))]  # forced garments must fit the base
    cur = _totals(ctx, members)

    # Greedy per slot (ENG-REQ-009). Candidates that would break a hard filter
    # are never eligible, so the post-extension re-check (ENG-REQ-023) holds by
    # construction: the best valid option wins, or the slot is left empty.
    for slot, col in (("mid_layer", _MID_COL), ("outerwear", _OUTER_COL)):
        if slot not in fixed:
            _extend(ctx, members, cur, col, by_slot.get(slot, np.empty(0, dtype=np.int64)))
    free = np.array([i for i in by_slot.get("accessory", []) if i not in fixed_acc], dtype=np.int64)
    for step in range(max_acc - len(fixed_acc)):
        _extend(ctx, members, cur, _ACC_COL + len(fixed_acc) + step, free)

    keep = valid_mask(SetView(ctx, members)) & _not_recent(ctx, members)
    members = members[keep]
    comps = components(SetView(ctx, members))
    return members, comps, total_score(ctx, comps)


def _totals(ctx: Context, members: Array) -> Array:
    return total_score(ctx, components(SetView(ctx, members)))


def _not_recent(ctx: Context, members: Array) -> Array:
    """ENG-REQ-005: drop the exact garment sets worn inside the window."""
    if not ctx.recent_sets:
        return np.ones(len(members), dtype=bool)
    ids = [g.id for g in ctx.garments]
    return np.array(
        [frozenset(ids[i] for i in row if i >= 0) not in ctx.recent_sets for row in members],
        dtype=bool,
    )


def _extend(ctx: Context, members: Array, cur: Array, col: int, cands: Array) -> None:
    """For every base, put the candidate with the best marginal total into
    column `col`, only if it beats the current total. Mutates in place."""
    if len(cands) == 0 or len(members) == 0:
        return
    width = len(cands)
    step = max(1, C.STAGE2_CHUNK_ROWS // width)
    for start in range(0, len(members), step):
        block = members[start : start + step]
        rows = np.repeat(block, width, axis=0)
        rows[:, col] = np.tile(cands, len(block))
        scores = np.full(len(rows), -np.inf)
        view = SetView(ctx, rows)
        valid = valid_mask(view)
        if valid.any():
            scores[valid] = total_score(ctx, components(view.subset(valid)))
        scores = scores.reshape(len(block), width)
        best = scores.max(axis=1)
        near = scores >= best[:, None] - C.TIE_EPS
        choice = np.where(near, ctx.tiebreak[cands][None, :], np.inf).argmin(axis=1)
        take = np.isfinite(best) & (best > cur[start : start + step] + C.IMPROVEMENT_EPS)
        block[take, col] = cands[choice[take]]
        cur[start : start + step][take] = best[take]


# --- MMR -----------------------------------------------------------------------


def _mmr(ctx: Context, members: Array, totals: Array, fixed_idx: list[int]) -> list[int]:
    """ENG-REQ-014/015: maximal marginal relevance over the Jaccard similarity
    of garment-id sets, with a garment in at most 2 proposals. Fixed garments
    are in every proposal by definition, so they are exempt from that cap."""
    count = len(members)
    if count == 0:
        return []
    n = len(ctx.garments)
    onehot = np.zeros((count, n))
    rows = np.repeat(np.arange(count), members.shape[1])
    flat = members.ravel()
    present = flat >= 0
    onehot[rows[present], flat[present]] = 1.0
    sizes = onehot.sum(axis=1)
    exempt = np.zeros(n, dtype=bool)
    exempt[fixed_idx] = True
    usage = np.zeros(n)
    tie = _tie_key(ctx, members)
    available = np.ones(count, dtype=bool)
    chosen: list[int] = []
    max_sim = np.zeros(count)
    while len(chosen) < C.PROPOSAL_COUNT:
        capped = (usage >= C.MAX_GARMENT_APPEARANCES) & ~exempt
        eligible_rows = available & ((onehot @ capped.astype(float)) == 0)
        if not eligible_rows.any():
            break
        objective = C.MMR_LAMBDA * totals - (1 - C.MMR_LAMBDA) * max_sim
        objective = np.where(eligible_rows, objective, -np.inf)
        best = objective.max()
        near = objective >= best - C.TIE_EPS
        pick = int(np.where(near, tie, np.inf).argmin())
        chosen.append(pick)
        available[pick] = False
        usage += onehot[pick]
        inter = onehot @ onehot[pick]
        max_sim = np.maximum(max_sim, inter / (sizes + sizes[pick] - inter))
    return chosen


# --- output --------------------------------------------------------------------


def _proposal(ctx: Context, row: Array, comps: Array, total: float) -> Proposal:
    chosen = [int(i) for i in row if i >= 0]
    ordered = sorted(chosen, key=lambda i: (_STACK_ORDER.get(ctx.slot[i], 9), ctx.garments[i].id))
    items = tuple(
        ProposalItem(ctx.garments[i].id, ctx.slot[i], C.LAYER_BY_SLOT[ctx.slot[i]]) for i in ordered
    )
    return Proposal(
        items=items,
        score=total,
        breakdown=ScoreBreakdown(
            color=float(comps[0]),
            style=float(comps[1]),
            novelty=float(comps[2]),
            preference=float(comps[3]),
            total=total,
        ),
        explanation=explain(ctx, ordered, comps),
    )
